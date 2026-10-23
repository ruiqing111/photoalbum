"""人物维度：YuNet 人脸检测 + SFace 特征的无监督分组。

流程：
  1) YuNet（OpenCV 自带的 ONNX 小模型）在 1280px 缩略图上找人脸，一张照片最多取 6 张；
     旧版靠肤色规则，木头家具、桌面杂物、沙石、暖色食物全都会命中，
     「没有人也被标成人物」就是这么来的。
  2) 用 YuNet 的 5 个关键点做人脸对齐，SFace 提 128 维特征，按余弦相似度聚类。
  3) 分三种结果：
     · 个人组：同一个人的照片（≥1 张，只有一张的也会单独成组）；
     · 合影组：一张照片里有 ≥2 张可信人脸，单独归到「合影」；
     · 合影里的每张脸只要够大，也照常参与个人聚类，所以「谁和谁的合照」两边都能找到。
  4) 保留已有分组的自定义名称，重新分析不会丢名字。

模型没找到时直接返回空结果：宁可不显示人物，也不乱标。
"""
import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from . import db
from .config import BUNDLE_MODEL_DIR, MODEL_DIR, THUMB_DIR

MAX_SIDE = 1280      # 检测输入的长边上限（正好是 m 缩略图的尺寸）
# 4 线程：解码与 cv2 推理期间都会释放 GIL，多线程实测有明显收益
WORKERS = 4
# 特征算法版本：改了判定规则就 +1，旧缓存会自动作废重算，
# 不然用户点「AI 分析」也刷不掉之前的误判。
FEAT_VERSION = "5"
# YuNet 置信度下限。0.90 那一档里手办、海报、橱窗模特还很多，
# 0.92 往上基本就是真人脸，宁可漏掉远景里的路人也不乱标。
SCORE = 0.92
# 可信人脸的下限（占画面短边比例）：低于这个连「这是张脸」都不认。
MIN_FACE = 0.05
# 用来判断「同一个人」的人脸下限。太小的脸放大到 112px 后特征几乎全是噪声，
# 会把不同的人并成一组；这种小脸只用来判断「这是一张合影」，不参与身份聚类。
CLUSTER_FACE = 0.07
# 只有一张照片的人物组：人脸还得再大一点才立组。
# 远景路人（占短边 5%~8%）单独成组几乎全是噪声，真人脸够大才值得单独立项。
SINGLE_FACE = 0.10
# 一张照片最多认几张脸：超过 6 张基本是远景人群，认准也没意义。
MAX_FACES = 6
# SFace 余弦相似度阈值。官方同人判定线是 0.363，但在低清/远景人脸上区分度很差，
# 实测 0.65 还会把两个不同的人并成一组，0.72 才分得开。
# 宁可把同一个人的不同场次拆成两组（用户可以手动合并），也不能把两个人混在一起。
SIM = 0.72

YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"
_tls = threading.local()


def _model_path(name):
    """优先用程序目录里的模型，其次用数据目录里的（方便用户自己换模型）。"""
    for d in (BUNDLE_MODEL_DIR, MODEL_DIR):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def _ascii(path):
    """OpenCV 的 dnn / FileStorage 按本地编码打开文件，中文路径会直接读失败。

    便携版很可能就放在「I:\\照片相册」这种中文目录，所以遇到非 ASCII 路径
    先复制一份到临时目录再用。
    """
    if all(ord(c) < 128 for c in path):
        return path
    d = os.path.join(tempfile.gettempdir(), "photoalbum_models")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, os.path.basename(path))
    if not os.path.exists(out) or os.path.getsize(out) != os.path.getsize(path):
        shutil.copyfile(path, out)
    return out


def _models():
    """每线程一份检测器/识别器：cv2 这两个对象都不是线程安全的。"""
    m = getattr(_tls, "models", None)
    if m is None:
        import cv2
        yp, sp = _model_path(YUNET), _model_path(SFACE)
        if not yp or not sp:
            m = (None, None)
        else:
            det = cv2.FaceDetectorYN_create(_ascii(yp), "", (MAX_SIDE, MAX_SIDE),
                                            SCORE, 0.3, 5000)
            rec = cv2.FaceRecognizerSF_create(_ascii(sp), "")
            m = (det, rec)
        _tls.models = m
    return m


def _source(pid, path):
    """优先用 1280px 的 m 缩略图：原图动辄几千万像素，解码一次几百毫秒；
    而 m 已经由预热生成，脸也足够大，不用碰原图。"""
    m = os.path.join(THUMB_DIR, f"{pid}_m.jpg")
    return m if os.path.exists(m) else path


def _faces_of(pid, path):
    """找出照片里所有可信的人脸。

    返回 [(序号, 人脸占短边比例, 检测置信度, 128 维单位向量 bytes), ...]，按人脸面积从大到小。
    没有可信人脸返回 []。
    """
    try:
        import cv2
        det, rec = _models()
        if det is None:
            return []
        # 不能用 cv2.imread：它在 Windows 上按本地编码走路径，
        # 「I:\照片相册\...」这种中文路径会直接读失败（然后全库被当成"检测不到"）。
        buf = np.fromfile(_source(pid, path), dtype=np.uint8)
        if not buf.size:
            return []
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            return []
        h, w = img.shape[:2]
        if max(h, w) > MAX_SIDE:
            s = MAX_SIDE / float(max(h, w))
            img = cv2.resize(img, (int(w * s), int(h * s)))
        H, W = img.shape[:2]
        short = float(min(H, W))
        det.setInputSize((W, H))
        _, faces = det.detect(img)
        if faces is None or not len(faces):
            return []
        faces = sorted((f for f in faces if f[2] >= short * MIN_FACE),
                       key=lambda f: -float(f[2] * f[3]))[:MAX_FACES]
        out = []
        for i, f in enumerate(faces):
            v = rec.feature(rec.alignCrop(img, f)).flatten().astype(np.float32)
            n = float(np.linalg.norm(v))
            if n < 1e-6:
                continue
            out.append((i, float(f[2]) / short, float(f[14]), (v / n).tobytes()))
        return out
    except Exception:
        return []


def _features(progress=None, force=False):
    """取每张照片的人脸特征，缓存到 person_emb（一张照片可以有多行）。

    中途被打断再跑，已算过的直接复用；score = 0 表示「看过，没检出可信人脸」，
    这样下次不用重复解码没人的照片。
    """
    # 算法升级后旧特征一律作废：否则误报会一直躺在缓存里，
    # 用户点多少次「AI 分析」都刷不掉。
    ver = db.q1("SELECT v FROM meta WHERE k='feat_version'")
    if not ver or ver["v"] != FEAT_VERSION:
        force = True
    if force:
        db.execute("DELETE FROM person_emb")
    cache = {}
    for r in db.q("SELECT photo_id, face_idx, score, size, vec FROM person_emb"):
        cache.setdefault(r["photo_id"], []).append(r)
    rows = db.q("""SELECT id, path, quality FROM photos
                   WHERE kind='photo' ORDER BY taken_at""")
    todo = [r for r in rows if r["id"] not in cache]
    fresh = {}
    if todo:
        ex = ThreadPoolExecutor(max_workers=WORKERS)
        try:
            futs = {ex.submit(_faces_of, r["id"], r["path"]): r["id"] for r in todo}
            done = 0
            for fut in as_completed(futs):
                pid = futs[fut]
                try:
                    fresh[pid] = fut.result()
                except Exception:
                    fresh[pid] = []
                done += 1
                if progress:
                    progress(done, len(todo))   # 取消检查点：Cancelled 会从这里抛出去
        finally:
            # 取消时不再等排队中的任务，最多等正在跑的 4 张
            ex.shutdown(wait=False, cancel_futures=True)
    if fresh:
        add, empty = [], []
        for pid, faces in fresh.items():
            if faces:
                add += [(pid, i, sc, s, v) for i, s, sc, v in faces]
            else:
                # 占位行：表示「这张看过、没有脸」，避免下次重复解码
                empty.append((pid, 0, 0.0, 0.0, None))
        db.executemany("INSERT OR REPLACE INTO person_emb VALUES(?,?,?,?,?)", add + empty)
        db.execute("INSERT OR REPLACE INTO meta VALUES('feat_version', ?)", (FEAT_VERSION,))
    feats = []
    for r in rows:
        got = fresh.get(r["id"]) if r["id"] not in cache else \
            [(c["face_idx"], c["size"], c["score"], c["vec"]) for c in cache[r["id"]] if c["vec"]]
        if not got:
            continue
        feats.append({"id": r["id"], "q": r["quality"] or 0,
                      "faces": [(i, float(s), float(sc), np.frombuffer(v, dtype=np.float32))
                                for i, s, sc, v in got]})
    return feats


def analyze(progress=None, force=False):
    """重建人物分组：个人组 + 合影组，保留已有分组的自定义名称。"""
    feats = _features(progress=progress, force=force)
    # 合影：一张照片里有两张以上可信人脸
    group_ids = [f["id"] for f in feats if len(f["faces"]) >= 2]
    # 身份聚类只用够大的脸；小脸只负责「这是合影」
    faces = []
    solo = {}                      # 只有一张脸的照片：单张也要单独成组
    for f in feats:
        usable = [(i, v, s) for i, s, sc, v in f["faces"] if s >= CLUSTER_FACE]
        if len(f["faces"]) == 1:
            solo[f["id"]] = True
        for i, v, s in usable:
            faces.append((f["id"], i, v, s))

    clusters = []
    for pid, idx, v, size in faces:
        bi, bs = -1, SIM
        for i, c in enumerate(clusters):
            sim = float(np.dot(v, c["mean"]))
            if sim >= bs:
                bi, bs = i, sim
        if bi >= 0:
            c = clusters[bi]
            c["faces"].append((pid, idx, size))
            c["big"] = max(c["big"], size)
            mean = c["mean"] * (len(c["faces"]) - 1) + v
            c["mean"] = mean / (np.linalg.norm(mean) + 1e-9)
        else:
            clusters.append({"faces": [(pid, idx, size)], "mean": v.copy(), "big": size})

    # 合影里的脸如果自己聚不出第二张，就不该单独立组（否则同一张照片被拆成好几组）；
    # 单人组还要求这张脸够大，避免把远景路人一个个立成「人物」。
    out = []
    for c in clusters:
        ids = []
        for pid, idx, size in c["faces"]:
            if pid not in ids:
                ids.append(pid)
        if len(ids) >= 2 or (len(ids) == 1 and solo.get(ids[0]) and c["big"] >= SINGLE_FACE):
            out.append({"ids": ids, "faces": c["faces"]})
    out.sort(key=lambda c: -len(c["ids"]))

    old = {r["cover_photo_id"]: dict(r) for r in db.q(
        "SELECT * FROM people WHERE kind<>'group'")}
    qmap = {f["id"]: f["q"] for f in feats}
    db.execute("DELETE FROM person_photos")
    db.execute("DELETE FROM people")
    now = int(time.time())
    used = set()

    def add_row(name, kind, ids):
        cover = max(ids, key=lambda p: qmap.get(p, 0))
        cur = db.execute(
            """INSERT INTO people(name,cover_photo_id,photo_count,created_at,updated_at,kind)
               VALUES(?,?,?,?,?,?)""",
            (name, cover, len(ids), now, now, kind))
        return cur.lastrowid

    for i, c in enumerate(out):
        reused = next((old[p] for p in c["ids"] if p in old), None)
        name = reused["name"] if reused else f"人物 {i + 1}"
        if name in used:                       # 拆分后可能撞名，补个序号
            base, k = f"人物 {i + 1}", 2
            name = base
            while name in used:
                name, k = f"{base}-{k}", k + 1
        used.add(name)
        pid = add_row(name, "person", c["ids"])
        db.executemany("INSERT OR REPLACE INTO person_photos VALUES(?,?,?,?)",
                       [(pid, x, 0.0, 0) for x in c["ids"]])
    if group_ids:
        gid = add_row("合影", "group", group_ids)
        db.executemany("INSERT OR REPLACE INTO person_photos VALUES(?,?,?,?)",
                       [(gid, x, 0.0, 0) for x in group_ids])
    return len(out) + (1 if group_ids else 0)


def people_list():
    """人物列表：个人组按照片数降序，合影组排在最后。"""
    return [dict(r) for r in db.q(
        "SELECT * FROM people ORDER BY (kind='group'), photo_count DESC, id")]


def person_photos(person_id):
    rows = db.q("""SELECT p.* FROM person_photos pp JOIN photos p ON p.id=pp.photo_id
                   WHERE pp.person_id=? ORDER BY p.taken_at DESC""", (person_id,))
    items = [dict(r) for r in rows]
    for it in items:
        it["tags"] = [t["tag"] for t in db.q(
            "SELECT tag FROM tags WHERE photo_id=?", (it["id"],))]
    return items


def rename(person_id, name):
    db.execute("UPDATE people SET name=?, updated_at=? WHERE id=?",
               (name, int(time.time()), person_id))
    return {"id": person_id, "name": name}


def merge(src_id, dst_id):
    """把 src 的所有照片并入 dst，并删除 src。"""
    if src_id == dst_id:
        return {"merged": 0}
    rows = db.q("SELECT photo_id FROM person_photos WHERE person_id=?", (src_id,))
    db.executemany("INSERT OR IGNORE INTO person_photos VALUES(?,?,?,?)",
                   [(dst_id, r["photo_id"], 0.0, 0) for r in rows])
    cnt = db.q1("SELECT COUNT(*) c FROM person_photos WHERE person_id=?", (dst_id,))["c"]
    db.execute("UPDATE people SET photo_count=?, updated_at=? WHERE id=?",
               (cnt, int(time.time()), dst_id))
    db.execute("DELETE FROM person_photos WHERE person_id=?", (src_id,))
    db.execute("DELETE FROM people WHERE id=?", (src_id,))
    return {"merged": len(rows), "target_count": cnt}


def assign(photo_id, person_id):
    """把一张照片手动归到某个人物组。

    自动聚类难免有漏（同一人换了造型会被拆成两组），这里给用户一个出口；
    只是改索引关系，照片本身不动。
    """
    if not db.q1("SELECT 1 FROM photos WHERE id=?", (photo_id,)):
        return {"ok": False, "reason": "照片不存在"}
    if not db.q1("SELECT 1 FROM people WHERE id=?", (person_id,)):
        return {"ok": False, "reason": "分组不存在"}
    db.execute("INSERT OR IGNORE INTO person_photos VALUES(?,?,?,?)",
               (person_id, photo_id, 0.0, 0))
    _refresh(person_id)
    return {"ok": True, "photo_count": _count(person_id)}


def detach(photo_id, person_id):
    """把一张照片从某个人物组移出（仍留在相册里）。"""
    db.execute("DELETE FROM person_photos WHERE person_id=? AND photo_id=?",
               (person_id, photo_id))
    left = _count(person_id)
    if left:
        _refresh(person_id)
    else:
        db.execute("DELETE FROM people WHERE id=?", (person_id,))
    return {"ok": True, "photo_count": left}


def _count(person_id):
    return db.q1("SELECT COUNT(*) c FROM person_photos WHERE person_id=?",
                 (person_id,))["c"]


def _refresh(person_id):
    """重算封面（组内画质最高的那张）与计数。"""
    cnt = _count(person_id)
    best = db.q1("""SELECT pp.photo_id p FROM person_photos pp
                    JOIN photos ph ON ph.id=pp.photo_id
                    WHERE pp.person_id=? ORDER BY ph.quality DESC LIMIT 1""", (person_id,))
    db.execute("UPDATE people SET photo_count=?, cover_photo_id=?, updated_at=? WHERE id=?",
               (cnt, best["p"] if best else None, int(time.time()), person_id))
