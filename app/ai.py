"""AI 打标与语义搜索。

两层设计：
1) 启发式基线（始终可用、纯本地、零模型）：截图/文档/相机/夜景/视频等规则标签。
2) 可选 CLIP（onnxruntime + 本地模型，运行 scripts/download_models.py 后自动启用）：
   零样本场景/物体打标 + 文-图向量，用于自然语言搜索和以图搜图。
"""
import json
import math
import os
import struct

from . import db
from .config import MODEL_DIR

CLIP_IMAGE_MODEL = os.path.join(MODEL_DIR, "clip_image.onnx")
CLIP_TEXT_MODEL = os.path.join(MODEL_DIR, "clip_text.onnx")

# 零样本候选标签（CLIP 模式下用自然语言 prompt 匹配）
SCENE_LABELS = [
    "海滩", "雪山", "城市街景", "室内", "夜景", "日落", "森林", "美食",
    "宠物", "人物合影", "建筑", "花朵", "文档", "截图", "汽车", "天空",
]

_clip = None  # lazy: (img_sess, txt_sess, preprocess)


def ai_status():
    try:
        import onnxruntime  # noqa
    except Exception:
        return {"mode": "heuristic", "clip": False,
                "note": "未安装 onnxruntime，使用内置规则打标；运行 scripts/download_models.py 可启用 CLIP"}
    ok = os.path.exists(CLIP_IMAGE_MODEL) and os.path.exists(CLIP_TEXT_MODEL)
    return {"mode": "clip" if ok else "heuristic", "clip": ok,
            "note": "CLIP 就绪" if ok else "模型缺失，使用内置规则打标"}


# ---------------- 启发式基线 ----------------

def heuristic_tags(photo):
    """根据元数据/尺寸/亮度生成规则标签。photo 为 sqlite Row。"""
    tags = []
    w, h = photo["width"] or 0, photo["height"] or 0
    ext = (photo["ext"] or "").lower()
    if photo["kind"] == "video":
        tags.append(("视频", 1.0))
    if photo["camera_model"]:
        tags.append(("相机拍摄", 0.95))
    elif ext in (".png", ".webp") and w and h and (w / max(h, 1)) > 1.2 and not photo["camera_make"]:
        tags.append(("截图", 0.6))
    if ext == ".gif":
        tags.append(("动图", 0.9))
    t = photo["taken_at"] or 0
    if t:
        import time as _t
        hour = _t.localtime(t).tm_hour
        if hour >= 21 or hour < 5:
            tags.append(("夜晚拍摄", 0.7))
        elif 17 <= hour < 19:
            tags.append(("黄昏", 0.55))
    q = photo["quality"] or 0
    if q >= 70:
        tags.append(("高质量", 0.8))
    elif q and q < 30:
        tags.append(("模糊", 0.7))
    if photo["gps_lat"] is not None:
        tags.append(("含位置", 1.0))
    if w and h:
        tags.append(("横构图", 1.0) if w >= h else ("竖构图", 1.0))
    if w and h and w * h >= 8_000_000:
        tags.append(("高分辨率", 0.9))
    if photo["iso"] and photo["iso"] >= 800:
        tags.append(("高感光", 0.7))
    if photo["focal"] and photo["focal"] >= 100:
        tags.append(("长焦", 0.7))
    elif photo["focal"] and photo["focal"] <= 28:
        tags.append(("广角", 0.7))
    return tags


def _tone_tag(photo_id, avg=None):
    """用平均色判断色调，生成色彩类标签。

    平均色在导入时随直方图一起存库（avg_rgb），这里直接用，不再逐张打开缩略图；
    老数据没有平均色时才回退读文件。
    """
    if avg:
        r, g, b = avg
    else:
        from PIL import Image, ImageStat
        from .config import THUMB_DIR
        path = os.path.join(THUMB_DIR, f"{photo_id}_s.jpg")
        if not os.path.exists(path):
            return []
        try:
            r, g, b = ImageStat.Stat(Image.open(path).convert("RGB")).mean
        except Exception:
            return []
    mx, mn = max(r, g, b), min(r, g, b)
    if mx < 12:
        return []
    if mx - mn < 10:
        return [("低饱和", 0.6)]
    if r - b > 20:
        return [("暖色调", 0.7)]
    if b - r > 20:
        return [("冷色调", 0.7)]
    return []


def tag_photo_heuristic(photo):
    rows = [(photo["id"], tag, "heuristic", conf) for tag, conf in heuristic_tags(photo)]
    rows += [(photo["id"], tag, "color", conf) for tag, conf in _tone_tag(photo["id"])]
    b = db.q1("SELECT is_pick FROM bursts WHERE photo_id=?", (photo["id"],))
    if b:
        rows.append((photo["id"], "连拍精选" if b["is_pick"] else "连拍", "heuristic", 1.0))
    if rows:
        db.executemany("INSERT OR REPLACE INTO tags VALUES(?,?,?,?)", rows)
    return len(rows)


# ---------------- CLIP（可选） ----------------

def _load_clip():
    global _clip
    if _clip is not None:
        return _clip
    if not ai_status()["clip"]:
        _clip = False
        return _clip
    try:
        import onnxruntime as ort
        img_sess = ort.InferenceSession(CLIP_IMAGE_MODEL, providers=["CPUExecutionProvider"])
        txt_sess = ort.InferenceSession(CLIP_TEXT_MODEL, providers=["CPUExecutionProvider"])
        _clip = (img_sess, txt_sess)
    except Exception:
        _clip = False
    return _clip


def image_embedding(path):
    """返回 L2 归一化向量（list[float]）；CLIP 不可用则 None。"""
    if not _load_clip():
        return None
    try:
        import numpy as np
        from PIL import Image
        img = Image.open(path).convert("RGB").resize((224, 224))
        x = np.asarray(img, dtype=np.float32) / 255.0
        x = (x - np.array([0.48145466, 0.4578275, 0.40821073])) / np.array(
            [0.26862954, 0.26130258, 0.27577711])
        x = x.transpose(2, 0, 1)[None].astype(np.float32)
        sess = _clip[0]
        v = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
        v = v / (np.linalg.norm(v) + 1e-9)
        return v.tolist()
    except Exception:
        return None


def text_embedding(text):
    if not _load_clip():
        return None
    try:
        import numpy as np
        import re
        # 极简 BPE 不可用时的回退：字符级 tokenizer 仅作演示；正式使用请配合 clip tokenizer。
        # 这里期望模型输入为 int64 token ids（77 长度）。
        tokens = [49406] + [min(49151, ord(c) % 49152 + 256) for c in text[:75]] + [49407]
        tokens += [0] * (77 - len(tokens))
        x = np.array([tokens[:77]], dtype=np.int64)
        sess = _clip[1]
        v = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
        v = v / (np.linalg.norm(v) + 1e-9)
        return v.tolist()
    except Exception:
        return None


def save_embedding(photo_id, vec, model="clip"):
    blob = struct.pack(f"{len(vec)}f", *vec)
    db.execute("INSERT OR REPLACE INTO embeddings VALUES(?,?,?)", (photo_id, model, blob))


def load_embedding(photo_id):
    r = db.q1("SELECT vec FROM embeddings WHERE photo_id=?", (photo_id,))
    if not r:
        return None
    n = len(r["vec"]) // 4
    return list(struct.unpack(f"{n}f", r["vec"]))


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (na * nb)


def semantic_search(text, limit=60):
    qv = text_embedding(text)
    if qv is None:
        return None
    rows = db.q("SELECT photo_id, vec FROM embeddings")
    scored = []
    for r in rows:
        n = len(r["vec"]) // 4
        v = struct.unpack(f"{n}f", r["vec"])
        scored.append((r["photo_id"], cosine(qv, v)))
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


def embed_all():
    """为尚无向量的照片生成 CLIP 向量。"""
    if not ai_status()["clip"]:
        return 0
    rows = db.q("""SELECT p.id, p.path FROM photos p
                   LEFT JOIN embeddings e ON e.photo_id=p.id
                   WHERE e.photo_id IS NULL AND p.kind='photo'""")
    n = 0
    for r in rows:
        v = image_embedding(r["path"])
        if v:
            save_embedding(r["id"], v)
            n += 1
    return n


def tag_all(progress=None):
    """全库打标（按当前可用模式）。

    两处关键改动：
    1) 连拍映射一次查进内存，不再每张照片一次 SELECT；
    2) 每 2000 条标签一次 executemany —— 原先 1740 张照片就是 1740 次 commit。
    """
    rows = db.q("SELECT * FROM photos WHERE kind='photo'")
    n = len(rows)
    picks = {r["photo_id"]: r["is_pick"] for r in db.q("SELECT photo_id,is_pick FROM bursts")}
    hit = 0
    buf = []
    for i, r in enumerate(rows):
        avg = None
        if r["avg_rgb"]:
            try:
                avg = json.loads(r["avg_rgb"])
            except ValueError:
                avg = None
        tags = heuristic_tags(r) + _tone_tag(r["id"], avg)
        if r["id"] in picks:
            tags.append(("连拍精选" if picks[r["id"]] else "连拍", 1.0))
        for tag, conf in tags:
            buf.append((r["id"], tag,
                        "color" if tag in ("低饱和", "暖色调", "冷色调") else "heuristic",
                        conf))
        hit += len(tags)
        if len(buf) >= 2000:
            db.executemany("INSERT OR REPLACE INTO tags VALUES(?,?,?,?)", buf)
            buf = []
        if progress:
            progress(i + 1, n)
    if buf:
        db.executemany("INSERT OR REPLACE INTO tags VALUES(?,?,?,?)", buf)
    return hit
