"""生成测试照片集：4 位不同人物 + 多城市 GPS + 风景/夜景/截图/连拍。

人像刻意做成"同一人同肤色同构图、不同人差异明显"，用于验证人物聚类；
GPS 刻意分散在多个城市，用于验证地点聚合。纯合成图，仅用于功能演示。
"""
import os
import random
import sys
import time

from PIL import Image, ImageDraw, ImageFilter

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "test_photos")
os.makedirs(OUT, exist_ok=True)
random.seed(42)

BASE_TS = int(time.mktime((2025, 6, 1, 10, 0, 0, 0, 0, -1)))

# (城市, 纬度, 经度)
CITY_GPS = [
    ("上海", 31.2304, 121.4737), ("杭州", 30.2741, 120.1551), ("北京", 39.9042, 116.4074),
    ("三亚", 18.2528, 109.5119), ("巴黎", 48.8566, 2.3522),
]

# 人物：肤色/发色/衣服/背景/头部宽度都区分开，便于聚类
PERSONS = [
    dict(name="小雅", skin=(242, 205, 185), hair=(45, 35, 32), top=(62, 86, 150), bg=(88, 104, 148), hw=1.00),
    dict(name="阿哲", skin=(198, 148, 112), hair=(28, 26, 30), top=(48, 104, 88), bg=(72, 112, 96), hw=1.08),
    dict(name="奶奶", skin=(168, 120, 95), hair=(190, 190, 195), top=(132, 134, 140), bg=(104, 104, 116), hw=0.94),
    dict(name="多多", skin=(250, 220, 200), hair=(88, 60, 42), top=(40, 70, 130), bg=(96, 118, 158), hw=0.88),
]


def ts_of(offset_days, hour=10):
    t = time.localtime(BASE_TS + offset_days * 86400)
    return time.strftime("%Y:%m:%d %H:%M:%S", (t.tm_year, t.tm_mon, t.tm_mday, hour, 0, 0, 0, 0, -1))


def make_exif(model, offset_days, hour, city_idx, iso=100):
    e = Image.Exif()
    e[271] = "Apple"
    e[272] = model
    e[36867] = ts_of(offset_days, hour)
    e[33437] = 2.8
    e[37386] = 26.0
    e[34855] = iso
    name, lat, lon = CITY_GPS[city_idx % len(CITY_GPS)]
    e[0x8825] = {1: "N" if lat >= 0 else "S",
                 2: (abs(lat), random.uniform(2, 25), 0.0),
                 3: "E" if lon >= 0 else "W",
                 4: (abs(lon), random.uniform(2, 25), 0.0)}
    return e, name


def save(img, name, exif=None):
    img.save(os.path.join(OUT, name), exif=exif)


def gradient_bg(w, h, top, bottom, bokeh=0, seed=0):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        f = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * f) for a, b in zip(top, bottom)))
    rng = random.Random(seed)
    for _ in range(bokeh):
        x, y = rng.randint(0, w), rng.randint(0, h)
        r = rng.randint(20, 70)
        v = rng.randint(180, 255)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(v, v, v))
    return img.filter(ImageFilter.GaussianBlur(14))


def draw_person(p, seed, shift=0, w=1400, h=1866):
    """画一张人像。同一个人用同一 seed 与肤色，仅做微小位移。"""
    rng = random.Random(seed)
    base = p["bg"]
    img = gradient_bg(w, h, tuple(int(c * 0.62) for c in base),
                      tuple(min(255, int(c * 1.18)) for c in base), bokeh=26, seed=seed)
    d = ImageDraw.Draw(img)
    hw = p["hw"]
    cx = w // 2 + shift
    # 肩/身体
    d.ellipse([cx - int(430 * hw), 1180, cx + int(430 * hw), 2100], fill=p["top"])
    # 脖子
    d.rectangle([cx - int(85 * hw), 900, cx + int(85 * hw), 1220], fill=p["skin"])
    # 头发（外圈）
    d.ellipse([cx - int(240 * hw), 330, cx + int(240 * hw), 900], fill=p["hair"])
    # 脸
    d.ellipse([cx - int(205 * hw), 390, cx + int(205 * hw), 880], fill=p["skin"])
    # 刘海
    d.ellipse([cx - int(212 * hw), 352, cx + int(212 * hw), 600], fill=p["hair"])
    # 眼睛
    ey = 640
    for sx in (-1, 1):
        ex = cx + sx * int(78 * hw)
        d.ellipse([ex - int(26 * hw), ey - int(16 * hw), ex + int(26 * hw), ey + int(16 * hw)],
                  fill=(38, 34, 34))
    # 嘴
    d.ellipse([cx - int(56 * hw), 770, cx + int(56 * hw), 800], fill=(150, 92, 88))
    return img


n = 0
# ---- 人物：每人 4 张，跨城市跨月份 ----
for pi, p in enumerate(PERSONS):
    for k in range(4):
        img = draw_person(p, seed=100 + pi, shift=[0, 6, -5, 9][k])
        ex, city = make_exif("iPhone 15 Pro", offset_days=pi * 7 + k,
                             hour=[9, 14, 18, 20][k], city_idx=pi + k, iso=[64, 125, 200, 640][k])
        save(img, f"人物_{p['name']}_{k}.jpg", ex)
        n += 1

# ---- 风景：跨城市 ----
for i in range(10):
    img = gradient_bg(1800, 1200, (48 + i * 6, 118, 205), (96, 168, 96), bokeh=0)
    d = ImageDraw.Draw(img)
    d.ellipse([1320, 120, 1440, 240], fill=(255, 248, 214))          # 太阳
    d.polygon([(0, 1200), (620, 620), (1180, 1200)], fill=(70, 92, 74))   # 山
    d.polygon([(700, 1200), (1250, 730), (1800, 1200)], fill=(52, 74, 62))
    ex, _ = make_exif("iPhone 15 Pro", i * 3, 11, city_idx=i, iso=64)
    save(img, f"风景_{i:02d}.jpg", ex)
    n += 1

# ---- 夜景：城市灯光 ----
for i in range(8):
    img = gradient_bg(1800, 1200, (10, 12, 30), (28, 20, 44), bokeh=0)
    d = ImageDraw.Draw(img)
    for _ in range(46):
        x, y = random.randint(0, 1800), random.randint(260, 1200)
        r = random.randint(3, 12)
        col = random.choice([(255, 232, 176), (255, 198, 120), (196, 214, 255)])
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    for x in range(60, 1800, 130):
        d.rectangle([x, 700, x + 84, 1200], fill=(22, 26, 46))
    ex, _ = make_exif("iPhone 15 Pro", 26 + i, 22, city_idx=i + 1, iso=800)
    save(img, f"夜景_{i:02d}.jpg", ex)
    n += 1

# ---- 截图（无相机/无 GPS）----
for i in range(8):
    img = Image.new("RGB", (1440, 900), (250, 250, 252))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1440, 64], fill=(238, 240, 244))
    for y in range(110, 860, 52):
        d.rectangle([60, y, 60 + random.randint(360, 1180), y + 20], fill=(182, 190, 202))
    save(img, f"截图_{i:02d}.png")
    n += 1

# ---- 连拍：3 组 × 4 张 ----
for g in range(3):
    ex0, city = make_exif("iPhone 15 Pro", 54 + g, 15, city_idx=g, iso=125)
    t0 = time.mktime(time.strptime(ex0[36867], "%Y:%m:%d %H:%M:%S"))
    tone = [(150, 170, 210), (196, 168, 132), (128, 156, 140)][g]
    for j in range(4):
        img = gradient_bg(1800, 1200, (tone[0] - 40, tone[1] - 40, tone[2] - 30),
                          tone, bokeh=0)
        d = ImageDraw.Draw(img)
        d.ellipse([760 + j * 7, 420, 1120 + j * 7, 800], fill=(255, 255, 255))
        e = Image.Exif()
        e.load(ex0.tobytes())
        e[36867] = time.strftime("%Y:%m:%d %H:%M:%S", time.localtime(t0 + j * 2))
        save(img, f"连拍_{g}_{j}.jpg", e)
        n += 1

print(f"已生成 {n} 张测试照片 → {os.path.abspath(OUT)}")
