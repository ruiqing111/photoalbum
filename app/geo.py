"""地点维度：离线城市库 + GPS 聚合。无需联网即可把坐标转成城市名。

策略：
1) 距内置城市库最近的城市 < 150km → 归入该城市；
2) 否则按 1° 网格归组，命名为 "31.2°N 121.5°E"。
"""
import math
import time

from . import db

# (名称, 纬度, 经度) —— 常用国内城市 + 主要海外城市，覆盖绝大多数出行场景
CITIES = [
    ("北京", 39.9042, 116.4074), ("上海", 31.2304, 121.4737), ("广州", 23.1291, 113.2644),
    ("深圳", 22.5431, 114.0579), ("杭州", 30.2741, 120.1551), ("南京", 32.0603, 118.7969),
    ("苏州", 31.2989, 120.5853), ("成都", 30.5728, 104.0668), ("重庆", 29.5630, 106.5516),
    ("武汉", 30.5928, 114.3055), ("西安", 34.3416, 108.9398), ("天津", 39.3434, 117.3616),
    ("青岛", 36.0671, 120.3826), ("厦门", 24.4798, 118.0894), ("长沙", 28.2282, 112.9388),
    ("郑州", 34.7466, 113.6254), ("济南", 36.6512, 117.1201), ("沈阳", 41.8057, 123.4315),
    ("哈尔滨", 45.8038, 126.5350), ("大连", 38.9140, 121.6147), ("昆明", 24.8801, 102.8329),
    ("贵阳", 26.6470, 106.6302), ("南宁", 22.8170, 108.3665), ("福州", 26.0745, 119.2965),
    ("合肥", 31.8206, 117.2272), ("南昌", 28.6820, 115.8579), ("太原", 37.8706, 112.5489),
    ("石家庄", 38.0428, 114.5149), ("兰州", 36.0611, 103.8343), ("乌鲁木齐", 43.8256, 87.6168),
    ("呼和浩特", 40.8424, 111.7490), ("银川", 38.4872, 106.2309), ("西宁", 36.6171, 101.7782),
    ("拉萨", 29.6520, 91.1721), ("海口", 20.0440, 110.1990), ("三亚", 18.2528, 109.5119),
    ("香港", 22.3193, 114.1694), ("澳门", 22.1987, 113.5439), ("台北", 25.0330, 121.5654),
    ("东京", 35.6762, 139.6503), ("大阪", 34.6937, 135.5023), ("首尔", 37.5665, 126.9780),
    ("曼谷", 13.7563, 100.5018), ("新加坡", 1.3521, 103.8198), ("吉隆坡", 3.1390, 101.6869),
    ("巴厘岛", -8.4095, 115.1889), ("巴黎", 48.8566, 2.3522), ("伦敦", 51.5074, -0.1278),
    ("罗马", 41.9028, 12.4964), ("巴塞罗那", 41.3874, 2.1686), ("纽约", 40.7128, -74.0060),
    ("洛杉矶", 34.0522, -118.2437), ("旧金山", 37.7749, -122.4194), ("悉尼", -33.8688, 151.2093),
    ("墨尔本", -37.8136, 144.9631), ("奥克兰", -36.8485, 174.7633), ("迪拜", 25.2048, 55.2708),
    ("伊斯坦布尔", 41.0082, 28.9784), ("苏黎世", 47.3769, 8.5417), ("米兰", 45.4642, 9.1900),
]

MAX_KM = 150.0


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_city(lat, lon):
    best, bd = None, 1e9
    for name, clat, clon in CITIES:
        d = haversine(lat, lon, clat, clon)
        if d < bd:
            best, bd = (name, clat, clon), d
    if bd <= MAX_KM:
        return best[0], best[1], best[2], bd, "city"
    return f"{lat:.1f}°N {lon:.1f}°E", lat, lon, bd, "grid"


def rebuild(progress=None):
    """按 GPS 重建地点分组。写入 places / photo_places。"""
    db.execute("DELETE FROM places")
    db.execute("DELETE FROM photo_places")
    rows = db.q("""SELECT id, gps_lat, gps_lon, quality FROM photos
                   WHERE gps_lat IS NOT NULL AND gps_lon IS NOT NULL""")
    buckets = {}
    for i, r in enumerate(rows):
        name, clat, clon, dist, kind = nearest_city(r["gps_lat"], r["gps_lon"])
        b = buckets.setdefault(name, {"lat": clat, "lon": clon, "kind": kind,
                                      "ids": [], "best_q": -1, "cover": None})
        b["ids"].append((r["id"], dist))
        if (r["quality"] or 0) > b["best_q"]:
            b["best_q"], b["cover"] = r["quality"] or 0, r["id"]
        if progress:
            progress(i + 1, len(rows))
    now = int(time.time())
    for name, b in buckets.items():
        cur = db.execute(
            "INSERT INTO places(name,lat,lon,cover_photo_id,photo_count,kind) VALUES(?,?,?,?,?,?)",
            (name, b["lat"], b["lon"], b["cover"], len(b["ids"]), b["kind"]))
        pid = cur.lastrowid
        db.executemany("INSERT OR REPLACE INTO photo_places VALUES(?,?,?)",
                       [(photo_id, pid, d) for photo_id, d in b["ids"]])
    return len(buckets)


def place_list():
    return [dict(r) for r in db.q(
        "SELECT * FROM places ORDER BY photo_count DESC, name")]


def place_photos(place_id):
    rows = db.q("""SELECT p.*, pp.distance_km FROM photo_places pp
                   JOIN photos p ON p.id=pp.photo_id
                   WHERE pp.place_id=? ORDER BY p.taken_at DESC""", (place_id,))
    return [dict(r) for r in rows]
