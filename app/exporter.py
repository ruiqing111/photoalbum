"""分享导出：生成离线 HTML 相册包（可压缩成 zip 直接发送）。"""
import json
import os
import shutil
import time

from PIL import Image, ImageOps

from . import db
from .config import EXPORT_DIR

HTML_TEMPLATE = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{margin:0;background:#111;color:#eee;font-family:system-ui}}
header{{padding:16px 20px;font-size:18px;position:sticky;top:0;background:#111c}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px;padding:10px}}
.grid figure{{margin:0;cursor:pointer}}
.grid img{{width:100%;height:180px;object-fit:cover;border-radius:6px}}
#view{{position:fixed;inset:0;background:#000d;display:none;align-items:center;justify-content:center;flex-direction:column}}
#view img{{max-width:92vw;max-height:82vh}}
#view .meta{{padding:10px;font-size:13px;color:#aaa;text-align:center}}
</style></head><body>
<header>{title} · 共 {count} 张 · 本地离线相册</header>
<div class="grid">{figures}</div>
<div id="view" onclick="this.style.display='none'"><img id="big"><div class="meta" id="meta"></div></div>
<script>
const DATA={data};
function show(i){{const d=DATA[i];document.getElementById('big').src='images/'+d.f;
document.getElementById('meta').textContent=[d.f,d.t,d.cam].filter(Boolean).join(' · ');
document.getElementById('view').style.display='flex';}}
</script></body></html>"""


def export_pack(photo_ids=None, name=None, max_side=1600, quality=80):
    """导出相册包：缩放图片 + 离线 HTML 查看器 + manifest.json，返回 zip 路径。"""
    if photo_ids:
        marks = ",".join("?" * len(photo_ids))
        rows = db.q(f"SELECT * FROM photos WHERE id IN ({marks})", photo_ids)
    else:
        rows = db.q("SELECT * FROM photos WHERE kind='photo' ORDER BY taken_at DESC")
    if not rows:
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    title = name or f"相册分享_{stamp}"
    out = os.path.join(EXPORT_DIR, f"share_{stamp}")
    img_dir = os.path.join(out, "images")
    os.makedirs(img_dir, exist_ok=True)
    data, figures = [], []
    for i, r in enumerate(rows):
        fn = f"{i:04d}_{r['name']}"
        fn = os.path.splitext(fn)[0] + ".jpg"
        dst = os.path.join(img_dir, fn)
        try:
            img = Image.open(r["path"])
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((max_side, max_side))
            img.save(dst, "JPEG", quality=quality)
        except Exception:
            continue
        t = time.strftime("%Y-%m-%d", time.localtime(r["taken_at"] or 0))
        cam = " ".join(x for x in (r["camera_make"], r["camera_model"]) if x)
        data.append({"f": fn, "t": t, "cam": cam})
        figures.append(f'<figure onclick="show({i})"><img loading="lazy" src="images/{fn}"></figure>')
    html = HTML_TEMPLATE.format(title=title, count=len(data),
                                figures="".join(figures), data=json.dumps(data, ensure_ascii=False))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"title": title, "count": len(data),
                   "created": stamp, "photos": data}, f, ensure_ascii=False, indent=2)
    zip_path = shutil.make_archive(out, "zip", out)
    return {"dir": out, "zip": zip_path, "count": len(data), "title": title}
