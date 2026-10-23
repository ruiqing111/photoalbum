"""把编辑结果另存为副本。

铁律：原图一个字节都不动。产物只写 photoalbum_data/edits/，然后当作一次
正常导入交给 scanner.ingest_file —— 缩略图、直方图、索引全部自动补齐。
"""
import os
import re

from . import db, quality, scanner
from .config import EDITS_DIR, THUMB_DIR


def _stem(name):
    """原文件名 → 安全、可读的副本名主体。"""
    s = os.path.splitext(name or "")[0]
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_")
    return (s or "photo")[:60]


def _free_path(stem):
    n = 1
    while True:
        path = os.path.join(EDITS_DIR, f"{stem}_edit{n}.jpg")
        if not os.path.exists(path):
            return path
        n += 1


def save_copy(src_id, data):
    """写入一张编辑后的 JPEG，并登记进相册。返回新照片信息；原照片不存在返回 None。"""
    row = db.q1("SELECT * FROM photos WHERE id=? AND kind='photo'", (src_id,))
    if not row:
        return None
    os.makedirs(EDITS_DIR, exist_ok=True)
    path = _free_path(_stem(row["name"]))
    with open(path, "wb") as f:
        f.write(data)
    out = scanner.ingest_file(path)
    if not out:
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    pid, dup = out
    if dup:
        # 内容与已有照片完全一样（hash 相同）：不重复入库，也不留这个冗余文件
        try:
            os.remove(path)
        except OSError:
            pass
        r0 = db.q1("SELECT name FROM photos WHERE id=?", (pid,))
        return {"id": pid, "name": r0["name"] if r0 else "", "dup": True}
    # 继承拍摄时间与 GPS：副本要和原片排在一起，也落在同一个地点里
    db.execute("""UPDATE photos SET taken_at=?, gps_lat=?, gps_lon=?, gps_alt=?
                  WHERE id=?""",
               (row["taken_at"], row["gps_lat"], row["gps_lon"], row["gps_alt"], pid))
    r = db.q1("SELECT width,height FROM photos WHERE id=?", (pid,))
    q = quality.compute_quality(os.path.join(THUMB_DIR, f"{pid}_s.jpg"),
                                r["width"], r["height"])
    db.execute("UPDATE photos SET quality=? WHERE id=?", (q, pid))
    db.fts_rebuild()          # 新文件名/新标签要能被搜到
    return {"id": pid, "name": os.path.basename(path), "path": path,
            "width": r["width"], "height": r["height"], "quality": q, "dup": False}
