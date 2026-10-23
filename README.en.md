# PhotoAlbum

> A fully local, account-free, offline photo manager for Windows. The index and thumbnails live next to the executable — your original photos are never touched.

[![Release](https://img.shields.io/github/v/release/ruiqing111/photoalbum?label=release)](https://github.com/ruiqing111/photoalbum/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/ruiqing111/photoalbum/total)](https://github.com/ruiqing111/photoalbum/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078D4?logo=windows&logoColor=white)](#requirements)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](#run-from-source)

**简体中文：[README.md](README.md)**

## Download and run

[![Download for Windows](https://img.shields.io/badge/Download-Windows%20.exe-2ea44f?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/ruiqing111/photoalbum/releases/latest)

On the [Releases](https://github.com/ruiqing111/photoalbum/releases/latest) page:

| File | Description |
|---|---|
| `PhotoAlbum-1.2.2.exe` | Portable build — single file, **double-click to run** (recommended) |
| `PhotoAlbum-Setup-1.2.2.exe` | Installer with desktop shortcut and uninstall entry |

No Python, no account, no network required. The index, thumbnails and trash are created in `photoalbum_data/` next to the executable — copy the folder together with the exe to a portable drive or another PC and keep going.

> The exe is unsigned, so Windows SmartScreen may warn on first launch. Choose **More info → Run anyway**.
>
> Want to try it first? Import [`sample_photos/`](sample_photos/) — 54 fully synthetic demo images with no real photos or personal data.

## Screenshots

> Screenshots use a demo library: synthetic scenes plus the author's own photos, with no third-party assets.

| Library · grid | Library · timeline |
|:---:|:---:|
| ![Library grid](docs/screenshots/01-library-grid.png) | ![Library timeline](docs/screenshots/02-library-timeline.png) |
| Adaptive square grid, sticky date sections, quality scores | Jump to any year/month on the left, infinite scrolling on the right |

| Watch-face view | Watch-face view · center lens |
|:---:|:---:|
| ![Watch-face view](docs/screenshots/03-orb-view.png) | ![Center lens](docs/screenshots/04-orb-lens.png) |
| A draggable honeycomb photo wall | Center auto-enlarges, edges fade out, paging at the edges |

## Features

**Browsing**

- Grid and watch-face layouts. Grid supports small / medium / large density; the watch-face view is a draggable honeycomb wall with inertia and wheel zoom, rendering only visible nodes — it stays smooth with 20k+ photos
- Sticky date sections, year/month timeline, infinite scroll
- Three-stage progressive viewer: small thumb → medium → original, no flicker when switching
- Video thumbnails and playback, non-destructive 90° rotation (display angle only)
- Live Photo pairing of HEIC/JPG + MOV with a badge in the grid

**Organizing**

- Albums, folders, events, trips, duplicates, hidden, recently deleted
- Batch select, select all, favorite, tag, rename, move, add to album
- Marquee selection: drag a rectangle in selection mode to pick many photos
- Three deletion modes: index-only / move to trash (default, 30-day cleanup) / permanent delete
- Every operation is logged; `Ctrl+Z` undo with an undo toast

**AI and search**

- People: YuNet face detection + SFace feature clustering; single-person single-photo groups allowed; group photos are kept separate; rename, merge and manual correction
- Places: GPS → offline city database (60+ cities), grid fallback beyond 150 km
- Trips: automatic GPS + time clustering, curated highlights first
- Memories: monthly and place-based memory cards
- Things: 12+ content tags (camera, screenshot, night, warm/cool tone, orientation, high resolution, burst picks…)
- Search: filename, tags, camera model; SQLite FTS5 prefix index; optional CLIP for natural language and image-to-image search, merged with keyword results

**Interface**

- 5 styles: liquid glass / frosted translucent / minimal / pixel / comic
- 6 accent colors × light/dark/system theme, applied to the whole window and persisted locally

**Sharing and export**

- Copy to a share folder (auto-numbered duplicates) or export a self-contained offline HTML album with `manifest.json`

**Safety**

- All inference is local; nothing is uploaded
- The index stores paths and metadata only — photos are never copied into the library
- Edits, rotations and shares always create separate copies; originals stay read-only

## Quick start

1. Double-click the exe and click **Import**
2. Choose one or more folders (external drives supported), then **Start import**
3. Click **AI analysis**: tagging → quality scoring → burst picks → people → places
4. Browse from the left: Overview / Library / Curated / People / Places / Memories / Things / Favorites
5. **Organize** copies or moves selected photos into a target folder, flat or grouped by day/month/category
6. **Share** exports a share folder or an offline HTML album

## Requirements

- Windows 10 / 11 (x64)
- WebView2 runtime (included in Windows 11; install it on Windows 10 if missing, or run with `--browser`)
- Avoid `Program Files` (read-only directories redirect data to `%LOCALAPPDATA%`)

## Data and privacy

- Portable data directory: index, thumbnails and trash under `photoalbum_data/` next to the exe; delete the folder to wipe everything
- Originals are read-only: nothing is moved, renamed or copied during import
- Trash: files go to `trash/`, auto-cleaned after 30 days; restoring never overwrites an existing file
- Automatic backups: expired trash cleaned at startup, index backed up at least weekly, 8 historical copies kept
- Single-instance guard: only one window at a time, preventing concurrent index writes and disk contention

## Run from source

```powershell
py -3 -m pip install -r requirements.txt
py -3 run.py            # native window; use --browser for a browser tab
```

## Architecture

```
run.py                launcher (uvicorn + native window; --browser for a tab)
app/config.py         paths and constants (portable data directory)
app/db.py             SQLite(WAL) index, migrations, FTS5 search
app/scanner.py        scanning, EXIF/HEIC, thumbnails, Live Photo pairing, cancellable import
app/analyze.py        analysis pipeline (tags → score → curate → people → places)
app/ai.py             heuristic tagging (+ optional CLIP embeddings)
app/quality.py        Laplacian quality scoring and burst picks
app/people.py         YuNet detection + SFace clustering
app/geo.py            offline city database and place grouping
app/library.py        albums, folders, duplicates, events, trips
app/lifecycle.py      deletion modes, trash, operation log/undo, backups
app/editor.py         non-destructive editing (separate copies)
app/search.py         queries, stats, overview/memories/things/curated
app/exporter.py       offline HTML album export
app/extract.py        organize into folders (copy/move, subfolders, progress)
app/server.py         FastAPI routes and static assets
web/                  vanilla HTML/CSS/JS single-page frontend (no build step)
scripts/              demo photo generator, icon generator, model download notes
```

Stack: FastAPI + SQLite(WAL) + Pillow; vanilla HTML/CSS/JS frontend; desktop shell via pywebview + Edge WebView2.

## People recognition

- **Detection**: OpenCV YuNet (`face_detection_yunet_2023mar.onnx`) on 1280 px thumbnails, up to 6 faces per photo; confidence < 0.92 or face shorter side < 7% of the frame is discarded
- **Features**: 5-point alignment + SFace (`face_recognition_sface_2021dec.onnx`) 128-d embeddings, cosine clustering at 0.72
- **Grouping**: a single person in a single photo can form a group; photos with ≥2 people go to a separate group-photo cluster
- **Correction**: move photos out of a group or merge groups; feature caches are versioned and invalidated on algorithm updates

Models live in `models/` (git-ignored); see `scripts/download_models.py`. Without models, people analysis is skipped and everything else works.

## Optional semantic search

```powershell
py -3 -m pip install onnxruntime
py -3 scripts/download_models.py   # see how to obtain the models
py -3 run.py                       # restart, then POST /api/embed to generate vectors
```

## Performance

- **Import governance**: commit every 25 photos, small thumbnails only during import, pauses between batches for spinning disks; stop anytime and imported photos remain usable; automatic circuit breaker on repeated disk errors
- **Incremental grid**: only new tiles are appended; date headers deduplicated in a single pass
- **Progressive viewer**: small → medium → original; callbacks detached before swapping to avoid duplicate requests
- **Blur only on large panels**: `backdrop-filter` only on sidebar, top bar and dialogs
- **Watch-face virtualization**: only visible nodes are rendered; paging at the edges
- **Non-blocking switches**: render placeholder first, then fetch; stale responses discarded by request sequence
- **Caching**: thumbnails `max-age=31536000, immutable`; originals `max-age=86400`

## Build

Portable single-file exe:

```powershell
py -3 -m pip install pyinstaller
py -3 -m PyInstaller 照片相册.spec
```

Installer (optional, Inno Setup):

```powershell
winget install JRSoftware.InnoSetup
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

The installer uses `PrivilegesRequired=lowest` (no UAC) and never deletes original photos on uninstall.

## FAQ

**Does it modify my originals?**
No. Import only indexes; edits and rotations save separate copies; moves update index paths; deletion goes to `trash/` by default.

**Why is importing slow?**
Many small files on a spinning external drive are physically slow. Imports commit in batches, pause between them and only generate small thumbnails; stop anytime and imported photos stay usable.

**Is anything uploaded?**
No. All analysis runs locally; index and thumbnails stay in `photoalbum_data/`.

**Can I run it from an external drive?**
Yes. Keep the exe and `photoalbum_data/` together and double-click on any PC.

**No Python or network?**
Not needed. Download the exe from Releases and double-click.

## Roadmap

- [x] Native HEIC decoding and thumbnails
- [x] Video thumbnails, playback, non-destructive rotation
- [x] Trash / operation log / undo / hidden
- [x] Albums, folders, duplicates, events, trips
- [x] Live Photo pairing and playback
- [x] Watch-face view, five themes and light/dark mode
- [x] PyInstaller single-file portable exe
- [x] App icon + Inno Setup installer
- [ ] Optional ffmpeg transcoding/trimming (+60 MB)
- [ ] Better RAW preview
- [ ] Smart albums and custom covers

## License

No open-source license is declared yet. The code is public for learning and personal use; contact the author before redistribution or commercial use.
