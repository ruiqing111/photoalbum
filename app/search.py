"""查询与搜索：结构化筛选 + 关键词 + 语义（如可用）+ 聚合视图。"""
import time

from . import ai, db, geo, library, people


def _where(q=None, tag=None, date_from=None, date_to=None, camera=None,
           min_quality=None, favorite=None, kind=None, place_id=None, person_id=None,
           dir=None, hidden=0):
    """把筛选参数翻译成 WHERE 子句，供列表查询与「整理到文件夹」共用。

    hidden 默认 0：所有常规视图自动过滤掉隐藏照片；「隐藏」页传 1 才看得到。
    """
    where, args = ["1=1"], []
    if hidden is not None:
        where.append("p.hidden=?"); args.append(1 if hidden else 0)
    if kind:
        where.append("p.kind=?"); args.append(kind)
    if dir:
        where.append("p.dir=?"); args.append(dir)
    if tag:
        where.append("p.id IN (SELECT photo_id FROM tags WHERE tag=?)"); args.append(tag)
    if person_id:
        where.append("p.id IN (SELECT photo_id FROM person_photos WHERE person_id=?)")
        args.append(person_id)
    if place_id:
        where.append("p.id IN (SELECT photo_id FROM photo_places WHERE place_id=?)")
        args.append(place_id)
    if date_from:
        where.append("p.taken_at>=?"); args.append(int(date_from))
    if date_to:
        where.append("p.taken_at<=?"); args.append(int(date_to))
    if camera:
        where.append("(p.camera_model LIKE ? OR p.camera_make LIKE ?)")
        args += [f"%{camera}%", f"%{camera}%"]
    if min_quality is not None:
        where.append("p.quality>=?"); args.append(float(min_quality))
    if favorite:
        where.append("p.is_favorite=1")
    semantic_ids = None
    if q:
        # 关键词与语义两路都试：有 CLIP 时以语义排序为主，FTS 命中并入结果，
        # 避免「有向量就搜不到文件名」这种单路检索的老问题
        sem = ai.semantic_search(q) if ai.ai_status()["clip"] else None
        fts = db.fts_ids(q)
        if sem is not None:
            semantic_ids = [pid for pid, _ in sem]
            if fts:
                semantic_ids = list(dict.fromkeys(semantic_ids + fts))
            marks = ",".join("?" * len(semantic_ids))
            where.append(f"p.id IN ({marks})" if semantic_ids else "1=0")
            args += semantic_ids
        elif fts:
            where.append(f"p.id IN ({','.join('?'*len(fts))})")
            args += fts
        elif fts is None:
            like = f"%{q}%"
            where.append("""(p.name LIKE ? OR p.dir LIKE ? OR p.id IN
                (SELECT photo_id FROM tags WHERE tag LIKE ?))""")
            args += [like, like, like]
        else:
            where.append("1=0")
    return where, args, semantic_ids


def all_ids(**filters):
    """返回当前筛选下的全部照片 id（不分页），供「全选所有匹配」使用。"""
    where, args, _ = _where(**filters)
    return [r["id"] for r in db.q(
        f"SELECT p.id FROM photos p WHERE {' AND '.join(where)} ORDER BY p.taken_at DESC", args)]


def collect_rows(ids=None, **filters):
    """取出全部匹配行（不分页），用于整理到文件夹。"""
    if ids:
        marks = ",".join("?" * len(ids))
        return [dict(r) for r in db.q(
            f"""SELECT id, path, name, dir, ext, kind, taken_at, size FROM photos
                WHERE id IN ({marks}) ORDER BY taken_at DESC""", ids)]
    where, args, _ = _where(**filters)
    return [dict(r) for r in db.q(
        f"""SELECT p.id, p.path, p.name, p.dir, p.ext, p.kind, p.taken_at, p.size
            FROM photos p WHERE {' AND '.join(where)} ORDER BY p.taken_at DESC""", args)]


def search_photos(q=None, tag=None, date_from=None, date_to=None, camera=None,
                  min_quality=None, favorite=None, kind=None, place_id=None,
                  person_id=None, dir=None, hidden=0, sort="taken_desc",
                  page=1, page_size=80):
    where, args, semantic_ids = _where(
        q=q, tag=tag, date_from=date_from, date_to=date_to, camera=camera,
        min_quality=min_quality, favorite=favorite, kind=kind,
        place_id=place_id, person_id=person_id, dir=dir, hidden=hidden)
    order = {
        "taken_desc": "p.taken_at DESC", "taken_asc": "p.taken_at ASC",
        "quality": "p.quality DESC", "size": "p.size DESC",
    }.get(sort, "p.taken_at DESC")
    base = f"FROM photos p WHERE {' AND '.join(where)}"
    total = db.q1(f"SELECT COUNT(*) c {base}", args)["c"]
    rows = db.q(f"SELECT p.* {base} ORDER BY {order} LIMIT ? OFFSET ?",
                args + [page_size, (page - 1) * page_size])
    items = [dict(r) for r in rows]
    _attach(items)
    if semantic_ids is not None:
        rank = {pid: i for i, pid in enumerate(semantic_ids)}
        items.sort(key=lambda it: rank.get(it["id"], 10**9))
    return {"items": items, "total": total, "page": page,
            "semantic": bool(q and semantic_ids is not None)}


def _attach(items):
    """补齐每张照片的标签、地点名、人物名。"""
    if not items:
        return
    ids = [it["id"] for it in items]
    marks = ",".join("?" * len(ids))
    tag_map, place_map, person_map = {}, {}, {}
    for r in db.q(f"SELECT photo_id, tag FROM tags WHERE photo_id IN ({marks})", ids):
        tag_map.setdefault(r["photo_id"], []).append(r["tag"])
    for r in db.q(f"""SELECT pp.photo_id, pl.name FROM photo_places pp
                      JOIN places pl ON pl.id=pp.place_id
                      WHERE pp.photo_id IN ({marks})""", ids):
        place_map[r["photo_id"]] = r["name"]
    for r in db.q(f"""SELECT pph.photo_id, pe.name FROM person_photos pph
                      JOIN people pe ON pe.id=pph.person_id
                      WHERE pph.photo_id IN ({marks})""", ids):
        person_map.setdefault(r["photo_id"], []).append(r["name"])
    for it in items:
        it["tags"] = tag_map.get(it["id"], [])
        it["place"] = place_map.get(it["id"])
        it["people"] = person_map.get(it["id"], [])


def timeline():
    return [dict(r) for r in db.q("""SELECT strftime('%Y-%m', taken_at, 'unixepoch', 'localtime') ym,
        COUNT(*) c, MIN(taken_at) t0 FROM photos WHERE hidden=0
        GROUP BY ym ORDER BY ym DESC""")]


def tag_counts():
    return [dict(r) for r in db.q(
        "SELECT tag, COUNT(*) c FROM tags GROUP BY tag ORDER BY c DESC")]


def stats():
    p = db.q1("SELECT COUNT(*) c, COALESCE(SUM(size),0) s FROM photos WHERE hidden=0")
    return {
        "photos": p["c"], "bytes": p["s"],
        "tags": db.q1("SELECT COUNT(DISTINCT tag) c FROM tags")["c"],
        "bursts": db.q1("SELECT COUNT(DISTINCT group_id) c FROM bursts")["c"],
        "picks": db.q1("SELECT COUNT(*) c FROM bursts WHERE is_pick=1")["c"],
        "favorites": db.q1("SELECT COUNT(*) c FROM photos WHERE is_favorite=1 AND hidden=0")["c"],
        "with_gps": db.q1("SELECT COUNT(*) c FROM photos WHERE gps_lat IS NOT NULL AND hidden=0")["c"],
        "embeddings": db.q1("SELECT COUNT(*) c FROM embeddings")["c"],
        "people": db.q1("SELECT COUNT(*) c FROM people")["c"],
        "places": db.q1("SELECT COUNT(*) c FROM places")["c"],
        "videos": db.q1("SELECT COUNT(*) c FROM photos WHERE kind='video' AND hidden=0")["c"],
        "hidden": db.q1("SELECT COUNT(*) c FROM photos WHERE hidden=1")["c"],
        "live": db.q1("SELECT COUNT(*) c FROM photos WHERE is_live=1 AND hidden=0")["c"],
        "events": db.q1("""SELECT COUNT(*) c FROM (
              SELECT 1 FROM photos WHERE taken_at IS NOT NULL AND hidden=0
              GROUP BY strftime('%Y-%m-%d', taken_at,'unixepoch','localtime')
              HAVING COUNT(*)>=5)""")["c"],
        "months": db.q1("""SELECT COUNT(DISTINCT strftime('%Y-%m', taken_at,'unixepoch','localtime'))
              c FROM photos WHERE taken_at IS NOT NULL AND hidden=0""")["c"],
        "albums": db.q1("SELECT COUNT(*) c FROM albums")["c"],
        "trash": db.q1("SELECT COUNT(*) c FROM trash")["c"],
        "trips": len(library.trips()),
        "ai": ai.ai_status(),
    }


def _cover_of(ids):
    """从 id 列表里挑一张最适合当封面的（质量高、横向优先）。"""
    if not ids:
        return None
    marks = ",".join("?" * len(ids))
    r = db.q1(f"""SELECT id FROM photos WHERE id IN ({marks})
                  ORDER BY quality DESC LIMIT 1""", ids)
    return r["id"] if r else None


def overview():
    """概览页：统计 + 四个维度入口卡片。"""
    st = stats()
    ppl = people.people_list()[:8]
    pls = geo.place_list()[:8]
    tags = tag_counts()[:10]
    memories = []
    for m in timeline()[:1]:
        ys, ms = m["ym"].split("-")
        ids = [r["id"] for r in db.q(
            """SELECT id FROM photos WHERE strftime('%Y-%m', taken_at,'unixepoch','localtime')=?
               ORDER BY quality DESC LIMIT 60""", (m["ym"],))]
        memories.append({"title": f"{ys}年{int(ms)}月", "subtitle": f"{m['c']} 张照片",
                         "cover": _cover_of(ids), "kind": "month", "key": m["ym"]})
    return {"stats": st, "people": ppl, "places": pls, "tags": tags, "memories": memories}


def memories():
    """回忆卡片：按月成组 + 按城市成组。"""
    out = []
    for m in db.q("""SELECT strftime('%Y-%m', taken_at,'unixepoch','localtime') ym, COUNT(*) c
                     FROM photos GROUP BY ym ORDER BY ym DESC LIMIT 12"""):
        ys, ms = m["ym"].split("-")
        ids = [r["id"] for r in db.q(
            """SELECT id FROM photos WHERE strftime('%Y-%m', taken_at,'unixepoch','localtime')=?
               ORDER BY quality DESC LIMIT 60""", (m["ym"],))]
        out.append({"title": f"{ys}年 {int(ms)}月", "subtitle": f"{m['c']} 张 · 月度回忆",
                    "cover": _cover_of(ids), "kind": "month", "key": m["ym"],
                    "count": m["c"]})
    for pl in geo.place_list():
        ids = [r["photo_id"] for r in db.q(
            "SELECT photo_id FROM photo_places WHERE place_id=?", (pl["id"],))]
        out.append({"title": pl["name"], "subtitle": f"{pl['photo_count']} 张 · 地点",
                    "cover": pl["cover_photo_id"], "kind": "place", "key": pl["id"],
                    "count": pl["photo_count"]})
    return out


def things():
    """事物维度：标签分组（含代表图）。"""
    out = []
    for t in tag_counts():
        ids = [r["photo_id"] for r in db.q(
            "SELECT photo_id FROM tags WHERE tag=? LIMIT 200", (t["tag"],))]
        out.append({"name": t["tag"], "count": t["c"], "cover": _cover_of(ids)})
    return out


def curated(reason=None):
    """精选流：连拍精选 + 高质量 + 用户收藏，合并去重并附理由。"""
    got, order = {}, []
    def add(pid, why):
        if pid not in got:
            got[pid] = why
            order.append(pid)
    for r in db.q("""SELECT p.id FROM bursts b JOIN photos p ON p.id=b.photo_id
                    WHERE b.is_pick=1 ORDER BY p.quality DESC LIMIT 40"""):
        add(r["id"], "连拍精选")
    for r in db.q("SELECT id FROM photos WHERE quality>=68 ORDER BY quality DESC LIMIT 40"):
        add(r["id"], "画质优秀")
    for r in db.q("SELECT id FROM photos WHERE is_favorite=1 ORDER BY taken_at DESC LIMIT 40"):
        add(r["id"], "已收藏")
    for r in db.q("""SELECT id FROM photos WHERE rating>=4 ORDER BY rating DESC LIMIT 20"""):
        add(r["id"], "高分评价")
    if not order:
        for r in db.q("SELECT id FROM photos ORDER BY quality DESC LIMIT 40"):
            add(r["id"], "自动推荐")
    if reason:
        order = [p for p in order if reason in got.get(p, "")]
    if not order:
        return {"items": [], "total": 0}
    marks = ",".join("?" * len(order))
    rows = {r["id"]: dict(r) for r in db.q(f"SELECT * FROM photos WHERE id IN ({marks})", order)}
    items = []
    for pid in order:
        if pid in rows:
            it = rows[pid]
            it["reason"] = got[pid]
            items.append(it)
    _attach(items)
    return {"items": items, "total": len(items), "hero": items[0] if items else None}
