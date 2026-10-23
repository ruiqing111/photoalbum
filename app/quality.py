"""画质评估与精选（连拍堆叠 + 每组挑最佳）。纯 Pillow 实现，无重依赖。"""
import os
import time

from PIL import Image, ImageFilter, ImageStat

from . import db
from .config import THUMB_DIR


def _source(pid, path):
    """优先吃 320px 缩略图：清晰度/曝光都在小图上评估，1.4ms/张（原图要 92ms）。"""
    s = os.path.join(THUMB_DIR, f"{pid}_s.jpg")
    return s if os.path.exists(s) else path


def _gray(path, side):
    """统一走 draft 解码：JPEG 可以按 1/8 直接解出小图，省一个数量级的解码量。
    其它格式会自动忽略 draft，行为不变。"""
    img = Image.open(path)
    img.draft("L", (side, side))
    return img.convert("L")


def compute_quality(path, width, height):
    """清晰度 + 曝光 + 分辨率。

    清晰度用 Laplacian 方差：它只看二阶导数的能量，对「失焦」敏感，
    而旧的 FIND_EDGES 均值会把本身纹理多的画面（树叶、草地、书架）误判成清晰。
    拉普拉斯方差随场景复杂度增长得比边缘均值慢，所以配一条 0-100 的软上限。
    """
    s, e = 0.0, 50.0
    try:
        g = _gray(path, 256)
        small = g.copy()
        small.thumbnail((256, 256))
        s = _sharpness(small)
        tiny = g.copy()
        tiny.thumbnail((128, 128))
        m = ImageStat.Stat(tiny).mean[0]
        e = 20.0 if (m < 35 or m > 225) else max(0.0, 100.0 - abs(m - 120) * 0.8)
    except Exception:                      # 打不开就当没清晰度、曝光中性
        pass
    res = min(100.0, ((width or 0) * (height or 0)) / 12_000_000 * 100)
    return round(0.55 * s + 0.25 * e + 0.20 * res, 1)


def _sharpness(img):
    """Laplacian 方差 → 0~100。

    经验区间：明显糊片 < 40，正常手机照 80~400，锐利的静物能到 800+。
    用 sqrt 压缩动态范围，让「有点糊」和「很糊」之间的差距更可辨。
    """
    try:
        import cv2
        import numpy as np
        a = np.asarray(img, dtype=np.uint8)
        v = float(cv2.Laplacian(a, cv2.CV_64F).var())
        return min(100.0, (v ** 0.5) * 5.0)
    except Exception:
        return min(100.0, ImageStat.Stat(img.filter(ImageFilter.FIND_EDGES)).mean[0] * 6)


# 画质算法版本：换算法就 +1，启动后第一次分析会把全库重算一遍。
Q_VERSION = "2"


def score_all(limit=None, progress=None):
    # 算法换过就整库重算，否则老分数会一直沿用旧标准（新旧分数混在一起没法排序）
    ver = db.q1("SELECT v FROM meta WHERE k='quality_version'")
    if not ver or ver["v"] != Q_VERSION:
        db.execute("UPDATE photos SET quality=0")
    rows = db.q("SELECT id,path,width,height FROM photos WHERE kind='photo' AND junk=0 AND quality=0")
    n = len(rows)
    hit = 0
    buf = []
    for i, r in enumerate(rows):
        q = compute_quality(_source(r["id"], r["path"]), r["width"], r["height"])
        buf.append((q, r["id"]))
        hit += 1
        # 批量提交：逐张 commit 每次 0.286ms，攒 200 张一次只要 0.0013ms/张
        if len(buf) >= 200:
            db.executemany("UPDATE photos SET quality=? WHERE id=?", buf)
            buf = []
        if progress:
            progress(i + 1, n)
        if limit and hit >= limit:
            break
    if buf:
        db.executemany("UPDATE photos SET quality=? WHERE id=?", buf)
    db.execute("INSERT OR REPLACE INTO meta VALUES('quality_version', ?)", (Q_VERSION,))
    return hit


def group_bursts(gap=3, progress=None):
    """同一相机 3 秒内连拍归为一组，质量最高者为精选代表。"""
    rows = db.q("""SELECT id,path,width,height,taken_at,camera_model,quality FROM photos
                   WHERE kind='photo' AND junk=0 ORDER BY camera_model, taken_at""")
    db.execute("DELETE FROM bursts")
    groups, cur, last_key = [], [], None
    for r in rows:
        key = (r["camera_model"], (r["taken_at"] or 0) // gap)
        if key != last_key and cur:
            groups.append(cur)
            cur = []
        cur.append(r)
        last_key = key
    if cur:
        groups.append(cur)
    multi = [g for g in groups if len(g) >= 2]
    n_groups = 0
    buf = []
    for i, g in enumerate(multi):
        gid = f"b{g[0]['taken_at']}_{g[0]['id']}"
        best = max(g, key=lambda r: r["quality"])
        for r in g:
            buf.append((gid, r["id"], 1 if r["id"] == best["id"] else 0))
        n_groups += 1
        if len(buf) >= 1000:
            db.executemany("INSERT OR REPLACE INTO bursts VALUES(?,?,?)", buf)
            buf = []
        if progress:
            progress(i + 1, len(multi))
    if buf:
        db.executemany("INSERT OR REPLACE INTO bursts VALUES(?,?,?)", buf)
    return n_groups
