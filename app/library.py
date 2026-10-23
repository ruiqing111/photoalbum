"""集合与检索面：相册、文件夹、重复照片、事件聚合。

这些是「成熟相册软件」最常用的四条整理路径，全部只读索引，
不复制照片本体；唯一的写操作是相册成员关系。
"""
import os
import time

from . import db, lifecycle


# ------------------------------------------------------------------ 相册

def _refresh_cover(album_id):
    r = db.q1("""SELECT ap.photo_id FROM album_photos ap JOIN photos p ON p.id=ap.photo_id
                 WHERE ap.album_id=? ORDER BY p.quality DESC, p.taken_at DESC LIMIT 1""",
              (album_id,))
    db.execute("UPDATE albums SET cover_photo_id=? WHERE id=?",
               (r["photo_id"] if r else None, album_id))


def album_list():
    rows = db.q("""SELECT a.id,a.name,a.created_at,a.cover_photo_id,
                          (SELECT COUNT(*) FROM album_photos ap WHERE ap.album_id=a.id) c
                   FROM albums a ORDER BY a.created_at DESC""")
    return [dict(r) for r in rows]


def album_create(name):
    name = (name or "").strip()
    if not name:
        raise ValueError("相册名不能为空")
    exist = db.q1("SELECT id FROM albums WHERE name=?", (name,))
    if exist:
        raise ValueError("同名相册已存在")
    cur = db.execute("INSERT INTO albums(name,created_at) VALUES(?,?)", (name, int(time.time())))
    return {"id": cur.lastrowid, "name": name}


def album_rename(album_id, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("相册名不能为空")
    if db.q1("SELECT id FROM albums WHERE name=? AND id!=?", (name, album_id)):
        raise ValueError("同名相册已存在")
    db.execute("UPDATE albums SET name=? WHERE id=?", (name, album_id))
    return {"id": album_id, "name": name}


def album_delete(album_id):
    db.execute("DELETE FROM album_photos WHERE album_id=?", (album_id,))
    db.execute("DELETE FROM albums WHERE id=?", (album_id,))
    return {"deleted": album_id}


def album_detail(album_id):
    a = db.q1("SELECT * FROM albums WHERE id=?", (album_id,))
    if not a:
        return None
    items = [dict(r) for r in db.q(
        """SELECT p.* FROM album_photos ap JOIN photos p ON p.id=ap.photo_id
           WHERE ap.album_id=? AND p.hidden=0 ORDER BY p.taken_at DESC""", (album_id,))]
    return {"album": dict(a), "items": items}


def album_add(album_id, ids, log_it=True):
    if not db.q1("SELECT id FROM albums WHERE id=?", (album_id,)):
        raise ValueError("相册不存在")
    n = 0
    con = db.db()
    for pid in list(dict.fromkeys(ids or [])):
        if not con.execute("SELECT 1 FROM photos WHERE id=?", (pid,)).fetchone():
            continue
        cur = con.execute("INSERT OR IGNORE INTO album_photos(album_id,photo_id) VALUES(?,?)",
                          (album_id, pid))
        n += cur.rowcount
    con.commit()
    _refresh_cover(album_id)
    if log_it and n:
        lifecycle.log("album", f"加入相册 {n} 张", {"album_id": album_id, "ids": ids, "action": "add"})
    return {"count": n, "album_id": album_id}


def album_remove(album_id, ids, log_it=True):
    n = 0
    con = db.db()
    for pid in list(dict.fromkeys(ids or [])):
        cur = con.execute("DELETE FROM album_photos WHERE album_id=? AND photo_id=?",
                          (album_id, pid))
        n += cur.rowcount
    con.commit()
    _refresh_cover(album_id)
    if log_it and n:
        lifecycle.log("album", f"移出相册 {n} 张", {"album_id": album_id, "ids": ids, "action": "remove"})
    return {"count": n, "album_id": album_id}


# ------------------------------------------------------------------ 文件夹

def folder_list():
    """按磁盘目录聚合。路径来自索引，照片本体没有被移动或复制。"""
    rows = db.q("""SELECT dir, COUNT(*) c, COALESCE(SUM(size),0) s
                   FROM photos WHERE dir IS NOT NULL AND dir!=''
                   GROUP BY dir ORDER BY dir""")
    return [dict(r) for r in rows]


def folder_tree():
    """把目录列表折成树（只在内存里拼，库仍然是扁平目录字段）。"""
    nodes = {}
    roots = []
    for r in folder_list():
        parts = [p for p in r["dir"].replace("/", "\\").split("\\") if p]
        if not parts:
            continue
        cur = {"name": parts[0], "path": parts[0] + ("\\" if len(parts) > 1 else ""),
               "count": 0, "size": 0, "children": []}
        if cur["name"] not in nodes:
            nodes[cur["name"]] = cur
            roots.append(cur)
        node, acc = nodes[cur["name"]], parts[0] + ("\\" if len(parts) > 1 else "")
        for p in parts[1:]:
            acc = os.path.join(acc, p)
            nxt = next((c for c in node["children"] if c["name"] == p), None)
            if nxt is None:
                nxt = {"name": p, "path": acc, "count": 0, "size": 0, "children": []}
                node["children"].append(nxt)
            node = nxt
        node["count"] += r["c"]
        node["size"] += r["s"]
    def walk(n):
        for c in n["children"]:
            walk(c)
            n["count"] += c["count"]
            n["size"] += c["size"]
        n["children"].sort(key=lambda x: x["name"].lower())
    for r in roots:
        walk(r)
    return roots


def folder_detail(path):
    path = (path or "").rstrip("\\/")
    if not path:
        raise ValueError("缺少文件夹路径")
    items = [dict(r) for r in db.q(
        """SELECT * FROM photos WHERE dir=? ORDER BY taken_at DESC""", (path,))]
    sub = [dict(r) for r in db.q(
        """SELECT dir, COUNT(*) c FROM photos WHERE dir LIKE ? AND dir!=?
           GROUP BY dir ORDER BY dir""", (path + "\\%", path))]
    return {"path": path, "items": items, "children": sub}


# ------------------------------------------------------------------ 重复照片

def duplicates():
    """完全相同内容（快速哈希一致）的组；保留建议按画质、分辨率、体积排序。"""
    groups = db.q("""SELECT hash, COUNT(*) c, SUM(size) s FROM photos
                     WHERE hash IS NOT NULL AND hidden=0 GROUP BY hash HAVING c>1
                     ORDER BY s DESC""")
    out = []
    for g in groups:
        items = [dict(r) for r in db.q(
            """SELECT id,path,name,dir,size,width,height,taken_at,quality,ext
               FROM photos WHERE hash=? ORDER BY quality DESC, size DESC""", (g["hash"],))]
        if len(items) < 2:
            continue
        keep = items[0]
        out.append({"hash": g["hash"], "count": len(items),
                    "bytes": sum(i["size"] or 0 for i in items),
                    "keep": keep["id"], "items": items})
    return out


# ------------------------------------------------------------------ 事件聚合

def events(limit=36):
    """事件 = 同一天 + 同一地点、照片数量足够的一天。

    没有 LLM 也能给出「2025 年 8 月 · 杭州 · 37 张」这种可用的回忆入口。
    """
    days = db.q("""SELECT strftime('%Y-%m-%d', taken_at,'unixepoch','localtime') d,
                          COUNT(*) c, MAX(quality) q
                   FROM photos WHERE taken_at IS NOT NULL AND hidden=0
                   GROUP BY d HAVING c>=5 ORDER BY d DESC LIMIT ?""", (limit,))
    out = []
    for r in days:
        cover = db.q1("""SELECT id FROM photos
                         WHERE strftime('%Y-%m-%d', taken_at,'unixepoch','localtime')=?
                         ORDER BY quality DESC LIMIT 1""", (r["d"],))
        place = db.q1("""SELECT pl.name, COUNT(*) c FROM photos p
                         JOIN photo_places pp ON pp.photo_id=p.id
                         JOIN places pl ON pl.id=pp.place_id
                         WHERE strftime('%Y-%m-%d', p.taken_at,'unixepoch','localtime')=?
                         GROUP BY pl.name ORDER BY c DESC LIMIT 1""", (r["d"],))
        out.append({"date": r["d"], "count": r["c"],
                    "place": place["name"] if place else None,
                    "cover": cover["id"] if cover else None})
    return out


# ------------------------------------------------------------------ 旅行篇（GPS + 日期聚类）

_trip_cache = {"ts": 0.0, "data": []}


def _km(lat1, lon1, lat2, lon2):
    """两点球面距离（公里）。够用就行，不需要高精度。"""
    from math import asin, cos, radians, sin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def _trip_clusters():
    """把「有 GPS、且连着几天都在外面跑」的照片聚成旅行。

    判断一条记录属于同一次旅行需要同时满足：
      · 与上一张相隔不超过 3 天（回家隔了一周再出门就是另一趟）
      · 与这次旅行的活动中心不超过 400 公里（换城市也算同一趟）
    只把 >=8 张、跨 >=2 天的簇算作旅行，避免把日常通勤当成旅行。
    """
    rows = db.q("""SELECT id, taken_at, gps_lat, gps_lon
                   FROM photos WHERE hidden=0 AND kind='photo'
                     AND gps_lat IS NOT NULL AND gps_lon IS NOT NULL
                     AND taken_at IS NOT NULL ORDER BY taken_at""")
    clusters, cur = [], None
    for r in rows:
        t, lat, lon = r["taken_at"], r["gps_lat"], r["gps_lon"]
        same = (cur is not None and t - cur["last"] <= 3 * 86400
                and _km(lat, lon, cur["lat"], cur["lon"]) <= 400)
        if same:
            n = len(cur["ids"])
            cur["lat"] = (cur["lat"] * n + lat) / (n + 1)
            cur["lon"] = (cur["lon"] * n + lon) / (n + 1)
            cur["ids"].append(r["id"])
            cur["last"] = t
            cur["days"].add(time.strftime("%Y-%m-%d", time.localtime(t)))
        else:
            cur = {"start": t, "last": t, "lat": lat, "lon": lon, "ids": [r["id"]],
                   "days": {time.strftime("%Y-%m-%d", time.localtime(t))}}
            clusters.append(cur)
    out = []
    for c in clusters:
        n, days = len(c["ids"]), len(c["days"])
        if n < 8 or days < 2:
            continue
        marks = ",".join("?" * len(c["ids"]))
        picks = [r["id"] for r in db.q(
            f"""SELECT id FROM photos WHERE id IN ({marks})
                ORDER BY is_favorite DESC, quality DESC LIMIT 24""", c["ids"])]
        cover = picks[0] if picks else c["ids"][0]
        a, b = time.localtime(c["start"]), time.localtime(c["last"])
        # Windows 的 strftime 不支持 %-m/%-d，手工拼中文日期
        d0 = f"{a.tm_year}年{a.tm_mon}月{a.tm_mday}日"
        out.append({
            "key": str(c["start"]), "start": c["start"], "end": c["last"],
            "title": d0 if c["start"] == c["last"] else f"{d0} – {b.tm_mon}月{b.tm_mday}日",
            "subtitle": f"{n} 张精选照片 · {days} 天",
            "count": n, "days": days, "cover": cover, "picks": picks[:24],
            "lat": round(c["lat"], 4), "lon": round(c["lon"], 4), "ids": c["ids"],
        })
    out.sort(key=lambda x: -x["start"])
    return out


def trips():
    """旅行篇列表（带 45 秒缓存：侧栏统计与页面共用一次聚类结果）。"""
    now = time.time()
    if now - _trip_cache["ts"] > 45:
        _trip_cache["data"] = _trip_clusters()
        _trip_cache["ts"] = now
    return [{k: v for k, v in t.items() if k != "ids"} for t in _trip_cache["data"]]


def trip_detail(start):
    """按起始时间取某趟旅行的全部照片；先精选、其余按时间。"""
    trips()
    hit = next((t for t in _trip_cache["data"] if str(t["start"]) == str(start)), None)
    if not hit:
        return None
    order = {pid: i for i, pid in enumerate(hit["picks"])}
    items = [dict(r) for r in db.q(
        f"SELECT * FROM photos WHERE id IN ({','.join('?' * len(hit['ids']))})",
        hit["ids"])]
    items.sort(key=lambda it: (order.get(it["id"], 999), -(it["taken_at"] or 0)))
    return {"trip": {k: v for k, v in hit.items() if k != "ids"}, "items": items}
