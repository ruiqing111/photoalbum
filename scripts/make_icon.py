"""生成应用图标 icon.ico（多尺寸）。用法：py -3 scripts/make_icon.py [预览图输出路径]"""
import os
import sys

from PIL import Image, ImageDraw

S = 256
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icon.ico")


def rounded_gradient(size):
    """蓝紫渐变 + 圆角方形底。"""
    grad = Image.new("RGB", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / (size - 1)
        gd.line([(0, y), (size, y)],
                fill=(int(10 + (104 - 10) * t), int(132 + (86 - 132) * t), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=int(size * 0.22), fill=255)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    return img


def draw_glyph(img):
    """白色相框 + 太阳 + 两座山。"""
    k = img.width / 256.0
    d = ImageDraw.Draw(img)
    w = lambda v: v * k
    # 相框
    d.rounded_rectangle([w(58), w(66), w(198), w(192)], radius=w(20),
                        outline=(255, 255, 255, 240), width=int(round(w(11))))
    # 太阳
    d.ellipse([w(86), w(88), w(114), w(116)], fill=(255, 255, 255, 240))
    # 山
    d.polygon([(w(74), w(180)), (w(116), w(126)), (w(158), w(180))], fill=(255, 255, 255, 240))
    d.polygon([(w(136), w(180)), (w(166), w(142)), (w(188), w(180))], fill=(255, 255, 255, 200))
    return img


def main():
    base = draw_glyph(rounded_gradient(S))
    sizes = [256, 128, 64, 48, 32, 16]
    frames = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[0].save(OUT, format="ICO", sizes=[(s, s) for s in sizes])
    print("icon ->", OUT)
    if len(sys.argv) > 1:
        preview = os.path.join(sys.argv[1])
        base.save(preview)
        print("preview ->", preview)


if __name__ == "__main__":
    main()
