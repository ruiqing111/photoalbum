# 照片相册 · PhotoAlbum

> 纯本地、零账号、离线可用的 Windows 照片管理工具。索引和缩略图都放在程序旁边，原图一张都不动。

[![Release](https://img.shields.io/github/v/release/ruiqing111/photoalbum?label=release)](https://github.com/ruiqing111/photoalbum/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/ruiqing111/photoalbum/total)](https://github.com/ruiqing111/photoalbum/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078D4?logo=windows&logoColor=white)](#系统要求)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](#从源码运行)

## 下载即用

[![Download for Windows](https://img.shields.io/badge/Download-Windows%20.exe-2ea44f?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/ruiqing111/photoalbum/releases/latest)

在 [Releases](https://github.com/ruiqing111/photoalbum/releases/latest) 里选择：

| 文件 | 说明 |
|---|---|
| `PhotoAlbum-1.2.2.exe` | 便携版，单文件，**下载后双击直接打开即用**（推荐） |
| `PhotoAlbum-Setup-1.2.2.exe` | 安装版，创建桌面快捷方式与卸载项 |

下载后**双击 exe 直接打开就能用**：单文件、绿色便携，不需要安装 Python、不需要注册账号、不需要联网。
索引、缩略图、回收站等数据全部生成在 exe 同级的 `photoalbum_data/` 目录里；把这个文件夹和 exe 一起拷到移动硬盘或另一台电脑，就能接着用。

> Windows 第一次运行未签名 exe 时会弹 SmartScreen 提示，点「更多信息 → 仍要运行」即可。

想先看看效果，可以导入仓库里的 [`sample_photos/`](sample_photos/)（54 张纯合成演示图，不含任何真实照片）。

## 截图

| 图库 · 网格 | 图库 · 时间线 |
|:---:|:---:|
| ![图库网格](docs/screenshots/01-library-grid.png) | ![图库时间线](docs/screenshots/02-library-timeline.png) |
| 正方形自适应网格、粘性日期分组、画质角标 | 左侧按年月直达，右侧无限流滚动 |

| 表盘视图 | 表盘视图 · 中心放大 |
|:---:|:---:|
| ![表盘视图](docs/screenshots/03-orb-view.png) | ![表盘中心放大](docs/screenshots/04-orb-lens.png) |
| 可拖动的蜂窝照片墙 | 中心自动放大、边缘渐隐，拖到边缘自动加载下一页 |

## 功能特性

**浏览**

- 网格 / 表盘两种布局。网格支持小、中、大三档密度；表盘是类似 Apple Watch 主屏的蜂窝墙，可拖拽、惯性滑动、滚轮缩放，只渲染可视区域，两万张也能一直拖
- 粘性日期分组、年月时间线、无限滚动
- 大图查看器三级渐进加载：小图先上屏 → 中图 → 原图，切换不掉帧
- 视频缩略图与播放，支持非破坏性 90° 旋转（只改显示角度，原文件不动）
- 实况照片自动配对同名 HEIC/JPG + MOV，网格显示「实况」角标

**整理**

- 相册、文件夹、事件、旅行篇、重复照片、隐藏、最近删除
- 批量选择、全选、收藏、标签、重命名、移动、加入相册
- 框选：在选择模式下直接拖出一片区域批量选中
- 三档删除：仅移除索引 / 移入最近删除（默认，30 天自动清理）/ 彻底删除
- 所有操作写入操作日志，`Ctrl+Z` 可撤销，删除后会弹出撤销提示条

**AI 与检索**

- 人物：YuNet 人脸检测 + SFace 特征聚类，单人单照可独立成组，合影单独分组，支持重命名、合并、纠错
- 地点：GPS → 离线城市库（60+ 城市），超出 150km 退回经纬网格
- 旅行：按 GPS + 时间自动聚合行程，精选优先
- 回忆：自动生成月度与地点回忆卡片
- 事物：12+ 内容标签（相机拍摄 / 截图 / 夜景 / 暖冷色调 / 横竖构图 / 高分辨率 / 连拍精选等）
- 搜索：文件名、标签、相机型号；SQLite FTS5 前缀索引；装好 CLIP 后支持自然语言与以图搜图，关键词与语义结果合并展示

**界面**

- 5 种风格：液态玻璃 / 朦胧半透明 / 简洁 / 像素 / 漫画
- 6 种强调色 × 明暗模式（跟随系统 / 浅色 / 深色）
- 风格作用于整个窗口，而不只是弹窗；设置本地持久化

**分享与导出**

- 复制到分享文件夹（重名自动加序号）
- 导出 zip：解压双击 `index.html` 即可离线浏览，带 `manifest.json`

**安全**

- 全本地推理，不联网、不上传
- 索引只存路径和元数据，不复制照片本体
- 编辑、旋转、分享一律生成独立副本，原图保持只读

## 快速开始

1. 双击 exe，点右上角「导入」
2. 在弹窗里点「＋ 添加文件夹」调起系统文件夹选择框（可加多个、支持移动硬盘），再点「开始导入」
3. 点「AI 分析」：打标 → 画质评分 → 连拍精选 → 人物分组 → 地点聚合
4. 左侧入口浏览：概览 / 图库 / 精选 / 人物 / 地点 / 回忆 / 事物 / 收藏
5. 「整理」把筛选出的照片按平铺、按天、按月或按分类复制/剪切到指定文件夹
6. 「分享」导出分享文件夹或离线 HTML 相册包

## 系统要求

- Windows 10 / 11（x64）
- WebView2 运行时（Win11 自带；Win10 若缺失，可按系统提示安装，或用 `--browser` 走浏览器模式）
- 建议把程序放在移动硬盘或本地磁盘的普通目录，不要放 `Program Files`（只读目录会把数据改存到 `%LOCALAPPDATA%`）

## 数据与隐私

- 便携目录：索引、缩略图、回收站都写在 exe 旁的 `photoalbum_data/`，删掉文件夹即彻底清空
- 原图只读：导入不移动、不改名、不复制照片本体，索引里只记录路径
- 最近删除：文件进 `trash/`，30 天自动清理；恢复时不会覆盖同名文件
- 自动备份：启动时清理过期回收站，每周至少备份一次索引，保留 8 份历史
- 多实例保护：同一时间只允许一个窗口，避免多个进程同时读写索引库、抢移动硬盘

## 从源码运行

```powershell
py -3 -m pip install -r requirements.txt
py -3 run.py            # 原生窗口；想用浏览器：py -3 run.py --browser
```

## 架构

```
run.py                一键启动（uvicorn + 原生窗口；--browser 走系统浏览器）
app/config.py         路径与常量（便携数据目录）
app/db.py             SQLite(WAL) 索引、迁移、FTS5 搜索
app/scanner.py        扫描、EXIF/HEIC、缩略图、实况配对、可取消导入
app/analyze.py        一键分析流水线（打标 → 评分 → 精选 → 人物 → 地点）
app/ai.py             启发式打标（+ 可选 CLIP 语义向量）
app/quality.py        Laplacian 画质评分与连拍精选
app/people.py         YuNet 人脸检测 + SFace 特征聚类
app/geo.py            离线城市库与地点聚合
app/library.py        相册、文件夹、重复检测、事件、旅行篇
app/lifecycle.py      三档删除、最近删除、操作日志/撤销、备份与体检
app/editor.py         非破坏性图片编辑（另存副本，原图不动）
app/search.py         查询、统计、概览/回忆/事物/精选
app/exporter.py       离线 HTML 相册包导出
app/extract.py        整理到文件夹（复制/剪切 + 分目录 + 后台进度）
app/server.py         FastAPI 路由与静态资源
web/index.html        页面骨架（含明暗模式引导脚本）
web/theme.js          风格 / 强调色 / 明暗模式
web/orb.js            表盘视图（虚拟化拖动、中心透镜、分页加载）
web/app.js            单页应用主逻辑
web/style.css         设计系统与五套主题
scripts/              测试照片生成、图标生成、模型下载说明
```

技术栈：FastAPI + SQLite(WAL) + Pillow；前端原生 HTML/CSS/JS 单页，无构建步骤、无前端依赖；桌面外壳为 pywebview + Edge WebView2。

## 关于人物识别

- **检测**：OpenCV 自带的 YuNet（`face_detection_yunet_2023mar.onnx`）在 1280px 缩略图上找人脸，一张最多取 6 张；置信度低于 0.92、或人脸短边占比不足画面 7% 的直接丢弃，避免把手办、海报、印刷品当成人
- **特征**：用 YuNet 的 5 个关键点做人脸对齐，SFace（`face_recognition_sface_2021dec.onnx`）提 128 维特征，按余弦相似度聚类（阈值 0.72）
- **分组**：单人单照可以独立成组；同一张照片里出现 ≥2 人时单独归为合影组，不和个人组合并
- **纠错**：人物页支持把照片移出当前组、合并到其他组；特征缓存与算法版本绑定，升级后自动作废旧缓存

模型文件放在 `models/`（已在 `.gitignore` 中排除），可用 `scripts/download_models.py` 获取；
没有模型时人物分析会跳过，不影响其它功能。

## 启用语义搜索（可选）

```powershell
py -3 -m pip install onnxruntime
py -3 scripts/download_models.py   # 查看模型获取方式
py -3 run.py                       # 重启后调用 POST /api/embed 生成向量
```

## 性能

- **导入治理**：每 25 张提交一次事务、导入期只生成小缩略图、批间停顿给机械硬盘留寻道余量；支持随时停止，已入库照片立即可用；连续盘级错误自动熔断，避免把移动硬盘拖到掉线
- **网格增量渲染**：翻页只把新图块追加进网格；日期头按天去重、张数单遍统计
- **渐进式查看器**：小图 → 中图 → 原图逐级替换；换图前摘掉回调，避免重复请求
- **模糊只给大面板**：`backdrop-filter` 只用于侧栏、顶栏、对话框；按钮、搜索框、缩略图角标一律不用
- **表盘只画看得见的**：照片排成一张大平面，只渲染可视范围内的节点，拖到边缘按页加载
- **切换不阻塞**：换布局先渲染占位与转圈，再异步取照片；请求带序号，快速切换时旧响应直接丢弃
- **缓存策略**：缩略图 `max-age=31536000, immutable`；原图 `max-age=86400`

## 构建

单文件便携版：

```powershell
py -3 -m pip install pyinstaller
py -3 -m PyInstaller 照片相册.spec
```

产物 `dist\照片相册.exe`，双击即用、不依赖本机 Python。

安装包（Inno Setup，可选）：

```powershell
winget install JRSoftware.InnoSetup
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

产物 `dist\照片相册_安装包.exe`，`PrivilegesRequired=lowest` 装到用户目录、不弹 UAC；卸载只删索引与缩略图缓存，不动原图。

两个打包要点：

- uvicorn 用字符串 `"app.server:app"` 动态导入，静态分析看不到，spec 里必须显式 `hiddenimports=['app.server']`
- 数据目录会生成在 exe 旁边而不是打包临时目录，所以「exe + photoalbum_data」一起拷走就能换机器

图标由脚本生成，想换配色或图形就改脚本再跑一遍：

```powershell
py -3 scripts/make_icon.py            # 生成 icon.ico
py -3 scripts/make_icon.py out.png    # 顺便导出一张预览图自检
```

## 常见问题

**会不会动我的原图？**
不会。导入只建索引，编辑和旋转另存副本，批量移动会同步修正索引路径，删除默认进 `trash/`。

**导入很慢正常吗？**
机械移动硬盘大量小文件读写在物理上就慢。程序已按批提交、分批停顿、导入期只出小图；可以随时停止，已导入的照片完整可用。

**照片会传到网上吗？**
不会。所有分析都在本地完成，索引和缩略图只在 `photoalbum_data/`。

**能放在移动硬盘上带着走吗？**
可以。把 exe 和 `photoalbum_data/` 放在同一目录，换电脑后直接双击。

**没有网络 / 没有 Python 能跑吗？**
能。下载 Release 里的 exe 双击即可，不依赖 Python 和网络。

## 路线图

- [x] 原生 HEIC 解析与缩略图
- [x] 视频缩略图、播放、非破坏性旋转
- [x] 最近删除 / 操作日志 / 撤销 / 隐藏
- [x] 相册、文件夹、重复检测、事件、旅行篇
- [x] 实况照片配对与播放
- [x] 表盘视图、五套主题与明暗模式
- [x] PyInstaller 单文件打包，绿色便携 exe
- [x] 应用图标 + Inno Setup 安装包
- [ ] 视频转码剪辑（可选打包 ffmpeg，体积约 +60MB）
- [ ] RAW 预览增强
- [ ] 智能相册（规则动态聚合）与自定义封面

## 许可

本项目暂未声明开源许可证。代码公开供学习与个人使用；如需二次分发或商用，请先联系作者。

---

如果这个项目对你有用，欢迎点个 Star 支持一下。
