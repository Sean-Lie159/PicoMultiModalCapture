# AGENTS.md — Offline Processing Pipeline (tools/)

> **English first, then 中文.** — 英文在前，中文在后。
>
> This is the development guide for the offline processing pipeline in `tools/`. For the Unity capture app, see the repository-root `AGENTS.md`.
> 这是 `tools/` 下离线处理管线的开发指南。Unity 采集端见仓库根 `AGENTS.md`。

A vibe-coding quick reference for AI assistants (or your future self) taking over this pipeline: how to run it, how to modify it, and pitfalls encountered. Details live in `README.md`.

---

## English

### What this is in one sentence

First-person multimodal data captured by PICO 4 Ultra → offline data-processing / format-conversion pipeline (LeRobot dataset + depth point clouds + skeleton visualization + combined video). **No training, no model inference** — pure data processing.

### How to run

Single-sample pipeline; every script must be given `--input-dir` explicitly:

```powershell
python scripts\01_parse_data.py --input-dir <sample>
python scripts\02_build_lerobot.py --input-dir <sample>
python scripts\03_depth_pointcloud.py --input-dir <sample>      # default light mode
python scripts\04_skeleton_viz.py --input-dir <sample> --view front
python scripts\06_visualize.py --input-dir <sample>
```

Or run the whole thing with `scripts\_process_sample.ps1 -SampleDir <sample>` (add `-SkipDepth` to skip depth).

### Key conventions (read before changing code)

- **Access path constants via module attributes**: use `import _00_common as C` + `C.XXX_DIR`, **not** `from _00_common import X`. `set_input_dir()` re-binds paths at runtime, and `from ... import X` is a value binding that does not update (a known pitfall).
- **Evaluate paths inside functions**: write `C.DEPTH_DIR / "x"` inside function bodies, never bake module-level path constants (otherwise switching samples uses the wrong paths).
- **New scripts** go in `scripts/`; shared topology/coloring goes in `_`-prefixed modules.
- **Windows multiprocessing** must use `mp.get_context("spawn")` + top-level worker functions + an `if __name__ == "__main__"` guard, or it recurses forever.
- The `03` depth script already merges light/full modes (`--mode`), with unified **fixed global range + TURBO + median filter** coloring (removes the per-frame-normalization flicker). To tune the look, edit `_depth_norm` / `_depth_bgr`.

### Pitfalls (quick notes)

- Lost hands: the collector sets hand joints empty + `tracked=False`; rendering that directly "collapses to the origin". `_align.py` fills lost segments using the body Wrist + last valid hand shape (short segments interpolate, long segments extrapolate along the arm).
- `_process_sample.ps1` is blocked under PowerShell's default `Restricted` policy; run it with `-ExecutionPolicy Bypass`.
- Do not put `output/` at the project root; scripts write to `<sample>/output/` by default so parallel samples do not collide.

### Collaboration notes for AI

- Re-`read_file` before editing (the user may have changed the file); don't edit from memory.
- Before processing a new sample, run 01/02 first to check parsing, then proceed.
- For size-sensitive use (upload/backup), prefer light mode; use full mode only when complete point clouds are required (~30× larger output).

---

## 中文

### 项目一句话

PICO 4 Ultra 采集的第一人称多模态数据 → 离线的数据处理/格式转换管线（LeRobot 数据集 + 深度点云 + 骨架可视化 + 合屏视频）。**没有训练、没有模型推断**，纯数据处理。

### 怎么跑

单样例管线，每个脚本都要显式传 `--input-dir`：

```powershell
python scripts\01_parse_data.py --input-dir <样例>
python scripts\02_build_lerobot.py --input-dir <样例>
python scripts\03_depth_pointcloud.py --input-dir <样例>       # 默认 light 模式
python scripts\04_skeleton_viz.py --input-dir <样例> --view front
python scripts\06_visualize.py --input-dir <样例>
```

或用现成脚本一键跑：`scripts\_process_sample.ps1 -SampleDir <样例>`（加 `-SkipDepth` 跳过深度）。

### 关键约定（改代码前必读）

- **路径常量走模块属性**：用 `import _00_common as C` + `C.XXX_DIR`，**不要** `from _00_common import X`。因为 `set_input_dir()` 会动态重绑路径，`from ... import X` 是值绑定，改了不会更新（踩过的坑）。
- **路径必须在函数体内动态求值**：`C.DEPTH_DIR / "x"` 在函数内写，不要模块顶层固化成常量（否则切样例时用错路径）。
- **新脚本**放 `scripts/`，共享拓扑/配色放 `_` 前缀模块。
- **Windows 多进程**必须 `mp.get_context("spawn")` + worker 顶层定义 + `if __name__ == "__main__"` 保护，否则无限递归。
- 03 深度脚本已合并 light/full 两模式（`--mode`），配色统一走**固定全局范围 + TURBO + 中值滤波**（消除逐帧归一化的"闪"）。要改深度观感改 `_depth_norm/_depth_bgr`。

### 踩过的坑（速记）

- 手部丢失：采集端会把手部 joints 置空 + `tracked=False`，直接渲染会"塌缩到原点"。`_align.py` 用身体 Wrist + 有效手形插值/推算填充（短段插值、长段沿臂方向推算）。
- `_process_sample.ps1` 在 PowerShell 默认 `Restricted` 下会被拒，用 `-ExecutionPolicy Bypass` 运行。
- 不要擅自把 `output/` 放项目根，脚本默认写到 `<样例>/output/`，保证多样例并行不冲突。

### 给 AI 的协作建议

- 改动前先 `read_file` 重读（用户可能改过），别凭记忆改。
- 处理新样例前先跑 01/02 看解析是否正常，再往下走。
- 体积敏感场景（要上传/备份）优先 light 模式；要完整点云再 full 模式（体积约 30 倍）。
