"""SQLite 索引库：照片、标签、连拍组、相册、向量。"""
import os
import sqlite3
import threading
from .config import DB_PATH, THUMB_DIR, THUMB_SIZES

_local = threading.local()

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS photos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT UNIQUE, name TEXT, dir TEXT, ext TEXT,
  size INTEGER, width INTEGER, height INTEGER,
  duration REAL, fps REAL, vcodec TEXT,
  taken_at INTEGER, mtime INTEGER, hash TEXT,
  camera_make TEXT, camera_model TEXT, lens TEXT,
  focal REAL, aperture REAL, shutter TEXT, iso INTEGER,
  gps_lat REAL, gps_lon REAL, gps_alt REAL, orientation INTEGER,
  quality REAL DEFAULT 0, is_favorite INTEGER DEFAULT 0, rating INTEGER DEFAULT 0,
  kind TEXT DEFAULT 'photo',
  -- hidden=1 只是隐藏显示：照片仍在库里、仍在原位置，随时可以取消隐藏
  hidden INTEGER DEFAULT 0,
  added_at INTEGER,
  -- 缩略图直方图与平均色：导入时一次算好，查看器切图只读库，不再现场跑 PIL
  hist TEXT, avg_rgb TEXT
);
CREATE INDEX IF NOT EXISTS idx_taken ON photos(taken_at);
CREATE INDEX IF NOT EXISTS idx_dir ON photos(dir);
CREATE TABLE IF NOT EXISTS tags(
  photo_id INTEGER, tag TEXT, source TEXT, confidence REAL DEFAULT 1.0,
  PRIMARY KEY(photo_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_tag ON tags(tag);
CREATE TABLE IF NOT EXISTS bursts(
  group_id TEXT, photo_id INTEGER, is_pick INTEGER DEFAULT 0,
  PRIMARY KEY(group_id, photo_id)
);
CREATE TABLE IF NOT EXISTS albums(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_at INTEGER,
  cover_photo_id INTEGER
);
CREATE TABLE IF NOT EXISTS album_photos(
  album_id INTEGER, photo_id INTEGER, PRIMARY KEY(album_id, photo_id)
);
-- 回收站：remove=只摘索引，trash=文件已移到 photoalbum_data/trash
CREATE TABLE IF NOT EXISTS trash(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  photo_id INTEGER, path TEXT, trash_path TEXT, name TEXT,
  snapshot TEXT, deleted_at INTEGER, kind TEXT
);
-- 操作日志：支持撤销，也让用户看得见自己到底动过什么
CREATE TABLE IF NOT EXISTS ops(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT, summary TEXT, payload TEXT, created_at INTEGER,
  undone INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ops_time ON ops(created_at);
CREATE TABLE IF NOT EXISTS embeddings(
  photo_id INTEGER PRIMARY KEY, model TEXT, vec BLOB
);
CREATE TABLE IF NOT EXISTS people(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, cover_photo_id INTEGER, photo_count INTEGER DEFAULT 0,
  created_at INTEGER, updated_at INTEGER,
  -- person=某个人的照片集合；group=合影（一张照片里有多人）
  kind TEXT DEFAULT 'person'
);
CREATE TABLE IF NOT EXISTS person_photos(
  person_id INTEGER, photo_id INTEGER, dist REAL DEFAULT 0, face_idx INTEGER DEFAULT 0,
  PRIMARY KEY(person_id, photo_id)
);
CREATE INDEX IF NOT EXISTS idx_person_photo ON person_photos(person_id);
CREATE TABLE IF NOT EXISTS person_emb(
  photo_id INTEGER, face_idx INTEGER, score REAL, size REAL, vec BLOB,
  PRIMARY KEY(photo_id, face_idx)
);
CREATE TABLE IF NOT EXISTS places(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE, lat REAL, lon REAL,
  cover_photo_id INTEGER, photo_count INTEGER DEFAULT 0, kind TEXT DEFAULT 'city'
);
CREATE TABLE IF NOT EXISTS photo_places(
  photo_id INTEGER PRIMARY KEY, place_id INTEGER, distance_km REAL
);
CREATE INDEX IF NOT EXISTS idx_photo_place ON photo_places(place_id);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""

# 关键词全文索引：FTS5 的 MATCH 比 LIKE '%x%' 快一个量级（大库才明显，
# 小库上也没坏处）。部分 Python 发行版没编译 FTS5，所以建表失败时整体降级。
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS photos_fts USING fts5(
  name, dir, tokens,
  content='', tokenize='unicode61 remove_diacritics 2'
);
"""


def db() -> sqlite3.Connection:
    con = getattr(_local, "con", None)
    if con is None:
        # WAL 只有一个写者：后台分析线程逐张写库时，请求线程的收藏/删除可能撞上写锁。
        # 默认只等 5 秒就抛 database is locked，这里放宽到 30 秒，让它自己排队等锁。
        con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        # 移动硬盘上 FULL 同步会把每一条写入都变成一次物理 fsync，
        # 批量导入时慢到不可接受；WAL + NORMAL 只在检查点落盘，掉电最多丢最后几条索引，
        # 重扫即可补回，原片一个字节都不受影响。
        con.execute("PRAGMA synchronous=NORMAL")
        _local.con = con
    return con


def defer_commits(on=True):
    """当前线程是否延后提交（批量导入用）。

    只影响本线程的连接：导入线程在内存里攒几十条再一次性提交，
    网页线程的收藏/删除照样即时落盘，不会被拖住。
    """
    _local.defer = bool(on)


def commit():
    db().commit()


def init():
    con = db()
    con.executescript(SCHEMA)
    _migrate(con)
    global FTS
    try:
        con.executescript(FTS_SCHEMA)
        FTS = True
    except sqlite3.OperationalError:      # 没编译 FTS5：全部走 LIKE，功能不受影响
        FTS = False
    con.commit()


FTS = False


def fts_rebuild():
    """整表重建关键词索引。导入/删除后调用，是全量重建（几千张只要几十毫秒）。"""
    if not FTS:
        return 0
    con = db()
    # contentless 表不支持 DELETE，整表重建最省事（几千行也就几十毫秒）
    con.executescript("DROP TABLE IF EXISTS photos_fts;" + FTS_SCHEMA)
    con.execute("""INSERT INTO photos_fts(rowid, name, dir, tokens)
                   SELECT p.id, COALESCE(p.name,''), COALESCE(p.dir,''),
                          COALESCE((SELECT group_concat(tag, ' ') FROM tags
                                    WHERE photo_id=p.id), '')
                   FROM photos p""")
    con.commit()
    return con.execute("SELECT COUNT(*) c FROM photos_fts").fetchone()["c"]


def fts_ids(text, limit=20000):
    """关键词 → 照片 id 列表。只在 FTS 可用时返回，否则返回 None（调用方回退 LIKE）。"""
    if not FTS or not text:
        return None
    safe = "".join(ch if ch.isalnum() or ch in " _-" else " " for ch in text).strip()
    if not safe:
        return None
    # 每个词都加前缀匹配（"海边" 能命中 "海边日落"）
    expr = " AND ".join(f'"{w}"*' for w in safe.split() if w)
    if not expr:
        return None
    try:
        # 注意：本模块里 db 是连接函数，不是模块自身，所以直接用 db()
        rows = db().execute(
            "SELECT rowid FROM photos_fts WHERE photos_fts MATCH ? LIMIT ?",
            (expr, limit + 1)).fetchall()
        # 命中太多（比如搜 ".jpg" 等于全库）：ID 列表塞进 IN (...) 会撑爆参数上限，
        # 这种关键词交回 LIKE 走全表反而更稳
        if len(rows) > limit:
            return None
        return [r["rowid"] for r in rows]
    except sqlite3.OperationalError:
        return None


def _migrate(con):
    """给已经在用的库补新列。

    CREATE TABLE IF NOT EXISTS 对已存在的表什么都不做，所以视频那几列
    （时长/帧率/编码）光写进 SCHEMA 是到不了老库上的，必须显式 ALTER。
    """
    have = {r["name"] for r in con.execute("PRAGMA table_info(photos)")}
    for col, decl in (("duration", "REAL"), ("fps", "REAL"), ("vcodec", "TEXT"),
                      ("hist", "TEXT"), ("avg_rgb", "TEXT"),
                      ("rotate", "INTEGER DEFAULT 0"), ("is_live", "INTEGER DEFAULT 0"),
                      ("live_path", "TEXT"), ("hidden", "INTEGER DEFAULT 0")):
        if col not in have:
            con.execute(f"ALTER TABLE photos ADD COLUMN {col} {decl}")
    # 旧版靠肤色规则存的「人物特征」已被 YuNet+SFace 取代，留着只会误导，直接清掉
    con.execute("DROP TABLE IF EXISTS person_feats")
    # 老库的人物表没有 kind / face_idx：补列，并把 person_emb 换成「一照多脸」结构
    cols = {r["name"] for r in con.execute("PRAGMA table_info(albums)")}
    if "cover_photo_id" not in cols:
        con.execute("ALTER TABLE albums ADD COLUMN cover_photo_id INTEGER")
    cols = {r["name"] for r in con.execute("PRAGMA table_info(people)")}
    if "kind" not in cols:
        con.execute("ALTER TABLE people ADD COLUMN kind TEXT DEFAULT 'person'")
    cols = {r["name"] for r in con.execute("PRAGMA table_info(person_photos)")}
    if "face_idx" not in cols:
        con.execute("ALTER TABLE person_photos ADD COLUMN face_idx INTEGER DEFAULT 0")
    cols = {r["name"] for r in con.execute("PRAGMA table_info(person_emb)")}
    if cols and "face_idx" not in cols:
        con.execute("DROP TABLE person_emb")
        con.executescript("""CREATE TABLE person_emb(
          photo_id INTEGER, face_idx INTEGER, score REAL, size REAL, vec BLOB,
          PRIMARY KEY(photo_id, face_idx));
        """)


def q(sql, args=()):
    return db().execute(sql, args).fetchall()


def q1(sql, args=()):
    return db().execute(sql, args).fetchone()


def execute(sql, args=()):
    con = db()
    cur = con.execute(sql, args)
    if not getattr(_local, "defer", False):
        con.commit()
    return cur


def executemany(sql, rows):
    con = db()
    con.executemany(sql, rows)
    if not getattr(_local, "defer", False):
        con.commit()


def delete_photo(pid, with_file=False, drop_thumbs=True):
    """把一张照片从相册里摘掉。

    默认只删索引：原文件一个字节都不动。这些是不可再生的原片，而且躺在移动硬盘上，
    删掉就真找不回来了；相册索引删了随时能重新导入找回来。
    with_file 只给「彻底删除」的强确认流程用；drop_thumbs=False 用于移入回收站
    （回收站里还要显示缩略图，只有彻底删干净时才清缓存）。
    """
    con = db()
    row = con.execute("SELECT path FROM photos WHERE id=?", (pid,)).fetchone()
    if row is None:
        return None
    path = row["path"]
    out = {"id": pid, "path": path, "with_file": bool(with_file), "thumbs": 0}

    # 缓存缩略图（{pid}_s.jpg / {pid}_m.jpg）
    for key in THUMB_SIZES:
        f = os.path.join(THUMB_DIR, f"{pid}_{key}.jpg")
        try:
            if drop_thumbs and os.path.exists(f):
                os.remove(f)
                out["thumbs"] += 1
        except OSError:
            pass

    if with_file:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    # 记下受影响的聚合行，删完再回填计数/封面
    person_ids = [r["person_id"] for r in
                  con.execute("SELECT person_id FROM person_photos WHERE photo_id=?", (pid,))]
    place_ids = [r["place_id"] for r in
                 con.execute("SELECT place_id FROM photo_places WHERE photo_id=?", (pid,))]

    for t in ("tags", "bursts", "album_photos", "embeddings", "person_emb",
              "person_photos", "photo_places"):
        con.execute(f"DELETE FROM {t} WHERE photo_id=?", (pid,))
    con.execute("DELETE FROM photos WHERE id=?", (pid,))

    for x in set(person_ids):
        _refresh_group(con, "people", "person_photos", "person_id", x)
    for x in set(place_ids):
        _refresh_group(con, "places", "photo_places", "place_id", x)

    con.commit()
    return out


def _refresh_group(con, table, join_table, col, gid):
    """照片被删后回填某个聚合行：计数归零就删行，封面被删就改挂剩余照片里画质最高的。"""
    n = con.execute(f"SELECT COUNT(*) c FROM {join_table} WHERE {col}=?", (gid,)).fetchone()["c"]
    if not n:
        con.execute(f"DELETE FROM {join_table} WHERE {col}=?", (gid,))
        con.execute(f"DELETE FROM {table} WHERE id=?", (gid,))
        return
    cover = con.execute(f"SELECT cover_photo_id c FROM {table} WHERE id=?", (gid,)).fetchone()
    if cover and con.execute("SELECT 1 FROM photos WHERE id=?", (cover["c"],)).fetchone():
        con.execute(f"UPDATE {table} SET photo_count=? WHERE id=?", (n, gid))
        return
    best = con.execute(
        f"SELECT j.photo_id p FROM {join_table} j JOIN photos ph ON ph.id=j.photo_id "
        f"WHERE j.{col}=? ORDER BY ph.quality DESC LIMIT 1", (gid,)).fetchone()
    con.execute(f"UPDATE {table} SET photo_count=?, cover_photo_id=? WHERE id=?",
                (n, best["p"] if best else None, gid))
