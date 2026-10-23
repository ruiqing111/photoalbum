"""扫描目录、解析 EXIF、生成缩略图、写索引。原件永不修改。"""
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from PIL import Image, ImageOps

from . import db
from .config import IMAGE_EXTS, THUMB_DIR, THUMB_SIZES, VIDEO_EXTS

Image.MAX_IMAGE_PIXELS = 200_000_000
# iPhone 默认拍 HEIC，Pillow 自己解不了。装上 pillow-heif 后注册解码器，
# 否则这些照片能被扫描到却永远生成不出缩略图（点开是一片破图）。
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    _HEIF = True
except Exception:                        # 没装就静默降级，其它格式照常工作
    _HEIF = False
# 预热是一整轮扫全库的活儿，只允许一个在跑（启动时的后台线程与
# 「AI 分析」里的 warm 步骤都要用它，撞在一起就是双倍磁盘 I/O）
_warm_lock = threading.Lock()
# 外接机械盘上并发解原图会把寻道队列塞满：2 路已经够快，再多只是在互相拖。
WARM_WORKERS = 2
# 每次启动最多补这么多张 m 缩略图，剩下的交给查看器按需生成，
# 免得刚导完一万多张、下次一开机就又是一轮全盘解码。
WARM_M_LIMIT = 300
# 导入节流：每多少张提交一次索引、每张之间歇多久（秒）
BATCH_COMMIT = 25
PACE_SECONDS = 0.02


def _save_jpg(img, out, quality=82):
    tmp = f"{out}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        img.save(tmp, "JPEG", quality=quality)
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def file_hash(path, chunks=3, chunk_size=1 << 20):
    """快速内容哈希：头/中/尾各 1MB + 文件大小。"""
    h = hashlib.sha1()
    size = os.path.getsize(path)
    h.update(str(size).encode())
    with open(path, "rb") as f:
        for off in (0, max(0, size // 2 - chunk_size // 2), max(0, size - chunk_size)):
            f.seek(off)
            h.update(f.read(chunk_size))
    return h.hexdigest()


def _parse_dt(s):
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.strptime(s, fmt).timestamp())
        except Exception:
            pass
    return None


def _ratio(v):
    try:
        return float(v[0]) / float(v[1]) if v[1] else None
    except Exception:
        try:
            return float(v)
        except Exception:
            return None


def _gps_to_deg(v):
    try:
        d, m, s = (_ratio(x) or 0 for x in v)
        return d + m / 60 + s / 3600
    except Exception:
        return None


def read_exif(path):
    info = {}
    try:
        img = Image.open(path)
        exif = img.getexif()
        if not exif:
            return info
        info["camera_make"] = str(exif.get(271) or "").strip() or None
        info["camera_model"] = str(exif.get(272) or "").strip() or None
        info["orientation"] = exif.get(274)
        try:
            sub = exif.get_ifd(0x8769)

            def g(k):
                v = sub.get(k)
                return exif.get(k) if v is None else v

            info["taken_at"] = _parse_dt(g(36867) or g(36868) or "")
            info["focal"] = _ratio(g(37386))
            info["aperture"] = _ratio(g(33437))
            sh = _ratio(g(33434))
            info["shutter"] = (f"1/{int(1/sh)}" if sh and 0 < sh < 1 else (str(sh) if sh else None))
            info["iso"] = g(34855)
            info["lens"] = str(g(42036) or "").strip() or None
        except Exception:
            pass
        try:
            gps = exif.get_ifd(0x8825)
            if gps:
                lat, lon = _gps_to_deg(gps.get(2)), _gps_to_deg(gps.get(4))
                if lat is not None:
                    info["gps_lat"] = -lat if gps.get(1) == "S" else lat
                if lon is not None:
                    info["gps_lon"] = -lon if gps.get(3) == "W" else lon
                info["gps_alt"] = _ratio(gps.get(6))
        except Exception:
            pass
    except Exception:
        pass
    return info


def thumb_stats(path):
    """从缩略图算出直方图（每通道 16 桶）与平均色，序列化成 JSON 存库。

    这两样原先由查看器每次切图现算（打开缩略图 + resize + histogram，实测 120ms）；
    导入时算一次存下来，切图就只剩一次 SELECT。
    """
    try:
        with Image.open(path) as img:
            h = img.convert("RGB").histogram()
    except Exception:
        return None, None
    # 直接在缩略图上取直方图，省掉一次 resize（全库回填时差别很明显）
    hist, avg = {}, []
    for i, ch in enumerate("rgb"):
        part = h[i * 256:(i + 1) * 256]
        hist[ch] = [sum(part[b:b + 16]) for b in range(0, 256, 16)]
        total = sum(part) or 1
        avg.append(round(sum(v * n for v, n in enumerate(part)) / total))
    return json.dumps(hist, separators=(",", ":")), json.dumps(avg, separators=(",", ":"))


def make_thumb(photo_id, path, size_key):
    side = THUMB_SIZES[size_key]
    out = os.path.join(THUMB_DIR, f"{photo_id}_{size_key}.jpg")
    if os.path.exists(out):
        return out
    # 不再整段加锁：解原图是纯 CPU 活，锁住会让预热的线程池退化成单线程。
    # _save_jpg 写的是带线程号的临时文件再 os.replace，天然满足原子性，
    # 最多是极端并发下同一张多解一次，不会写出半个 jpg。
    try:
        img = Image.open(path)
        # 目标比原图小很多时让 JPEG 直接按 1/2、1/4、1/8 解码（draft），
        # 生成 1280px 的 m 缩略图能省掉一个数量级的解码量。必须在 load 之前调用。
        if img.format == "JPEG" and max(img.size) > side * 2:
            img.draft("RGB", (side, side))
        img = ImageOps.exif_transpose(img)
        img.thumbnail((side, side))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        _save_jpg(img, out)
        return out
    except Exception:
        return None


def _fourcc(cap, cv2):
    """把 OpenCV 的四字符编码解成可读字符串（h264 / MJPG …）。"""
    v = int(cap.get(cv2.CAP_PROP_FOURCC))
    s = "".join(chr((v >> 8 * i) & 0xFF) for i in range(4)).strip(" \x00")
    return s.lower() or None


def probe_video(path):
    """读视频的宽高/帧率/时长/编码。

    全靠 OpenCV 自带的 ffmpeg 解码；任意一步失败都返回空字典 —— 视频进不了库
    是小事，把整次导入拖垮才是大事。
    """
    cap = None
    try:
        import cv2
    except ImportError:
        return {}
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return {}
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        out = {"width": w, "height": h,
               "fps": round(fps, 2) if fps > 0 else None,
               "vcodec": _fourcc(cap, cv2)}
        if fps > 0 and frames > 0:
            out["duration"] = round(frames / fps, 2)
        return out
    except Exception:
        return {}
    finally:
        if cap is not None:
            cap.release()


def _video_frame(path):
    """抽 10% 处的一帧当封面（开头常是黑场，第一帧等于没封面），失败退回第一帧。

    返回 PIL 图像；解码不了返回 None —— 视频封面失败不能拖垮整次导入。
    """
    try:
        import cv2
    except ImportError:
        return None
    cap = None
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        if fps > 0 and frames > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, frames / fps * 1000 * 0.1)
        ok, frame = cap.read()
        if (not ok or frame is None) and frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok or frame is None:
            return None
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    except Exception:
        return None
    finally:
        if cap is not None:
            cap.release()


def make_video_thumbs(photo_id, path, angle=0):
    """一次解码同时写 s 与 m 两张封面。

    原来 s、m 各调一次 cv2，等于把同一段片子从头解两遍；库里视频占三成时，
    这一处是移动硬盘上最不值得的重复 I/O。angle 是用户设定的顺时针旋转角度，
    封面跟着转，网格里才和查看器看到的一致。
    """
    frame = _video_frame(path)
    if frame is None:
        return None
    for size_key, side in THUMB_SIZES.items():
        out = os.path.join(THUMB_DIR, f"{photo_id}_{size_key}.jpg")
        if os.path.exists(out):
            continue
        img = frame.copy()
        img.thumbnail((side, side))
        if angle % 360:
            # PIL 的 rotate 是逆时针，用户给的是顺时针，取负号；
            # expand=True 后长宽互换，再缩一次才符合尺寸约定
            img = img.rotate(-angle, expand=True)
            img.thumbnail((side, side))
        _save_jpg(img, out)
    return True


def iter_media(dirs):
    for root_dir in dirs:
        for dirpath, _, files in os.walk(root_dir):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMAGE_EXTS or ext in VIDEO_EXTS:
                    yield os.path.join(dirpath, fn)


_JUNK_NAME = re.compile(r"^(thumbcache|thumbnail|thumbs?|thumb[_-]|资源管理器|临时文件)[_\-]", re.I)


def _looks_like_junk(path, name, dirpath, width, height, size):
    """判断一张图是不是「浏览器缓存/系统缩略图」这类非照片。

    规则分强弱两档，宁可漏判也不误伤正常照片：
      1) 文件名就是 Windows 缩略图缓存（thumbcache_*/资源管理器_*/临时文件_*）—— 直接算；
      2) 目录名明确是缩略图恢复/系统缓存/thumbnails —— 只要尺寸不超过 1280 就算；
      3) 目录名带 cache/temp/thumb 的，再叠加「小尺寸或小文件」才判；
      4) 没有这层目录线索时，只看「极小图」和「超宽广告横幅」这两种极端情况。
    误判可以到「非照片」页点「标记为照片」恢复，自动识别之后不会再改它。
    """
    m = max(width or 0, height or 0)
    n = name or ""
    d = (dirpath or "").lower()
    if _JUNK_NAME.match(n):
        return True
    if any(k in d for k in ("缩略图", "thumbcache", "thumbnails", "系统缓存")):
        return m <= 1280 if m else True
    if any(k in d for k in ("\\cache", "/cache", "\\temp", "/temp", "\\tmp", "/tmp", "thumb")):
        return (m and m <= 512) or (m <= 1280 and size <= 120 * 1024) or not m
    if m and m <= 200 and size <= 60 * 1024:
        return True
    if (m and width and height and m <= 512 and size <= 150 * 1024
            and m / max(1, min(width, height)) >= 3.2):
        return True
    return False


def _live_companion(path):
    """找实况照片配对的短视频（同目录、同文件名、视频扩展名）。

    iPhone 的实况照片导出后是 IMG_1234.HEIC + IMG_1234.MOV 成对出现。
    找到就把 MOV 记在照片上：网格显示「实况」角标，查看时可以播放动态。
    MOV 本身仍按视频正常入库，所以在「视频」页照样能找到。
    """
    stem = os.path.splitext(path)[0]
    for ext in VIDEO_EXTS:
        for cand in (stem + ext, stem + ext.upper()):
            if os.path.normcase(cand) == os.path.normcase(path):
                continue
            if os.path.exists(cand):
                return cand
    return None


def ingest_file(path):
    ext = os.path.splitext(path)[1].lower()
    st = os.stat(path)
    kind = "video" if ext in VIDEO_EXTS else "photo"
    width = height = None
    exif = {}
    if kind == "photo":
        try:
            with Image.open(path) as img:
                width, height = img.size
        except Exception:
            return None
        exif = read_exif(path)
    else:
        # 视频没有 EXIF，宽高/时长/帧率/编码全靠 OpenCV 解出来
        exif = probe_video(path)
        width, height = exif.get("width"), exif.get("height")
    taken = exif.get("taken_at") or int(st.st_mtime)
    h = file_hash(path)
    # 只按「路径」判断重复导入：同一张照片换个文件夹再导入，照样进索引，
    # 由「重复照片」页统一显示并提供一键清理。若这里按内容 hash 直接跳过，
    # 那份副本在库里完全消失，重复照片页也就永远是空的。
    exist = db.q1("SELECT id FROM photos WHERE path=?", (path,))
    if exist:
        return exist["id"], True
    junk = 1 if kind == "photo" and _looks_like_junk(
        path, os.path.basename(path), os.path.dirname(path), width, height, st.st_size) else 0
    cur = db.execute(
        """INSERT OR IGNORE INTO photos(path,name,dir,ext,size,width,height,duration,fps,vcodec,
        taken_at,mtime,hash,
        camera_make,camera_model,lens,focal,aperture,shutter,iso,gps_lat,gps_lon,gps_alt,
        orientation,kind,junk,added_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (path, os.path.basename(path), os.path.dirname(path), ext, st.st_size, width, height,
         exif.get("duration"), exif.get("fps"), exif.get("vcodec"),
         taken, int(st.st_mtime), h, exif.get("camera_make"), exif.get("camera_model"),
         exif.get("lens"), exif.get("focal"), exif.get("aperture"), exif.get("shutter"),
         exif.get("iso"), exif.get("gps_lat"), exif.get("gps_lon"), exif.get("gps_alt"),
         exif.get("orientation"), kind, junk, int(time.time())),
    )
    pid = cur.lastrowid
    if not cur.rowcount:                 # 极小概率的并发同路径写入，按已存在处理
        row = db.q1("SELECT id FROM photos WHERE path=?", (path,))
        return (row["id"] if row else None), True
    if kind == "photo":
        # 导入阶段只出 s（网格用）：m 要到查看器打开时才需要，
        # 十几万次「解原图 + 写盘」堆在导入流程里，正是移动硬盘被拖死的主因。
        # /api/thumb 会在查看器第一次要 m 时按需补，晚一点没有任何副作用。
        s_path = make_thumb(pid, path, "s")
        hist, avg = thumb_stats(s_path) if s_path else (None, None)
        if hist:
            db.execute("UPDATE photos SET hist=?, avg_rgb=? WHERE id=?", (hist, avg, pid))
        live = _live_companion(path)
        if live:
            db.execute("UPDATE photos SET is_live=1, live_path=? WHERE id=?", (live, pid))
    else:
        # 视频一次解码出 s/m 两张：网格用 s，查看器拿 m 当 poster 秒开
        make_video_thumbs(pid, path)
    return pid, False


def warm_thumbs(progress=None):
    """给老库补上直方图与 m 缩略图（新导入的照片在 ingest_file 里已经算好）。

    只读缩略图与原图、只写索引和缓存文件，原图一个字节都不动。
    两遍走：先补直方图（只读 320px 小图，很快），再补 m（要解原图，慢一些）。
    """
    with _warm_lock:
        return _warm_thumbs_locked(progress)


# 导入进行时把预热让开：两件事同时解原图、写盘，移动硬盘的寻道队列会被打满
_scan_running = threading.Event()


def _wait_scan():
    while _scan_running.is_set():
        time.sleep(0.25)


def mark_junk():
    """给老库补一次「非照片」标记：只写 junk 字段，不动任何文件。

    junk_fix=1 是用户在「非照片」页手动确认过的照片，不再自动改动。
    返回本次新标记的张数。
    """
    rows = db.q("SELECT id,path,name,dir,width,height,size FROM photos "
                "WHERE kind='photo' AND junk=0 AND junk_fix=0")
    batch, n = [], 0
    for r in rows:
        if _looks_like_junk(r["path"], r["name"], r["dir"], r["width"], r["height"], r["size"] or 0):
            batch.append((r["id"],))
            n += 1
            if len(batch) >= 500:
                db.executemany("UPDATE photos SET junk=1 WHERE id=?", batch)
                batch = []
    if batch:
        db.executemany("UPDATE photos SET junk=1 WHERE id=?", batch)
    return n


def backfill_live():
    """给老库补实况照片配对：导入时只处理新文件，历史照片在启动时补一次。

    只写索引里的 is_live / live_path，不动任何文件；配对的视频照旧留在视频页。
    """
    vids = {}
    for r in db.q("SELECT path FROM photos WHERE kind='video'"):
        p = r["path"]
        vids.setdefault((os.path.dirname(p).lower(),
                         os.path.splitext(os.path.basename(p))[0].lower()), p)
    if not vids:
        return 0
    batch = []
    for r in db.q("SELECT id, path FROM photos WHERE kind='photo' AND is_live=0"):
        key = (os.path.dirname(r["path"]).lower(),
               os.path.splitext(os.path.basename(r["path"]))[0].lower())
        v = vids.get(key)
        if v:
            batch.append((v, r["id"]))
    if batch:
        db.executemany("UPDATE photos SET is_live=1, live_path=? WHERE id=?", batch)
    return len(batch)


def _warm_thumbs_locked(progress):
    try:
        backfill_live()
    except Exception:
        pass
    rows = db.q("SELECT id, path, hist FROM photos WHERE kind='photo'")
    hist_todo = [r for r in rows if not r["hist"]]
    m_todo = [r for r in rows
              if not os.path.exists(os.path.join(THUMB_DIR, f"{r['id']}_m.jpg"))][:WARM_M_LIMIT]
    total = len(hist_todo) + len(m_todo)
    done = 0

    batch = []
    for r in hist_todo:
        _wait_scan()
        s_path = os.path.join(THUMB_DIR, f"{r['id']}_s.jpg")
        if not os.path.exists(s_path):
            s_path = make_thumb(r["id"], r["path"], "s")
        hist, avg = thumb_stats(s_path) if s_path else (None, None)
        if hist:
            batch.append((hist, avg, r["id"]))
            if len(batch) >= 200:
                db.executemany("UPDATE photos SET hist=?, avg_rgb=? WHERE id=?", batch)
                batch = []
        done += 1
        if progress:
            progress(done, total)
    if batch:
        db.executemany("UPDATE photos SET hist=?, avg_rgb=? WHERE id=?", batch)

    # m 那遍要解原图，单线程跑 1700 张太慢：4 路并发压满 CPU，
    # 回收完立刻取消排队中的任务，点「取消」不用等整轮跑完。
    if m_todo:
        ex = ThreadPoolExecutor(max_workers=WARM_WORKERS, thread_name_prefix="warm")
        try:
            futs = [ex.submit(_warm_one, r) for r in m_todo]
            for _ in as_completed(futs):
                done += 1
                if progress:
                    progress(done, total)
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
    return total


def _warm_one(row):
    _wait_scan()
    make_thumb(row["id"], row["path"], "m")
    time.sleep(PACE_SECONDS)             # 给移动硬盘的寻道队列留一点空隙
    return row["id"]


class ScanJob:
    def __init__(self, dirs):
        self.dirs = dirs
        self.status = "running"
        self.total = 0
        self.done = 0
        self.new = 0
        self.dups = 0
        self.errors = 0
        self.speed = 0.0
        self.junk = 0                   # 本次新导入里被识别为「非照片」的张数
        self.message = ""
        self.started_at = time.time()
        self.finished_at = None
        # 导入报告：跳过/失败的清单，让用户知道哪些照片没进来、为什么
        self.dup_names = []
        self.failed = []

    def to_dict(self):
        d = {k: getattr(self, k) for k in
             ("dirs", "status", "total", "done", "new", "dups", "errors",
              "junk", "speed", "message", "started_at", "finished_at")}
        d["speed"] = round(self.speed, 1)
        d["dup_names"] = self.dup_names[:30]
        d["failed"] = self.failed[:30]
        d["persisted"] = self.new        # 已经入库、随时可用的张数
        return d


def _drive_gone(err, dirs):
    """判断这次失败是「文件坏了」还是「整块盘出问题了」。

    盘掉线时继续猛敲只会让控制器更难受，必须立刻停手。
    """
    if not all(os.path.isdir(d) for d in dirs):
        return True
    return isinstance(err, OSError) and getattr(err, "errno", None) in (5, 13, 21, 1117)


def run_scan(job: ScanJob):
    # 导入线程延后提交：一万一十张若每张都 fsync，光落盘就要几十分钟。
    # 每 BATCH_COMMIT 张提交一次，中途停止时前面的照片照样已经在库里。
    db.defer_commits(True)
    _scan_running.set()
    streak = 0
    try:
        files = list(iter_media(job.dirs))
        job.total = len(files)
        for i, p in enumerate(files, 1):
            if job.status == "cancelled":
                break
            try:
                pid, is_dup = ingest_file(p) or (None, False)
                streak = 0
                if is_dup:
                    job.dups += 1
                    if len(job.dup_names) < 30:
                        job.dup_names.append(os.path.basename(p))
                elif pid:
                    job.new += 1
                else:
                    job.errors += 1
                    if len(job.failed) < 30:
                        job.failed.append({"name": os.path.basename(p), "reason": "无法解码"})
            except Exception as e:
                job.errors += 1
                if len(job.failed) < 30:
                    job.failed.append({"name": os.path.basename(p), "reason": str(e)})
                streak = streak + 1 if _drive_gone(e, job.dirs) else 0
            job.done += 1
            elapsed = time.time() - job.started_at
            job.speed = job.done / elapsed if elapsed > 0 else 0
            if job.done % BATCH_COMMIT == 0:
                db.commit()
                time.sleep(PACE_SECONDS)   # 让磁盘喘口气，别把 I/O 队列打满
            if streak >= 8:
                job.status = "stopped"
                job.message = ("移动硬盘没有响应或目录已断开，导入已自动停止。"
                               "已经导入的照片都在库里，可以正常浏览。")
                break
        if job.status == "running":
            job.status = "done"
    except Exception as e:
        job.status = "error"
        job.message = str(e)
    finally:
        try:
            db.commit()                    # 停止/出错也把已处理的照片落盘
        except Exception:
            pass
        db.defer_commits(False)
        _scan_running.clear()
        try:
            row = db.q1("SELECT COUNT(*) n FROM photos WHERE junk=1 AND added_at>=?",
                        (int(job.started_at),))
            job.junk = row["n"] if row else 0
        except Exception:
            pass
        if job.new or job.dups:
            try:
                db.fts_rebuild()           # 中途停止的照片也要能被搜到
            except Exception:
                pass
        job.finished_at = time.time()
        if job.status == "cancelled" and not job.message:
            job.message = f"已停止导入，已导入的 {job.new} 张可以直接使用"
