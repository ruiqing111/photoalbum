"""路径与常量配置。便携模式：所有数据放在程序目录下的 photoalbum_data/。"""
import os
import sys

FROZEN = bool(getattr(sys, "frozen", False))
# 打包成单文件 exe 后，代码被解到临时目录，而数据必须落在 exe 旁边才不会随退出丢失
APP_DIR = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN \
    else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)     # 只读资源目录，web/ 在这里


def _data_dir():
    d = os.path.join(APP_DIR, "photoalbum_data")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:                                # exe 放在只读目录（如 Program Files）时的兜底
        return os.path.join(os.environ.get("LOCALAPPDATA", APP_DIR), "photoalbum_data")


BASE_DIR = BUNDLE_DIR
WEB_DIR = os.path.join(BUNDLE_DIR, "web")
DATA_DIR = os.environ.get("PHOTOALBUM_DATA") or _data_dir()
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
# 编辑另存的副本：只写这里，原照片所在目录一个文件都不碰
EDITS_DIR = os.path.join(DATA_DIR, "edits")
MODEL_DIR = os.path.join(DATA_DIR, "models")
# 回收站：默认删除把原文件移到这里（与数据同盘，基本是瞬时的 rename），
# 30 天内可恢复；彻底删除才真正从磁盘抹掉
TRASH_DIR = os.path.join(DATA_DIR, "trash")
# 索引库定期快照：每周/每次大操作前留一份，出问题能回退
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
# 随程序打包的模型（人脸检测/识别），只读；用户也可以把自己的模型放进 DATA_DIR/models 覆盖
BUNDLE_MODEL_DIR = os.path.join(BUNDLE_DIR, "models")
DB_PATH = os.path.join(DATA_DIR, "album.db")

for d in (DATA_DIR, THUMB_DIR, EXPORT_DIR, EDITS_DIR, MODEL_DIR, TRASH_DIR, BACKUP_DIR):
    os.makedirs(d, exist_ok=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

THUMB_SIZES = {"s": 320, "m": 1280}
