# 本地 AI 照片相册

纯本地、零账号、离线可用的照片管理工具。界面参考 Apple Photos / Google Photos：
液态玻璃与深色模式、五种可切换风格、自适应网格与可拖动的表盘照片墙、
粘性日期分组、渐进式大图查看器，全部数据只落在程序旁边的 `photoalbum_data/`。

## 快速开始

```powershell
py -3 -m pip install -r requirements.txt
py -3 run.py            # 弹出原生应用窗口；想用浏览器：py -3 run.py --browser
```

不想装 Python，可以直接下 Windows 便携版（单文件 exe）：
[GitHub Releases](https://github.com/ruiqing111/photoalbum/releases/latest) —— exe 与安装包都在里面。

想先看看效果，导入仓库里的 `sample_photos/`（54 张纯合成演示图，不含任何真实照片）。

1. 点右上「导入」，在弹窗里点「＋ 添加文件夹」调起系统文件夹选择框挑目录（可加多个、支持移动硬盘），再点「开始导入」
2. 点「AI 分析」：打标 → 画质评分 → 连拍精选 → 人物分组 → 地点聚合
3. 左侧八个入口浏览：概览 / 图库 / 精选 / 人物 / 地点 / 回忆 / 事物 / 收藏
4. 筛选出要修的照片后点「整理」：把它们复制/剪切到指定文件夹（目标文件夹也能点「选择…」用系统窗口挑；可平铺，也可按天、月、分类分子目录）
5. 点「分享」导出 zip：发给朋友，解压双击 index.html 即可离线浏览

## 功能一览

| 模块 | 说明 |
|---|---|
| 概览 | 统计卡片 + 回忆 Hero + 人物/地点卡片行 + 事物分类 + 最近照片 |
| 图库 | 正方形自适应网格（小/中/大），粘性日期分组，滚动自动加载，无限流 |
| 布局 | 网格 / 表盘两种视图；表盘是可拖动的蜂窝照片墙，中心自动放大、边缘渐隐，拖到边缘会自动加载下一页 |
| 精选 | 连拍最佳 + 画质优秀 + 你的收藏，合并去重并标注入选理由 |
| 人物 | YuNet 人脸检测 + SFace 特征聚类，支持重命名、合并、手动纠错 |
| 地点 | GPS → 离线城市库（60+ 城市）最近匹配，超出 150km 退回经纬网格 |
| 旅行 | 按 GPS + 时间自动聚成旅行篇，精选优先排在前面，可跳地图查看 |
| 回忆 | 自动生成月度回忆与地点回忆卡片 |
| 事物 | 12+ 内容标签：相机拍摄/截图/夜景/暖色调/冷色调/低饱和/横竖构图/高分辨率/连拍精选… |
| 搜索 | 文件名、标签、相机型号；CLIP 就绪后支持自然语言与以图搜图；关键词与语义结果合并展示 |
| 详情 | EXIF（机型/镜头/光圈/快门/ISO）、人物、地点、RGB 直方图、地图链接 |
| 整理 | 复制/剪切到指定文件夹，支持平铺或按天/月/分类分子目录；批量收藏、标签、重命名、加入相册 |
| 相册/文件夹 | 自建相册与按目录浏览；封面自动取第一张；文件夹视图直接对应硬盘目录 |
| 删除与安全网 | 三档删除：仅移除索引 / 移入最近删除（默认，30 天清理）/ 彻底删除；操作日志 + Ctrl+Z 撤销 |
| 隐藏 | 照片可隐藏，默认不出现在图库与搜索里，需要时进「隐藏」页查看 |
| 实况照片 | 自动配对同名的 HEIC/JPG + MOV，网格显示「实况」角标并可播放动态；MOV 同时留在视频页 |
| 视频 | 视频缩略图、播放、非破坏性 90° 旋转（只改显示角度，原文件不动） |
| 主题 | 5 种风格（液态玻璃/朦胧/简洁/像素/漫画）× 6 种强调色 × 明暗（跟随系统/浅色/深色） |
| 分享 | 复制到分享文件夹（重名自动加序号）或打包自包含 HTML 相册包 + manifest.json |
| 隐私 | 全本地推理，数据只在 `photoalbum_data/`，拷走即迁移，删除即清空 |

## 架构

```
run.py                一键启动（uvicorn + 原生窗口；--browser 走系统浏览器）
app/config.py         路径与常量（便携数据目录）
app/db.py             SQLite(WAL) 索引、迁移、FTS5 搜索
app/scanner.py        扫描、EXIF/HEIC、缩略图、实况配对、可取消导入
app/analyze.py        一键分析流水线（打标 → 评分 → 精选 → 人物 → 地点）
app/ai.py             启发式打标（+可选 CLIP 语义向量）
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

## 性能与体验

- **导入治理**：每 25 张提交一次事务、导入期只生成小缩略图、批间停顿给机械硬盘留寻道余量；支持随时停止，已入库的照片立即可用；连续盘级错误会自动熔断，避免把移动硬盘拖到掉线
- **单实例保护**：同一时间只允许一个窗口，避免多个进程同时读写索引库、抢盘
- **网格增量渲染**：翻页只把新图块 `insertAdjacentHTML` 追加进网格，不再重建整张网格；日期头按天去重、张数单遍统计
- **渐进式查看器**：小图先上屏，再换中图，最后换原图；换图前先摘掉回调，避免原图 `onload` 再次触发导致重复请求
- **模糊只给大面板**：`backdrop-filter` 只用于侧栏、顶栏、对话框；按钮、搜索框、缩略图角标一律不用 —— 一屏几十个实时模糊是 WebView2 掉帧的主因
- **表盘视图只画看得见的**：照片按行排成一张大平面，只渲染可视范围内的节点；拖动到边缘按页加载，两万张也能一直拖下去
- **切换不阻塞**：换布局先渲染占位与转圈，再异步取照片；请求带序号，快速切换时旧响应直接丢弃
- **缓存策略**：缩略图 `max-age=31536000, immutable`；原图 `max-age=86400`

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

## 技术栈

FastAPI + SQLite(WAL) + Pillow；前端原生 HTML/CSS/JS 单页，无构建步骤、无前端依赖；
桌面外壳用 pywebview + Edge WebView2（Windows 自带 Chromium 内核，无需额外安装运行时）。

## 打包成单文件 exe（可选）

```powershell
py -3 -m pip install pyinstaller
py -3 -m PyInstaller --noconfirm --onefile --noconsole --name 照片相册 --add-data "web;web" `
  --collect-all webview --collect-all clr_loader --collect-all pythonnet `
  --collect-submodules app --hidden-import app --hidden-import app.server `
  --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan.on run.py
```

产物是 `dist\照片相册.exe`，双击即用、不依赖本机 Python。之后重打包可直接
`py -3 -m PyInstaller 照片相册.spec`。

两个要点：
- uvicorn 是用字符串 `"app.server:app"` 动态导入的，静态分析看不到，所以必须显式
  `--hidden-import app.server`，否则 exe 一启动就报 `No module named 'app'`。
- 数据目录 `photoalbum_data/` 会生成在 **exe 旁边**（不是打包进 exe 的临时目录里），
  所以「exe + photoalbum_data 文件夹」一起拷走就能换机器用；删掉文件夹就是全新开始。
  若 exe 被放在只读目录（如 Program Files），数据会自动落到 `%LOCALAPPDATA%`。

## 图标

`icon.ico`（16/32/48/64/128/256 六个尺寸）由脚本生成；想换配色或图形就改脚本再跑一遍：

```powershell
py -3 scripts/make_icon.py            # 生成 icon.ico
py -3 scripts/make_icon.py out.png    # 顺便导出一张预览图自检
```

打包时 spec 里的 `icon='icon.ico'` 会自动把它塞进 exe，安装包也拿它当程序图标。

## 做可分发的安装包

给别人发的不是 exe，而是 `dist\照片相册_安装包.exe`：双击就装，自动创建**桌面快捷方式**和开始菜单项，装完能直接启动，控制面板里也能正常卸载（卸载只删索引与缩略图缓存，不动你的原图）。

```powershell
winget install JRSoftware.InnoSetup      # 装一次 Inno Setup
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

产物 `dist\照片相册_安装包.exe` 一个文件发出去即可，对方不需要装 Python，也不需要 WebView2 运行时（Win10/11 自带）。

几个要点：
- `PrivilegesRequired=lowest` → 装到 `%LOCALAPPDATA%\Programs\照片相册`，**不弹 UAC**，普通用户权限就能装
- 免安装玩法：直接把 `dist\照片相册.exe` 和 `photoalbum_data\` 一起拷到 U 盘/移动硬盘，exe 在哪儿数据就在哪儿
- `AppId` 是升级与卸载的身份证，发新版不要改；改了会被当成另一个软件
- 中文安装界面来自项目根目录的 `ChineseSimplified.isl`：Inno Setup 官方发行版不带中文，这份是从官方仓库的非官方翻译取的，随项目一起带上

## 路线图

- [x] 原生 HEIC 解析与缩略图
- [x] 视频缩略图、播放、非破坏性旋转
- [x] 最近删除 / 操作日志 / 撤销 / 隐藏
- [x] 相册、文件夹、重复检测、事件、旅行篇
- [x] 实况照片配对与播放
- [x] 环形布局、五套主题与明暗模式
- [ ] 视频转码剪辑（可选打包 ffmpeg，体积约 +60MB）
- [ ] RAW 预览增强
- [ ] 智能相册（规则动态聚合）与自定义封面
- [x] PyInstaller 单文件打包，真正的绿色便携 exe
- [x] 应用图标 + Inno Setup 安装包（桌面快捷方式、卸载项）
