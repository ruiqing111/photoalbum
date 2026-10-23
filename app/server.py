"""FastAPI 服务：REST API + 前端静态页。"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (ai, analyze, db, editor, exporter, extract, geo, library, lifecycle,
               people, quality, scanner, search)
from .config import THUMB_DIR, WEB_DIR

db.init()
app = FastAPI(title="Local AI Photo Album")
_jobs = {}


def _warm_worker():
    """启动后在后台补直方图与 m 缩略图。

    老库第一次升级要跑一两分钟；跑完之后查看器切图只取缓存文件，
    不再现场解原图。失败不影响任何功能，下次启动会接着补。
    顺手清掉超过 30 天的回收站条目，并保证每周至少有一份索引快照。
    """
    try:
        scanner.mark_junk()
    except Exception:
        pass
    try:
        scanner.warm_thumbs()
    except Exception:
        pass
    try:
        lifecycle.purge_stale()
        last = lifecycle.backups()
        if not last or time.time() - last[0]["time"] > 7 * 86400:
            lifecycle.backup_now()
    except Exception:
        pass


threading.Thread(target=_warm_worker, daemon=True, name="warm-thumbs").start()


class ScanReq(BaseModel):
    dirs: list[str]


class IdsReq(BaseModel):
    ids: list[int] = []
    name: str | None = None


class NameReq(BaseModel):
    name: str


class MergeReq(BaseModel):
    src: int
    dst: int


class AssignReq(BaseModel):
    photo_id: int
    person_id: int


class DeleteReq(BaseModel):
    # remove=只摘索引；trash=移入回收站（默认）；purge=彻底删原文件
    mode: str = "trash"


class BatchDeleteReq(BaseModel):
    ids: list[int] = []
    mode: str = "trash"          # remove | trash | purge


class BatchIdsReq(BaseModel):
    ids: list[int] = []


class ShareReq(BaseModel):
    ids: list[int] = []
    dir: str = ""


class BatchFavReq(BaseModel):
    ids: list[int] = []
    value: bool = True


class BatchHideReq(BaseModel):
    ids: list[int] = []
    value: bool = True


class AlbumReq(BaseModel):
    name: str


class AlbumIdsReq(BaseModel):
    ids: list[int] = []


class RenameReq(BaseModel):
    ids: list[int] = []
    template: str = "{date}_{seq}"
    start: int = 1


class TagReq(BaseModel):
    ids: list[int] = []
    tag: str
    action: str = "add"          # add | remove


class UndoReq(BaseModel):
    id: int | None = None


class AnalyzeReq(BaseModel):
    # 强制重算人物特征（忽略 person_feats 缓存）
    force: bool = False


class ExtractReq(BaseModel):
    dir: str
    ids: list[int] = []
    mode: str = "copy"          # copy | move
    layout: str = "flat"        # flat | day | month | tag
    prefix: str | None = None
    q: str | None = None
    tag: str | None = None
    kind: str | None = None
    favorite: int | None = None
    person_id: int | None = None
    place_id: int | None = None
    month: str | None = None
    dir: str | None = None
    min_quality: float | None = None
    camera: str | None = None
    junk: int | None = None


def _month_range(month):
    y, m = map(int, month.split("-"))
    start = time.mktime(time.strptime(month, "%Y-%m"))
    end = time.mktime((y + (m == 12), m % 12 + 1, 1, 0, 0, 0, 0, 0, -1))
    return start, end


# 系统文件夹选择框：放进独立子进程，避免 tkinter 与服务器线程互相干扰
_PICKER_SCRIPT = (
    "import sys, tkinter as tk\n"
    "from tkinter import filedialog\n"
    "root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)\n"
    "p = filedialog.askdirectory(title=sys.argv[1])\n"
    "root.destroy()\n"
    "open(sys.argv[2], 'w', encoding='utf-8').write(p or '')\n"
)
_pick_lock = threading.Lock()


def pick_folder(title):
    """弹出本机文件夹选择框，返回绝对路径；取消或不可用则返回 None。"""
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        with _pick_lock:
            r = subprocess.run([sys.executable, "-c", _PICKER_SCRIPT, title, tmp],
                               capture_output=True, timeout=600)
        if r.returncode != 0:
            return None
        with open(tmp, encoding="utf-8") as f:
            return f.read().strip() or None
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@app.get("/api/pick-folder")
def api_pick_folder(title: str = "选择文件夹"):
    path = pick_folder(title)
    return {"ok": bool(path), "path": path}


@app.post("/api/analyze")
def api_analyze(req: AnalyzeReq | None = None):
    """一键全量分析：打标 → 评分 → 连拍精选 → 人物分组 → 地点聚合。

    上千张要跑十几分钟，所以放到后台线程，前端轮询 /api/analyze/status 看进度。
    """
    job = _jobs.get("analyze")
    if job and job.status == "running":
        raise HTTPException(409, "分析正在进行中")
    job = analyze.AnalyzeJob()
    _jobs["analyze"] = job
    force = bool(req and req.force)
    threading.Thread(target=analyze.run_analyze, args=(job, force), daemon=True).start()
    return {"started": True}


@app.get("/api/analyze/status")
def api_analyze_status():
    job = _jobs.get("analyze")
    return job.to_dict() if job else {"status": "idle"}


@app.post("/api/analyze/cancel")
def api_analyze_cancel():
    job = _jobs.get("analyze")
    if job and job.status == "running":
        job.status = "cancelled"
    return {"cancelled": True}


@app.get("/api/overview")
def api_overview():
    return search.overview()


@app.get("/api/memories")
def api_memories():
    return search.memories()


@app.get("/api/things")
def api_things():
    return search.things()


@app.get("/api/people")
def api_people():
    return people.people_list()


@app.get("/api/people/{pid}")
def api_person(pid: int):
    r = db.q1("SELECT * FROM people WHERE id=?", (pid,))
    if not r:
        raise HTTPException(404, "not found")
    return {"person": dict(r), "items": people.person_photos(pid)}


@app.post("/api/people/{pid}/name")
def api_person_rename(pid: int, req: NameReq):
    return people.rename(pid, req.name)


@app.post("/api/people/merge")
def api_person_merge(req: MergeReq):
    return people.merge(req.src, req.dst)


@app.post("/api/people/assign")
def api_person_assign(req: AssignReq):
    """把照片手动归到某个人物组——自动聚类漏掉时的纠错出口。"""
    return people.assign(req.photo_id, req.person_id)


@app.post("/api/people/{pid}/detach")
def api_person_detach(pid: int, req: AssignReq):
    return people.detach(req.photo_id, pid)


@app.get("/api/places")
def api_places():
    return geo.place_list()


@app.get("/api/places/{pid}")
def api_place(pid: int):
    r = db.q1("SELECT * FROM places WHERE id=?", (pid,))
    if not r:
        raise HTTPException(404, "not found")
    items = geo.place_photos(pid)
    search._attach(items)
    return {"place": dict(r), "items": items}


@app.get("/api/stats")
def api_stats():
    return search.stats()


@app.get("/api/ai/status")
def api_ai_status():
    return ai.ai_status()


@app.post("/api/scan")
def api_scan(req: ScanReq):
    dirs = [d for d in req.dirs if os.path.isdir(d)]
    if not dirs:
        raise HTTPException(400, "没有有效目录")
    old = _jobs.get("scan")
    if old and old.status == "running":
        # 两路导入同时解原图、写缩略图，移动硬盘会被拖到掉线；
        # 想换目录就先把当前这次停掉（已导入的照片都还在）
        raise HTTPException(409, "上一次导入还没结束，先点「停止」再换目录")
    job = scanner.ScanJob(dirs)
    _jobs["scan"] = job
    threading.Thread(target=scanner.run_scan, args=(job,), daemon=True).start()
    return {"started": True, "dirs": dirs}


@app.get("/api/scan/status")
def api_scan_status():
    job = _jobs.get("scan")
    return job.to_dict() if job else {"status": "idle"}


@app.post("/api/scan/stop")
def api_scan_stop():
    """停止导入：已经入库的照片全部保留，随时可以接着用。"""
    job = _jobs.get("scan")
    if not job or job.status != "running":
        return {"stopping": False}
    job.status = "cancelled"
    return {"stopping": True}


@app.post("/api/tag")
def api_tag():
    return {"tagged": ai.tag_all()}


@app.post("/api/embed")
def api_embed():
    return {"embedded": ai.embed_all(), "ai": ai.ai_status()}


@app.post("/api/score")
def api_score():
    return {"scored": quality.score_all()}


@app.post("/api/curate")
def api_curate():
    return {"groups": quality.group_bursts()}


@app.get("/api/curated")
def api_curated(reason: str | None = None):
    return search.curated(reason)


@app.get("/api/photos")
def api_photos(q: str | None = None, tag: str | None = None,
               date_from: float | None = None, date_to: float | None = None,
               camera: str | None = None, min_quality: float | None = None,
               favorite: int | None = None, kind: str | None = None,
               person_id: int | None = None, place_id: int | None = None,
               month: str | None = None, dir: str | None = None, hidden: int = 0,
               junk: int = 0,
               sort: str = "taken_desc", page: int = 1, page_size: int = 80):
    if month:
        date_from, date_to = _month_range(month)
    return search.search_photos(q=q, tag=tag, date_from=date_from, date_to=date_to,
                                camera=camera, min_quality=min_quality, favorite=favorite,
                                kind=kind, person_id=person_id, place_id=place_id,
                                dir=dir, hidden=hidden, junk=junk, sort=sort, page=page,
                                page_size=page_size)


@app.get("/api/photos/ids")
def api_photo_ids(q: str | None = None, tag: str | None = None,
                  date_from: float | None = None, date_to: float | None = None,
                  camera: str | None = None, min_quality: float | None = None,
                  favorite: int | None = None, kind: str | None = None,
                  person_id: int | None = None, place_id: int | None = None,
                  month: str | None = None, dir: str | None = None, hidden: int = 0,
                  junk: int = 0):
    """当前筛选下的全部 id（不分页）：前端「全选」用，避免只选到已加载的那几屏。"""
    if month:
        date_from, date_to = _month_range(month)
    return {"ids": search.all_ids(q=q, tag=tag, date_from=date_from, date_to=date_to,
                                  camera=camera, min_quality=min_quality, favorite=favorite,
                                  kind=kind, person_id=person_id, place_id=place_id,
                                  dir=dir, hidden=hidden, junk=junk)}


@app.get("/api/timeline")
def api_timeline():
    return search.timeline()


@app.get("/api/tags")
def api_tags():
    return search.tag_counts()


@app.get("/api/photo/{pid}")
def api_photo(pid: int):
    r = db.q1("SELECT * FROM photos WHERE id=?", (pid,))
    if not r:
        raise HTTPException(404, "not found")
    d = dict(r)
    d["tags"] = [dict(t) for t in db.q("SELECT tag,source,confidence FROM tags WHERE photo_id=?", (pid,))]
    # people 给的是名字（列表页与信息面板共用同一份结构），people_groups 带 id 供纠错操作
    groups = [dict(r) for r in db.q(
        """SELECT p.id, p.name, p.kind FROM person_photos pp JOIN people p ON p.id=pp.person_id
           WHERE pp.photo_id=? ORDER BY (p.kind='group'), p.photo_count DESC""", (pid,))]
    d["people_groups"] = groups
    d["people"] = [g["name"] for g in groups]
    burst = db.q1("SELECT group_id,is_pick FROM bursts WHERE photo_id=?", (pid,))
    d["burst"] = dict(burst) if burst else None
    # 直方图与平均色在导入（或首次打开）时算好存库，这里只做一次 JSON 解析，
    # 不再打开缩略图跑 PIL —— 那是切图 120ms 的大头
    hist, avg = d.pop("hist", None), d.pop("avg_rgb", None)
    if not hist:
        s_path = os.path.join(THUMB_DIR, f"{pid}_s.jpg")
        if not os.path.exists(s_path):
            s_path = scanner.make_thumb(pid, d["path"], "s")
        if s_path:
            hist, avg = scanner.thumb_stats(s_path)
            if hist:
                db.execute("UPDATE photos SET hist=?, avg_rgb=? WHERE id=?", (hist, avg, pid))
    try:
        d["histogram"] = json.loads(hist) if hist else None
        d["avg_color"] = json.loads(avg) if avg else None
    except ValueError:
        d["histogram"] = d["avg_color"] = None
    return d


@app.post("/api/photo/{pid}/favorite")
def api_fav(pid: int):
    r = db.q1("SELECT is_favorite f FROM photos WHERE id=?", (pid,))
    if not r:
        raise HTTPException(404)
    db.execute("UPDATE photos SET is_favorite=? WHERE id=?", (0 if r["f"] else 1, pid))
    return {"favorite": 0 if r["f"] else 1}


@app.post("/api/photo/{pid}/rotate")
def api_rotate(pid: int, angle: int = 90):
    """视频旋转：只写索引里的角度，原文件不动。

    真正的转码需要 ffmpeg，这里先做到「看的时候是正的、封面也跟着转」，
    随时可以再转回来；用户要的是能在 app 里把竖拍视频调正，不是改坏原片。
    """
    if angle not in (90, -90, 270):
        raise HTTPException(400, "只支持 ±90 度")
    r = db.q1("SELECT kind, rotate, path FROM photos WHERE id=?", (pid,))
    if not r:
        raise HTTPException(404)
    if r["kind"] != "video":
        raise HTTPException(400, "图片请在编辑器里旋转")
    ang = ((r["rotate"] or 0) + angle) % 360
    db.execute("UPDATE photos SET rotate=? WHERE id=?", (ang, pid))
    for k in ("s", "m"):
        p = os.path.join(THUMB_DIR, f"{pid}_{k}.jpg")
        try:
            os.remove(p)
        except OSError:
            pass
    scanner.make_video_thumbs(pid, r["path"], ang)
    return {"rotate": ang}


@app.post("/api/photo/{pid}/delete")
def api_delete(pid: int, req: DeleteReq | None = None):
    """删除单张：默认移入最近删除，可恢复；mode=remove 只摘索引；purge 才真删文件。"""
    mode = (req.mode if req else "trash") or "trash"
    if mode not in ("remove", "trash", "purge"):
        raise HTTPException(400, "未知的删除方式")
    out = lifecycle.batch([pid], mode)
    if not out["count"] and out["failed"]:
        raise HTTPException(404, out["failed"][0]["msg"])
    return {"id": pid, "mode": mode, **out}


@app.post("/api/photos/batch/delete")
def api_batch_delete(req: BatchDeleteReq):
    """批量删除：默认进回收站；彻底删除必须显式传 mode=purge。"""
    ids = list(dict.fromkeys(req.ids))
    if not ids:
        raise HTTPException(400, "没有选中照片")
    out = lifecycle.batch(ids, req.mode)
    if out["count"]:
        db.fts_rebuild()
    return out


@app.get("/api/trash")
def api_trash():
    return {"items": lifecycle.trash_list(), "days": lifecycle.TRASH_DAYS}


@app.post("/api/trash/{tid}/restore")
def api_trash_restore(tid: int):
    if not lifecycle.restore(tid):
        raise HTTPException(400, "恢复失败：原文件或原位置不可用")
    return {"restored": tid}


@app.post("/api/trash/empty")
def api_trash_empty():
    return lifecycle.empty_trash()


@app.post("/api/trash/{tid}/purge")
def api_trash_purge(tid: int):
    r = db.q1("SELECT photo_id FROM trash WHERE id=?", (tid,))
    if not r:
        raise HTTPException(404)
    return lifecycle.purge(r["photo_id"])


@app.get("/api/ops")
def api_ops(limit: int = 20):
    return {"items": lifecycle.recent_ops(limit)}


@app.post("/api/ops/undo")
def api_ops_undo(req: UndoReq | None = None):
    return lifecycle.undo(req.id if req else None)


@app.get("/api/albums")
def api_albums():
    return library.album_list()


@app.post("/api/albums")
def api_album_create(req: AlbumReq):
    try:
        return library.album_create(req.name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/albums/{aid}")
def api_album(aid: int):
    d = library.album_detail(aid)
    if not d:
        raise HTTPException(404, "相册不存在")
    search._attach(d["items"])
    return d


@app.post("/api/albums/{aid}/rename")
def api_album_rename(aid: int, req: AlbumReq):
    try:
        return library.album_rename(aid, req.name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/albums/{aid}")
def api_album_delete(aid: int):
    return library.album_delete(aid)


@app.post("/api/albums/{aid}/add")
def api_album_add(aid: int, req: AlbumIdsReq):
    try:
        return library.album_add(aid, req.ids)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/albums/{aid}/remove")
def api_album_remove(aid: int, req: AlbumIdsReq):
    try:
        return library.album_remove(aid, req.ids)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/folders")
def api_folders(tree: int = 0):
    return library.folder_tree() if tree else library.folder_list()


@app.get("/api/folder")
def api_folder(path: str):
    try:
        return library.folder_detail(path)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/duplicates")
def api_duplicates():
    return library.duplicates()


@app.get("/api/events")
def api_events(limit: int = 36):
    return library.events(limit)


@app.get("/api/trips")
def api_trips():
    return library.trips()


@app.get("/api/trips/{start}")
def api_trip(start: str):
    d = library.trip_detail(start)
    if not d:
        raise HTTPException(404, "这趟旅行已经不在了")
    search._attach(d["items"])
    return d


@app.post("/api/photos/batch/rename")
def api_batch_rename(req: RenameReq):
    if not req.ids:
        raise HTTPException(400, "没有选中照片")
    try:
        return lifecycle.batch_rename(req.ids, req.template, req.start)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/photos/batch/tag")
def api_batch_tag(req: TagReq):
    if not req.ids:
        raise HTTPException(400, "没有选中照片")
    try:
        return lifecycle.batch_tag(req.ids, req.tag, req.action)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/maintenance")
def api_maintenance():
    return {"check": lifecycle.self_check(), "backups": lifecycle.backups()}


@app.post("/api/maintenance/backup")
def api_maintenance_backup():
    return lifecycle.backup_now()


@app.post("/api/photos/batch/hide")
def api_batch_hide(req: BatchHideReq):
    """隐藏 / 取消隐藏：只改显示标记，原文件与索引都保留。"""
    ids = list(dict.fromkeys(req.ids))
    if not ids:
        raise HTTPException(400, "没有选中照片")
    marks = ",".join("?" * len(ids))
    val = 1 if req.value else 0
    db.execute(f"UPDATE photos SET hidden=? WHERE id IN ({marks})", [val] + ids)
    lifecycle.log("hide", f"{'隐藏' if val else '取消隐藏'} {len(ids)} 张",
                  {"ids": ids, "value": val})
    return {"count": len(ids), "value": val}


@app.post("/api/photos/batch/junk")
def api_batch_junk(req: BatchHideReq):
    """把照片标成「非照片」（缓存缩略图/网页小图），或恢复成照片。

    只改索引标记，原文件、缩略图都不动。恢复时写 junk_fix=1，
    自动识别以后不会再把它扫回「非照片」。
    """
    ids = list(dict.fromkeys(req.ids))
    if not ids:
        raise HTTPException(400, "没有选中照片")
    marks = ",".join("?" * len(ids))
    if req.value:
        db.execute(f"UPDATE photos SET junk=1, junk_fix=0 WHERE id IN ({marks})", ids)
        lifecycle.log("junk", f"标记为非照片 {len(ids)} 张", {"ids": ids})
    else:
        db.execute(f"UPDATE photos SET junk=0, junk_fix=1 WHERE id IN ({marks})", ids)
        lifecycle.log("junk", f"恢复为照片 {len(ids)} 张", {"ids": ids})
    return {"count": len(ids), "value": 1 if req.value else 0}


@app.post("/api/junk/rescan")
def api_junk_rescan():
    """重新识别一遍缓存缩略图；已手动确认过的照片（junk_fix=1）不会被动。"""
    n = scanner.mark_junk()
    total = db.q1("SELECT COUNT(*) c FROM photos WHERE junk=1")["c"]
    return {"marked": n, "total": total}


@app.post("/api/photos/batch/favorite")
def api_batch_favorite(req: BatchFavReq):
    """批量收藏 / 取消收藏。"""
    ids = list(dict.fromkeys(req.ids))
    if not ids:
        raise HTTPException(400, "没有选中照片")
    marks = ",".join("?" * len(ids))
    val = 1 if req.value else 0
    db.execute(f"UPDATE photos SET is_favorite=? WHERE id IN ({marks})", [val] + ids)
    n = db.q1(f"SELECT COUNT(*) c FROM photos WHERE is_favorite=? AND id IN ({marks})",
              [val] + ids)["c"]
    return {"count": n, "value": val}


@app.post("/api/photo/{pid}/rating/{rating}")
def api_rate(pid: int, rating: int):
    db.execute("UPDATE photos SET rating=? WHERE id=?", (max(0, min(5, rating)), pid))
    return {"rating": rating}


@app.post("/api/photo/{pid}/edit-copy")
async def api_edit_copy(pid: int, request: Request):
    """保存编辑结果：前端 canvas 导出的 JPEG 原样上传，落盘后当新照片入库。

    原图只被读取、从不写回；副本写进 photoalbum_data/edits/。
    """
    data = await request.body()
    if not data:
        raise HTTPException(400, "没有收到图片数据")
    if len(data) > 80 * 1024 * 1024:
        raise HTTPException(400, "图片太大（上限 80MB）")
    if data[:3] != b"\xff\xd8\xff":
        raise HTTPException(400, "只接受 JPEG 数据")
    try:
        res = editor.save_copy(pid, data)
    except Exception as e:
        raise HTTPException(500, f"保存失败：{e}")
    if not res:
        raise HTTPException(404, "原照片不在相册里")
    return res


@app.get("/api/edit-source/{pid}")
def api_edit_source(pid: int):
    """给浏览器自己解不了的格式（HEIC / TIFF 等）转一份 JPEG 供编辑用。

    正常 JPEG/PNG 前端直接读 /api/image，只有解码失败才落到这里。
    """
    r = db.q1("SELECT path,kind FROM photos WHERE id=?", (pid,))
    if not r or r["kind"] != "photo" or not os.path.exists(r["path"]):
        raise HTTPException(404)
    from PIL import Image, ImageOps
    try:
        with Image.open(r["path"]) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=95)
    except Exception as e:
        raise HTTPException(400, f"无法读取：{e}")
    return Response(buf.getvalue(), media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/thumb/{pid}")
def api_thumb(pid: int, size: str = "s"):
    path = os.path.join(THUMB_DIR, f"{pid}_{size}.jpg")
    if not os.path.exists(path) and size == "m":
        r = db.q1("SELECT path FROM photos WHERE id=?", (pid,))
        if r:
            scanner.make_thumb(pid, r["path"], "m")
    if not os.path.exists(path):
        path = os.path.join(THUMB_DIR, f"{pid}_s.jpg")
    if not os.path.exists(path):
        raise HTTPException(404)
    # 缩略图内容永远不变（文件名带照片 id 与尺寸），可以放心 immutable：
    # 翻回看过的照片时 WebView2 直接命中磁盘缓存，连请求都不用发
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/image/{pid}")
def api_image(pid: int):
    r = db.q1("SELECT path FROM photos WHERE id=?", (pid,))
    if not r or not os.path.exists(r["path"]):
        raise HTTPException(404)
    return FileResponse(r["path"], headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/live/{pid}")
def api_live(pid: int):
    """实况照片的动态部分：返回与照片配对的短视频，原文件只读。"""
    r = db.q1("SELECT live_path FROM photos WHERE id=?", (pid,))
    if not r or not r["live_path"] or not os.path.exists(r["live_path"]):
        raise HTTPException(404)
    return FileResponse(r["live_path"], headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/video/{pid}/open-ext")
def api_video_open_ext(pid: int):
    """用系统默认播放器打开原文件。

    Chromium 内核不支持 AVI 这类容器（这是内核能力限制，不是实现问题），
    所以那些格式在应用内只能看封面，真要看就交给系统播放器 —— 顺带还有声音。
    """
    r = db.q1("SELECT path,kind FROM photos WHERE id=?", (pid,))
    if not r or r["kind"] != "video" or not os.path.exists(r["path"]):
        raise HTTPException(404, "not found")
    try:
        os.startfile(r["path"])
    except OSError as e:
        raise HTTPException(400, f"打不开：{e}")
    return {"opened": True, "path": r["path"]}


@app.get("/api/similar/{pid}")
def api_similar(pid: int):
    v = ai.load_embedding(pid)
    if v is None:
        raise HTTPException(400, "该照片还没有向量，请先运行 /api/embed（需 CLIP）")
    rows = db.q("SELECT photo_id, vec FROM embeddings WHERE photo_id!=?", (pid,))
    import struct
    scored = []
    for r in rows:
        n = len(r["vec"]) // 4
        scored.append((r["photo_id"], ai.cosine(v, struct.unpack(f"{n}f", r["vec"]))))
    scored.sort(key=lambda x: -x[1])
    ids = [p for p, _ in scored[:24]]
    if not ids:
        return {"items": []}
    marks = ",".join("?" * len(ids))
    items = [dict(r) for r in db.q(f"SELECT * FROM photos WHERE id IN ({marks})", ids)]
    items.sort(key=lambda it: ids.index(it["id"]))
    return {"items": items}


@app.post("/api/export")
def api_export(req: IdsReq):
    res = exporter.export_pack(req.ids or None, req.name)
    if not res:
        raise HTTPException(400, "没有可导出的照片")
    return res


@app.post("/api/share/copy")
def api_share_copy(req: ShareReq):
    """选中 → 复制到分享文件夹：原片不动，方便直接拖进聊天窗口发送。"""
    import shutil
    ids = req.ids
    if not ids:
        raise HTTPException(400, "没有选中照片")
    if not req.dir or not os.path.isdir(req.dir):
        raise HTTPException(400, "目标文件夹不存在")
    marks = ",".join("?" * len(ids))
    rows = db.q(f"SELECT id, path, name FROM photos WHERE id IN ({marks})", ids)
    count, skipped, used = 0, [], set()
    for r in rows:
        src = r["path"]
        if not src or not os.path.exists(src):
            skipped.append({"name": r["name"], "reason": "源文件不存在"})
            continue
        base, ext = os.path.splitext(r["name"] or os.path.basename(src))
        dst = os.path.join(req.dir, base + ext)
        n = 1
        while dst.lower() in used or os.path.exists(dst):
            dst = os.path.join(req.dir, f"{base}_{n}{ext}")
            n += 1
        used.add(dst.lower())
        try:
            shutil.copy2(src, dst)
            count += 1
        except Exception as e:
            skipped.append({"name": r["name"], "reason": f"复制失败：{e}"})
    return {"count": count, "dir": req.dir, "skipped": skipped[:20], "total": len(rows)}


@app.post("/api/extract")
def api_extract(req: ExtractReq):
    """把当前筛选结果整理到指定文件夹（复制或剪切，可分子目录）。"""
    kwargs = dict(q=req.q, tag=req.tag, kind=req.kind, favorite=req.favorite,
                  person_id=req.person_id, place_id=req.place_id, dir=req.dir,
                  min_quality=req.min_quality, camera=req.camera, junk=req.junk)
    if req.month:
        kwargs["date_from"], kwargs["date_to"] = _month_range(req.month)
    try:
        job = extract.prepare(req.dir, ids=req.ids or None, mode=req.mode,
                              layout=req.layout, prefix=req.prefix, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _jobs["extract"] = job
    threading.Thread(target=extract.run, args=(job,), daemon=True).start()
    return {"started": True, "total": job.total, "dir": job.dest, "mode": job.mode}


@app.get("/api/extract/status")
def api_extract_status():
    job = _jobs.get("extract")
    return job.to_dict() if job else {"status": "idle"}


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


@app.middleware("http")
async def revalidate_shell(request, call_next):
    """前端页面/脚本每次都要回源校验，改了代码刷新即生效，避免读到旧缓存。"""
    resp = await call_next(request)
    if not request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp
