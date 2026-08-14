# PICO MultiModal Capture — Offline Processing Pipeline

> **English first, then 中文.** — 英文在前，中文在后。

Offline post-processing scripts for the data captured by [PicoMultiModalCapture](../README.md) (PICO 4 Ultra first-person multimodal capture: `data.json / data.csv / meta.json / video.mp4`). Pure offline data processing — no training, no model inference.

Outputs: LeRobot-standard dataset, stereo SGBM depth and colored point clouds, 3D motion-capture skeleton, and RGB+skeleton combined video.

---

## English

### Dependencies & Setup

Python 3.10+ (verified on 3.14).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r scripts\requirements.txt
```

### Scripts & Execution Order

All scripts live in `scripts/`, and take the input sample directory via `--input-dir`.

| Script | Purpose | Key output |
|---|---|---|
| `01_parse_data.py` | Parse `data.json` (fix `:F(\d)` non-standard floats) + cross-check against `data.csv` | `output/_intermediate/pose_clean.{json,csv}` |
| `02_build_lerobot.py` | Normalize to LeRobot v2.1 format (parquet + isomorphic json) | `output/lerobot/` |
| `03_depth_pointcloud.py` | Stereo SGBM depth + colored point clouds (light / full modes) | `output/depth/`, `output/pointcloud/` |
| `04_skeleton_viz.py` | Body 24-joint + hands 26×2-joint motion-capture skeleton visualization | `output/skeleton/` |
| `06_visualize.py` | RGB + 3D skeleton combined video | `output/vis/combined.mp4` |

Recommended order (single sample):

```powershell
python scripts\01_parse_data.py --input-dir <sample>
python scripts\02_build_lerobot.py --input-dir <sample>
python scripts\03_depth_pointcloud.py --input-dir <sample>     # light mode (default)
python scripts\04_skeleton_viz.py --input-dir <sample> --view front
python scripts\06_visualize.py --input-dir <sample>
```

Or run the whole pipeline with `scripts\_process_sample.ps1` (`-SkipDepth` skips depth):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\_process_sample.ps1 -SampleDir <sample>
```

### 03 Depth / Point Cloud: light vs full

`03_depth_pointcloud.py` provides both modes in one script (`--mode light|full`, default `light`).

**light (default)** — depth/point cloud only for the first/middle/last 3 pose frames, plus a depth video covering the full duration:
- Outputs: `depth/frame_{first|mid|last}.{npy,png}` + `depth/depth_video.mp4`, `pointcloud/frame_{first|mid|last}.ply` + `pointcloud/preview.png`
- Small and fast; good for quick acceptance.

**full** — per-frame `npy/png/ply` for all pose frames, plus an aggregated world `aggregated_world.ply`:
- Outputs: all `depth/frame_*.{npy,png}`, `pointcloud/frames/frame_*.ply`, `pointcloud/aggregated_world.ply`
- Measured on a ~10000-frame sample: output about **90 GB** (light only ~3 GB, ~30× smaller), and noticeably slower (full 03 ~490s; whole pipeline 20+ minutes).

```powershell
python scripts\03_depth_pointcloud.py --input-dir <sample> --mode light
python scripts\03_depth_pointcloud.py --input-dir <sample> --mode full --step 3 --voxel 0.02
```

**Depth coloring** (shared by light/full): fixed global depth range (auto p2~p98 percentile) + TURBO colormap + median-filter smoothing, eliminating the frame-to-frame color flicker caused by per-frame normalization. Common options:

| Option | Description | Default |
|---|---|---|
| `--depth-near / --depth-far` | Fixed depth range (m); otherwise auto-estimated | auto |
| `--colormap` | Colormap `turbo` / `jet` | `turbo` |
| `--no-smooth` / `--smooth-k` | Disable median smoothing / kernel size | on / 5 |
| `--num-scale` | SGBM resolution scale (smaller = faster) | 0.5 |
| `--step` (full) | Process 1 frame every N | 1 |
| `--frames` (full) | Process only given frames | - |

### Output Layout

```
<sample>/output/
├── lerobot/                  # LeRobot dataset
│   ├── meta/{info.json, tasks.jsonl, stats.json}
│   ├── data/chunk-000/episode_000000.{parquet,json}
│   └── videos/chunk-000/
├── depth/                    # depth frame_XXXXXX.{npy,png} + depth_video.mp4
├── pointcloud/
│   ├── frames/               # per-frame colored point clouds frame_XXXXXX.ply
│   └── aggregated_world.ply  # world aggregated point cloud (full mode)
├── skeleton/                 # skeleton animation MP4
├── vis/combined.mp4          # RGB + skeleton combined
└── _intermediate/            # cleaned intermediate pose data
```

### Technical Notes & Known Limitations

- Depth/point clouds come from **stereo SGBM matching**: `depth = fx * baseline / disparity`, intrinsics/baseline read from `meta.json` (baseline ≈ 6.4 cm).
- Camera→world transform approximates the camera pose by the per-frame head pose. Since head is the "eye" pose rather than the optical center, and the SDK does not export lens distortion, there is a systematic error near edges.
- When a hand leaves the camera view, the collector sets `hands.*.joints` to empty with `tracked=False`. `_align.py` fills the lost segments by interpolating / extrapolating using the body Wrist position and the last valid hand shape, so the skeleton hand does not "collapse to the origin".
- LeRobot columns: `timestamp, frame_index, episode_index, task_index` + `observation.*` (head/body/left_hand/right_hand, 7 values each) + `action` (isomorphic to the skeleton, reserved for retargeting).

---

## 中文

### 依赖与安装

Python 3.10+（本项目在 3.14 下实测）。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r scripts\requirements.txt
```

### 脚本与执行顺序

所有脚本放到 `scripts/`，通过 `--input-dir <样例目录>` 指定输入。

| 脚本 | 作用 | 关键产物 |
|---|---|---|
| `01_parse_data.py` | 解析 `data.json`（修复 `:F(\d)` 非标准浮点）+ 与 `data.csv` 交叉校验 | `output/_intermediate/pose_clean.{json,csv}` |
| `02_build_lerobot.py` | 规范化为 LeRobot v2.1 标准格式（parquet + 同构 json） | `output/lerobot/` |
| `03_depth_pointcloud.py` | 双目 SGBM 深度重建 + 彩色点云（light/full 两种模式） | `output/depth/`、`output/pointcloud/` |
| `04_skeleton_viz.py` | 身体 24 关节 + 双手 26×2 关节动捕骨架可视化 | `output/skeleton/` |
| `06_visualize.py` | RGB + 3D 骨架合屏可视化 | `output/vis/combined.mp4` |

推荐执行顺序（单样例）：

```powershell
python scripts\01_parse_data.py --input-dir <样例>
python scripts\02_build_lerobot.py --input-dir <样例>
python scripts\03_depth_pointcloud.py --input-dir <样例>          # light 模式（默认）
python scripts\04_skeleton_viz.py --input-dir <样例> --view front
python scripts\06_visualize.py --input-dir <样例>
```

也可用 `scripts\_process_sample.ps1` 一键跑完整管线（`-SkipDepth` 跳过深度）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\_process_sample.ps1 -SampleDir <样例绝对路径>
```

### 03 深度/点云：light 与 full 模式

`03_depth_pointcloud.py` 一套脚本提供两种模式（`--mode light|full`，默认 light）。

**light（默认）**——只对首/中/末 3 个位姿帧做深度与点云，并生成一个覆盖全时长的深度视频：
- 产物：`depth/frame_{首|中|末}.{npy,png}` + `depth/depth_video.mp4`、`pointcloud/frame_{首|中|末}.ply` + `pointcloud/preview.png`
- 体积小、速度快，适合快速验收。

**full**——逐帧处理全部位姿帧的 `npy/png/ply`，并聚合出世界系 `aggregated_world.ply`：
- 产物：全部 `depth/frame_*.{npy,png}`、`pointcloud/frames/frame_*.ply`、`pointcloud/aggregated_world.ply`
- 以 10000 位姿帧样例实测：输出约 **90 GB**（light 仅约 3 GB，相差约 30 倍），耗时显著更长（03 全量约 490s，全管线约 20 分钟以上）。

```powershell
python scripts\03_depth_pointcloud.py --input-dir <样例> --mode light
python scripts\03_depth_pointcloud.py --input-dir <样例> --mode full --step 3 --voxel 0.02
```

**深度配色**（light/full 通用）：固定全局深度范围（自动统计 p2~p98 百分位）+ TURBO 色带 + 中值滤波平滑，消除逐帧独立归一化导致的帧间颜色漂移闪烁。常用参数：

| 参数 | 说明 | 默认 |
|---|---|---|
| `--depth-near / --depth-far` | 固定深度范围（米），否则自动统计 | 自动 |
| `--colormap` | 色带 `turbo` / `jet` | `turbo` |
| `--no-smooth` / `--smooth-k` | 关闭深度中值滤波 / 滤波核尺寸 | 开 / 5 |
| `--num-scale` | SGBM 分辨率缩放（越小越快） | 0.5 |
| `--step`（full） | 抽帧，每 N 帧处理 1 帧 | 1 |
| `--frames`（full） | 只处理指定帧 | - |

### 输出目录

```
<样例>/output/
├── lerobot/                  # LeRobot 标准数据集
│   ├── meta/{info.json, tasks.jsonl, stats.json}
│   ├── data/chunk-000/episode_000000.{parquet,json}
│   └── videos/chunk-000/
├── depth/                    # 深度 frame_XXXXXX.{npy,png} + depth_video.mp4
├── pointcloud/
│   ├── frames/               # 逐帧彩色点云 frame_XXXXXX.ply
│   └── aggregated_world.ply  # 世界系聚合点云（full 模式）
├── skeleton/                 # 骨架动捕动画 MP4
├── vis/combined.mp4          # RGB + 骨架合屏
└── _intermediate/            # 清洗后的中间位姿数据
```

### 技术说明与已知边界

- 深度/点云来自**双目 SGBM 立体匹配**：`depth = fx * baseline / disparity`，内参/基线取自 `meta.json`（baseline≈6.4cm）。
- 相机系→世界系用每帧 head 位姿近似。因 head 是"眼睛"位姿而非相机光心、且 SDK 未导出畸变系数，边缘存在系统性误差。
- 采集端在手部离开摄像头视野时会把 `hands.*.joints` 置为空并 `tracked=False`。`_align.py` 会对丢失段用身体 Wrist 位置 + 最近有效手形插值/推算填充，保证骨架视频手部不"塌缩到原点"。
- LeRobot 列结构：`timestamp, frame_index, episode_index, task_index` + `observation.*`（head/body/left_hand/right_hand，各 7 元组）+ `action`（与骨骼同构，预留重定向输出）。

---

## License / 许可证

MIT License (see [LICENSE](../LICENSE)).
本项目采用 MIT License（见 [LICENSE](../LICENSE)）。
