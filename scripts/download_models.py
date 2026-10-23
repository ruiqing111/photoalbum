"""下载 CLIP ONNX 模型，启用语义搜索与智能打标（可选，一次性）。

用法: py -3 scripts/download_models.py
下载后重启相册即可自动启用（状态见 /api/ai/status）。

模型来源可选：
1) 自行用 optimum 导出:  optimum-cli export onnx --model openai/clip-vit-base-patch32 photoalbum_data/models/clip
2) 或从 HuggingFace 下载社区已导出的 ONNX（搜索 "clip-vit-base-patch32 onnx"）。
需要两个文件：
  photoalbum_data/models/clip_image.onnx   (输入 1x3x224x224 float32, 输出 512 维向量)
  photoalbum_data/models/clip_text.onnx    (输入 1x77 int64 token ids, 输出 512 维向量)
另需安装: py -3 -m pip install onnxruntime
"""
import os
import sys

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "photoalbum_data", "models")
print(__doc__)
print("模型目录:", os.path.abspath(MODEL_DIR))
need = ["clip_image.onnx", "clip_text.onnx"]
missing = [f for f in need if not os.path.exists(os.path.join(MODEL_DIR, f))]
print("缺失文件:", missing if missing else "无，CLIP 已就绪")
try:
    import onnxruntime  # noqa
    print("onnxruntime: 已安装")
except ImportError:
    print("onnxruntime: 未安装，请运行  py -3 -m pip install onnxruntime")
sys.exit(0 if not missing else 1)
