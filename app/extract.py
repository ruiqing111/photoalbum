"""整理到文件夹：把筛选结果按需复制/剪切到目标目录，方便送去修图。

- 目标目录可平铺，也可按拍摄日期 / 月份 / 人物 / 地点 / 事物分类自动建子目录。
- 重名文件自动追加 _1、_2 后缀，不覆盖已有文件。
- 文件多时走后台任务，前端轮询进度。
"""
import os
import re
import shutil
import time

from . import db, search

LAYOUTS = ("flat", "day", "month", "tag", "person", "place")
MODES = ("copy", "move")

# 归类时忽略的结构/参数类标签，避免照片被「横构图」这类标签带偏
_META_TAGS = {
    "视频", "截图", "动图", "相机拍摄", "含位置", "横构图", "竖构图",
    "高分辨率", "高感光", "长焦", "广角", "低饱和", "暖色调", "冷色调",
    "高质量", "模糊", "夜晚拍摄", "黄昏", "连拍", "连拍精选",
}


def _safe(text):
    return re.sub(r'[\\/:*?"<>|]', "_", str(text or "").strip()).strip(". ") or "未分类"


def _folder_for(photo, layout, taken_at):
    """按目录结构返回子目录名；平铺返回空串。"""
    if layout == "day":
        return time.strftime("%Y-%m-%d", time.localtime(taken_at or 0))
    if layout == "month":
        return time.strftime("%Y-%m", time.localtime(taken_at or 0))
    return ""


class ExtractJob:
    """后台整理任务：避免大量文件复制时长时间占用请求。"""

    def __init__(self, dest, rows, mode, layout, prefix, group_of=None):
        self.dest = dest
        self.rows = rows
        self.mode = mode
        self.layout = layout
        self.prefix = prefix or ""
        self.group_of = group_of or {}
        self.total, self.done, self.count = len(rows), 0, 0
        self.skipped, self.status = [], "running"
        self.skipped_detail = []
        # 剪切成功的 (photo_id, 旧路径, 新路径)：跑完要把索引里的旧路径改掉，
        # 否则查看器还指着原位置；同时写进操作日志，Ctrl+Z 能把整批移回去。
        self.relocated = []

    def to_dict(self):
        return {"status": self.status, "total": self.total, "done": self.done,
                "count": self.count, "skipped": len(self.skipped),
                "skipped_detail": self.skipped_detail[:30],
                "moved": len(self.relocated),
                "dir": self.dest, "mode": self.mode}


def run(job):
    os.makedirs(job.dest, exist_ok=True)
    used = set()
    for r in job.rows:
        job.done += 1
        src = r["path"]
        if not src or not os.path.exists(src):
            job.skipped.append(r["name"])
            job.skipped_detail.append({"name": r["name"], "reason": "源文件不存在或已被移动"})
            continue
        if job.mode == "move" and os.path.dirname(os.path.abspath(src)) == job.dest:
            job.skipped.append(r["name"])
            job.skipped_detail.append({"name": r["name"], "reason": "已经在这个文件夹里"})
            continue
        base, ext = os.path.splitext(r["name"])
        stem = job.prefix + base
        if job.layout in ("tag", "person", "place"):
            sub = job.group_of.get(r["id"], "未分类")
        else:
            sub = _folder_for(r, job.layout, r["taken_at"])
        folder = os.path.join(job.dest, sub) if sub else job.dest
        if sub:
            os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, stem + ext)
        key = dst.lower()
        n = 1
        while key in used or os.path.exists(dst):
            dst = os.path.join(folder, f"{stem}_{n}{ext}")
            key = dst.lower(); n += 1
        used.add(key)
        try:
            if job.mode == "move":
                shutil.move(src, dst)
            else:
                shutil.copy2(src, dst)
        except Exception as e:
            job.skipped.append(r["name"])
            job.skipped_detail.append({"name": r["name"], "reason": f"写入失败：{e}"})
            continue
        if job.mode == "move":
            job.relocated.append((r["id"], src, dst))
        job.count += 1
    if job.relocated:
        _relocate(job.relocated)
    job.status = "done"
    return job


def _relocate(pairs):
    """剪切完成后把索引路径改到新位置：照片继续留在相册里，查看器也不会指向旧路径。"""
    n = 0
    ok_pairs = []
    for pid, old, path in pairs:
        try:
            db.execute("""UPDATE photos SET path=?, name=?, dir=?, ext=?, mtime=?
                          WHERE id=?""",
                       (path, os.path.basename(path), os.path.dirname(path),
                        os.path.splitext(path)[1].lower(), int(os.path.getmtime(path)), pid))
            ok_pairs.append([pid, old, path])
            n += 1
        except Exception:
            # 目标路径在索引里已被另一条记录占用时保持原状，别把整批回滚
            continue
    if n:
        db.fts_rebuild()
        try:
            from . import lifecycle
            lifecycle.log("move", f"移动 {n} 张照片到新文件夹", {"pairs": ok_pairs})
        except Exception:
            pass
    return n


def prepare(dest, ids=None, mode="copy", layout="flat", prefix=None, **filters):
    """校验参数、取出行、装配后台任务。"""
    if not dest or not dest.strip():
        raise ValueError("请填写目标文件夹")
    mode = mode if mode in MODES else "copy"
    layout = layout if layout in LAYOUTS else "flat"
    rows = search.collect_rows(ids=ids, **filters)
    if not rows:
        raise ValueError("当前筛选没有匹配到照片")
    group_of = {}
    if layout in ("tag", "person", "place") and rows:
        ids = [r["id"] for r in rows]
        marks = ",".join("?" * len(ids))
        if layout == "tag":
            for r in db.q(f"SELECT photo_id, tag FROM tags WHERE photo_id IN ({marks}) ORDER BY tag", ids):
                if r["tag"] not in _META_TAGS:
                    group_of.setdefault(r["photo_id"], _safe(r["tag"]))
        elif layout == "person":
            for r in db.q(f"""SELECT pp.photo_id, pe.name FROM person_photos pp
                              JOIN people pe ON pe.id=pp.person_id
                              WHERE pp.photo_id IN ({marks})
                              ORDER BY pp.dist, pe.id""", ids):
                group_of.setdefault(r["photo_id"], _safe(r["name"]))
        else:
            for r in db.q(f"""SELECT pp.photo_id, pl.name FROM photo_places pp
                              JOIN places pl ON pl.id=pp.place_id
                              WHERE pp.photo_id IN ({marks})""", ids):
                group_of.setdefault(r["photo_id"], _safe(r["name"]))
    dest = os.path.abspath(os.path.expanduser(dest.strip()))
    return ExtractJob(dest, rows, mode, layout, prefix, group_of)
