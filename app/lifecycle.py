"""文件生命周期：移出相册 / 回收站 / 彻底删除 / 撤销 / 批量改名打标。

三条铁律：
1. 默认删除只把文件挪进回收站（同盘 rename，几乎瞬时），不真抹磁盘；
2. 彻底删除必须走显式入口 + 二次确认，并且留下操作日志；
3. 每个会改文件或索引的动作都写一条 ops，能撤销的立刻能撤回。
"""
import json
import os
import re
import shutil
import sqlite3
import time

from . import db
from .config import BACKUP_DIR, DATA_DIR, THUMB_DIR, THUMB_SIZES, TRASH_DIR

TRASH_DAYS = 30
_SNAP_TABLES = ("tags", "bursts", "album_photos", "person_photos", "photo_places")


# ------------------------------------------------------------------ 快照 / 日志

def _snapshot(pid):
    """删除前把索引里这张照片相关的全部行拍个快照，供回收站与撤销还原。"""
    con = db.db()
    row = con.execute("SELECT * FROM photos WHERE id=?", (pid,)).fetchone()
    if row is None:
        return None
    snap = {"photo": dict(row)}
    for t in _SNAP_TABLES:
        snap[t] = [dict(r) for r in con.execute(f"SELECT * FROM {t} WHERE photo_id=?", (pid,))]
    return snap


def log(kind, summary, payload=None):
    """记录一次可撤销的操作，返回 ops.id。"""
    cur = db.execute(
        "INSERT INTO ops(kind,summary,payload,created_at,undone) VALUES(?,?,?,?,0)",
        (kind, summary, json.dumps(payload or {}, ensure_ascii=False), int(time.time())))
    return cur.lastrowid


def recent_ops(limit=20):
    rows = db.q("SELECT id,kind,summary,created_at,undone FROM ops ORDER BY id DESC LIMIT ?",
                (max(1, min(100, limit)),))
    return [dict(r) for r in rows]


def _undo_payload(op):
    try:
        return json.loads(op["payload"] or "{}")
    except ValueError:
        return {}


def undo(op_id=None):
    """撤销最近一次（或指定）操作。只处理已知且可逆的动作。"""
    if op_id:
        op = db.q1("SELECT * FROM ops WHERE id=? AND undone=0", (op_id,))
    else:
        op = db.q1("SELECT * FROM ops WHERE undone=0 ORDER BY id DESC LIMIT 1")
    if not op:
        return {"ok": False, "msg": "没有可撤销的操作"}
    p = _undo_payload(op)
    kind, n = op["kind"], 0
    if kind in ("trash", "remove"):
        for tid in p.get("trash_ids", []):
            if restore(tid):
                n += 1
    elif kind == "move":
        n = _undo_move(p.get("pairs", []))
    elif kind == "favorite":
        ids, val = p.get("ids", []), 0 if p.get("value") else 1
        if ids:
            marks = ",".join("?" * len(ids))
            db.execute(f"UPDATE photos SET is_favorite=? WHERE id IN ({marks})", [val] + ids)
            n = len(ids)
    elif kind == "tag":
        n = batch_tag(p.get("ids", []), p.get("tag", ""), p.get("action", "add"), log_it=False)["count"]
    elif kind == "album":
        from . import library
        album_id, ids = p.get("album_id"), p.get("ids", [])
        if p.get("action") == "add":
            n = library.album_remove(album_id, ids, log_it=False)["count"]
        else:
            n = library.album_add(album_id, ids, log_it=False)["count"]
    elif kind == "rename":
        n = _undo_rename(p.get("pairs", []))
    else:
        return {"ok": False, "msg": "这一步不支持撤销"}
    db.execute("UPDATE ops SET undone=1 WHERE id=?", (op["id"],))
    return {"ok": True, "kind": kind, "count": n, "summary": op["summary"]}


# ------------------------------------------------------------------ 三步删除

def remove(pid, log_it=True):
    """从相册移除：只摘索引，原文件一个字节都不动。"""
    snap = _snapshot(pid)
    if snap is None:
        return None
    tid = _push_trash(pid, snap["photo"].get("path"), None, snap, "remove")
    db.delete_photo(pid, drop_thumbs=False)
    if log_it:
        log("remove", f"从相册移除 1 张（原图保留）", {"trash_ids": [tid]})
    _prune_thumbs(pid, keep=True)
    return {"id": pid, "mode": "remove", "trash_id": tid}


def trash(pid, log_it=True):
    """移入回收站：文件挪到 photoalbum_data/trash，索引摘掉，可随时恢复。"""
    snap = _snapshot(pid)
    if snap is None:
        return None
    src = snap["photo"].get("path") or ""
    dst = None
    if src and os.path.exists(src):
        dst = _trash_path(pid, src)
        os.makedirs(TRASH_DIR, exist_ok=True)
        try:
            os.replace(src, dst)          # 同盘等于 rename，几万个文件也是毫秒级
        except OSError:
            try:
                shutil.move(src, dst)     # 跨盘兜底：真复制，慢但正确
            except Exception as e:
                return {"id": pid, "mode": "trash", "error": f"移动失败：{e}"}
    tid = _push_trash(pid, src, dst, snap, "trash")
    db.delete_photo(pid, drop_thumbs=False)
    if log_it:
        log("trash", "移入回收站 1 张（30 天内可恢复）", {"trash_ids": [tid]})
    return {"id": pid, "mode": "trash", "trash_id": tid, "trash_path": dst}


def purge(pid):
    """彻底删除：删原文件 + 缩略图 + 索引，不可撤销，必须由界面二次确认。"""
    snap = _snapshot(pid)
    if snap is None:
        return None
    out = db.delete_photo(pid, with_file=True, drop_thumbs=True)
    if out:
        log("purge", f"彻底删除 1 张：{snap['photo'].get('name') or ''}", {"path": out["path"]})
    return out


def batch(ids, mode="trash"):
    """批量执行三档删除，返回逐张结果与汇总。"""
    mode = mode if mode in ("remove", "trash", "purge") else "trash"
    fn = {"remove": remove, "trash": trash, "purge": purge}[mode]
    done, failed, tids = [], [], []
    for pid in list(dict.fromkeys(ids)):
        try:
            if mode == "purge":
                r = fn(pid)
            else:
                r = fn(pid, log_it=False)
            if not r:
                failed.append({"id": pid, "msg": "照片不存在"})
                continue
            if r.get("error"):
                failed.append({"id": pid, "msg": r["error"]})
                continue
            done.append(pid)
            if r.get("trash_id"):
                tids.append(r["trash_id"])
        except Exception as e:
            failed.append({"id": pid, "msg": str(e)})
    if tids and mode != "purge":
        label = "从相册移除" if mode == "remove" else "移入回收站"
        log(mode, f"{label} {len(done)} 张", {"trash_ids": tids})
    elif mode == "purge" and done:
        log("purge", f"彻底删除 {len(done)} 张", {"ids": done})
    return {"mode": mode, "count": len(done), "ids": done, "failed": failed}


# ------------------------------------------------------------------ 回收站

def _trash_path(pid, src):
    base = os.path.basename(src)
    name = f"{pid}_{base}"
    dst = os.path.join(TRASH_DIR, name)
    n = 1
    while os.path.exists(dst):
        dst = os.path.join(TRASH_DIR, f"{pid}_{n}_{base}")
        n += 1
    return dst


def _push_trash(pid, path, trash_path, snap, kind):
    cur = db.execute(
        """INSERT INTO trash(photo_id,path,trash_path,name,snapshot,deleted_at,kind)
           VALUES(?,?,?,?,?,?,?)""",
        (pid, path, trash_path, (snap.get("photo") or {}).get("name"),
         json.dumps(snap, ensure_ascii=False), int(time.time()), kind))
    return cur.lastrowid


def trash_list():
    rows = db.q("""SELECT id,photo_id,path,trash_path,name,deleted_at,kind
                   FROM trash ORDER BY id DESC""")
    out = []
    for r in rows:
        d = dict(r)
        d["exists"] = bool(d["trash_path"]) and os.path.exists(d["trash_path"])
        d["size"] = 0
        try:
            if d["exists"]:
                d["size"] = os.path.getsize(d["trash_path"])
        except OSError:
            pass
        out.append(d)
    return out


def restore(tid):
    """把回收站条目还原：文件回到原路径，索引连同标签/人物/地点/相册一起重建。"""
    row = db.q1("SELECT * FROM trash WHERE id=?", (tid,))
    if not row:
        return False
    snap = json.loads(row["snapshot"] or "{}")
    photo = snap.get("photo") or {}
    path = photo.get("path") or row["path"]
    if not path:
        return False
    if row["kind"] == "trash":
        src = row["trash_path"]
        if not src or not os.path.exists(src):
            return False
        if os.path.exists(path):
            return False               # 原位置已经有同名文件：宁可不动，也不覆盖
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        try:
            os.replace(src, path)
        except OSError:
            try:
                shutil.move(src, path)
            except Exception:
                return False
    pid = _reinsert(photo, snap)
    if not pid:
        return False
    db.execute("DELETE FROM trash WHERE id=?", (tid,))
    _regen_thumbs(pid, path)
    db.fts_rebuild()
    return True


def empty_trash():
    """清空回收站：只删回收站目录里的文件，绝不碰库外路径。"""
    rows = db.q("SELECT id,photo_id,trash_path,kind FROM trash")
    n = 0
    for r in rows:
        if r["kind"] == "trash" and r["trash_path"]:
            p = os.path.abspath(r["trash_path"])
            if p.startswith(os.path.abspath(TRASH_DIR)) and os.path.exists(p):
                try:
                    os.remove(p)
                    n += 1
                except OSError:
                    pass
        _prune_thumbs(r["photo_id"], keep=False)
        db.execute("DELETE FROM trash WHERE id=?", (r["id"],))
    log("empty_trash", f"清空回收站（{n} 个文件）", {})
    return {"files": n, "items": len(rows)}


def _prune_thumbs(pid, keep=True):
    """回收站保留缩略图；彻底清掉时才删缓存。"""
    if keep:
        return
    for key in THUMB_SIZES:
        f = os.path.join(THUMB_DIR, f"{pid}_{key}.jpg")
        try:
            if os.path.exists(f):
                os.remove(f)
        except OSError:
            pass


def _reinsert(photo, snap):
    """按快照恢复 photos 行与关联表；id 被占用时退回自动分配。"""
    con = db.db()
    cols = [r["name"] for r in con.execute("PRAGMA table_info(photos)")]
    data = {k: v for k, v in photo.items() if k in cols}
    if not data.get("path"):
        return None
    names = list(data)
    marks = ",".join("?" * len(names))
    try:
        con.execute(f"INSERT INTO photos({','.join(names)}) VALUES({marks})",
                    [data[k] for k in names])
    except sqlite3.IntegrityError:
        # 同一个 id 或 path 已经被新导入占用了：换 id 再插，保住照片本身
        data.pop("id", None)
        names = list(data)
        marks = ",".join("?" * len(names))
        try:
            con.execute(f"INSERT INTO photos({','.join(names)}) VALUES({marks})",
                        [data[k] for k in names])
        except sqlite3.IntegrityError:
            return None
    row = con.execute("SELECT id FROM photos WHERE path=?", (data["path"],)).fetchone()
    pid = row["id"] if row else None
    if not pid:
        return None
    for t in _SNAP_TABLES:
        for rec in snap.get(t, []):
            rec = dict(rec)
            rec["photo_id"] = pid
            ks = list(rec)
            try:
                con.execute(f"INSERT OR IGNORE INTO {t}({','.join(ks)}) VALUES({','.join('?'*len(ks))})",
                            [rec[k] for k in ks])
            except sqlite3.Error:
                pass
    for t in ("people", "places"):
        col = "person_id" if t == "people" else "place_id"
        join = "person_photos" if t == "people" else "photo_places"
        got = con.execute(f"SELECT {col} x FROM {join} WHERE photo_id=?", (pid,)).fetchall()
        for g in {x["x"] for x in got}:
            db._refresh_group(con, t, join, col, g)
    con.commit()
    return pid


def _regen_thumbs(pid, path):
    """恢复后的照片补回缩略图与直方图；失败不影响索引本身。"""
    if not path or not os.path.exists(path):
        return
    try:
        from . import scanner
        s = scanner.make_thumb(pid, path, "s")
        scanner.make_thumb(pid, path, "m")
        if s:
            hist, avg = scanner.thumb_stats(s)
            if hist:
                db.execute("UPDATE photos SET hist=?, avg_rgb=? WHERE id=?", (hist, avg, pid))
    except Exception:
        pass


# ------------------------------------------------------------------ 撤销移动 / 改名

def _undo_move(pairs):
    n = 0
    for item in pairs:
        try:
            pid, old, new = item
        except ValueError:
            continue
        if not os.path.exists(new):
            continue
        if os.path.exists(old):
            continue
        os.makedirs(os.path.dirname(old) or ".", exist_ok=True)
        try:
            os.replace(new, old)
        except OSError:
            try:
                shutil.move(new, old)
            except Exception:
                continue
        try:
            db.execute("""UPDATE photos SET path=?,name=?,dir=?,ext=?,mtime=?
                          WHERE id=?""",
                       (old, os.path.basename(old), os.path.dirname(old),
                        os.path.splitext(old)[1].lower(), int(os.path.getmtime(old)), pid))
            n += 1
        except Exception:
            continue
    if n:
        db.fts_rebuild()
    return n


# ------------------------------------------------------------------ 批量改名 / 打标

_TOKEN = re.compile(r"\{(date|time|name|seq|ext)\}")


def batch_rename(ids, template="{date}_{seq}", start=1):
    """批量改文件名（只改硬盘上的名字，不复制也不删除）。

    模板支持 {date} {time} {name} {seq} {ext}；重名自动加 _1、_2，绝不覆盖已有文件。
    """
    if not template or not template.strip():
        raise ValueError("请填写文件名模板")
    rows = [dict(r) for r in db.q(
        f"SELECT id,path,name,taken_at FROM photos WHERE id IN ({','.join('?'*len(ids))})"
        if ids else "SELECT id,path,name,taken_at FROM photos WHERE 0",
        ids or ())]
    rows.sort(key=lambda r: (r["taken_at"] or 0, r["id"]))
    done, failed, pairs = 0, [], []
    used = set()
    for k, r in enumerate(rows):
        src = r["path"]
        if not src or not os.path.exists(src):
            failed.append({"id": r["id"], "msg": "文件不存在"})
            continue
        base, ext = os.path.splitext(r["name"] or os.path.basename(src))
        t = time.localtime(r["taken_at"] or os.path.getmtime(src))

        def rep(m):
            key = m.group(1)
            return {
                "date": time.strftime("%Y%m%d", t), "time": time.strftime("%H%M%S", t),
                "name": base, "seq": str(start + k).zfill(3), "ext": ext.lstrip("."),
            }[key]

        new_base = _TOKEN.sub(rep, template).strip() or base
        new_name = new_base + ext
        folder = os.path.dirname(src)
        dst = os.path.join(folder, new_name)
        n = 1
        while dst.lower() in used or (os.path.exists(dst) and os.path.normcase(dst) != os.path.normcase(src)):
            dst = os.path.join(folder, f"{new_base}_{n}{ext}")
            n += 1
        used.add(dst.lower())
        if os.path.normcase(dst) == os.path.normcase(src):
            continue
        try:
            os.replace(src, dst)
        except OSError:
            try:
                shutil.move(src, dst)
            except Exception as e:
                failed.append({"id": r["id"], "msg": str(e)})
                continue
        try:
            db.execute("""UPDATE photos SET path=?,name=?,dir=?,ext=?,mtime=?
                          WHERE id=?""",
                       (dst, os.path.basename(dst), folder,
                        os.path.splitext(dst)[1].lower(), int(os.path.getmtime(dst)), r["id"]))
            pairs.append([r["id"], src, dst])
            done += 1
        except Exception:
            failed.append({"id": r["id"], "msg": "索引更新失败"})
    if done:
        log("rename", f"批量重命名 {done} 张", {"pairs": pairs})
        db.fts_rebuild()
    return {"count": done, "failed": failed, "pairs": pairs}


def _undo_rename(pairs):
    return _undo_move(pairs)


def batch_tag(ids, tag, action="add", log_it=True):
    tag = (tag or "").strip()
    if not tag:
        raise ValueError("标签不能为空")
    if not ids:
        raise ValueError("没有选中照片")
    con = db.db()
    n = 0
    if action == "remove":
        for pid in ids:
            cur = con.execute("DELETE FROM tags WHERE photo_id=? AND tag=?", (pid, tag))
            n += cur.rowcount
    else:
        for pid in ids:
            con.execute("INSERT OR IGNORE INTO tags(photo_id,tag,source,confidence) VALUES(?,?,'manual',1.0)",
                        (pid, tag))
            n += 1
    con.commit()
    db.fts_rebuild()
    if log_it and n:
        log("tag", f"{'添加' if action != 'remove' else '移除'}标签「{tag}」{n} 处",
            {"ids": ids, "tag": tag, "action": action})
    return {"count": n, "tag": tag, "action": action}


# ------------------------------------------------------------------ 维护

def backup_now():
    """用 SQLite 在线备份 API 打一份快照，保留最近 8 份。"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"album_{stamp}.db")
    src = db.db()
    out = sqlite3.connect(dst)
    try:
        src.backup(out)
        out.commit()
    finally:
        out.close()
    olds = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("album_") and f.endswith(".db"))
    for f in olds[:-8]:
        try:
            os.remove(os.path.join(BACKUP_DIR, f))
        except OSError:
            pass
    return {"file": dst, "size": os.path.getsize(dst)}


def backups():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    out = []
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if not f.endswith(".db"):
            continue
        p = os.path.join(BACKUP_DIR, f)
        out.append({"name": f, "size": os.path.getsize(p),
                    "time": int(os.path.getmtime(p))})
    return out[:20]


def self_check():
    """索引体检：路径失效、重复内容、孤立缩略图、回收站占用。"""
    rows = db.q("SELECT id,path,hash,size FROM photos")
    missing = [r["id"] for r in rows if not r["path"] or not os.path.exists(r["path"])]
    dup = db.q("""SELECT hash, COUNT(*) c FROM photos WHERE hash IS NOT NULL
                  GROUP BY hash HAVING c>1""")
    keep = {f"{r['id']}_" for r in rows}
    orphans = 0
    try:
        for f in os.listdir(THUMB_DIR):
            if not f.endswith(".jpg"):
                continue
            if not any(f.startswith(k) for k in keep):
                orphans += 1
    except OSError:
        pass
    tr = db.q1("SELECT COUNT(*) c FROM trash")["c"]
    tr_size = 0
    try:
        for f in os.listdir(TRASH_DIR):
            p = os.path.join(TRASH_DIR, f)
            if os.path.isfile(p):
                tr_size += os.path.getsize(p)
    except OSError:
        pass
    return {
        "photos": len(rows), "missing": len(missing), "missing_ids": missing[:50],
        "dup_groups": len(dup), "orphan_thumbs": orphans,
        "trash_items": tr, "trash_bytes": tr_size,
        "db_bytes": os.path.getsize(os.path.join(DATA_DIR, "album.db"))
        if os.path.exists(os.path.join(DATA_DIR, "album.db")) else 0,
    }


def purge_stale(days=TRASH_DAYS):
    """清掉超过保留期的回收站条目（启动时跑一次）。"""
    cutoff = int(time.time()) - days * 86400
    rows = db.q("SELECT id FROM trash WHERE deleted_at<?", (cutoff,))
    for r in rows:
        row = db.q1("SELECT photo_id,trash_path,kind FROM trash WHERE id=?", (r["id"],))
        if row and row["kind"] == "trash" and row["trash_path"]:
            p = os.path.abspath(row["trash_path"])
            if p.startswith(os.path.abspath(TRASH_DIR)) and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        _prune_thumbs(row["photo_id"], keep=False)
        db.execute("DELETE FROM trash WHERE id=?", (r["id"],))
    return len(rows)
