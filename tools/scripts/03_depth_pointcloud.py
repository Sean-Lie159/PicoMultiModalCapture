# -*- coding: utf-8 -*-
"""
03_depth_pointcloud.py — 双目 SGBM 深度重建 + 彩色点云（一套脚本，light/full 两种模式）。

流程（对每一帧）：
  1. 从 video.mp4 取帧，切分左/右眼（2560x720 SBS -> 每眼 1280x720）
  2. 灰度化 + OpenCV SGBM 立体匹配 -> 视差图
  3. 用 meta.json 内参(fx/fy/cx/cy) 与基线(baseline) 换算米制深度：depth = fx*baseline/disparity
  4. 反投影得到相机系 3D 点，用左眼 RGB 着色 -> 彩色点云 .ply
  5. 深度可视化（TURBO 色带，固定全局范围 + 中值滤波平滑）
  6. 用每帧 head 位姿把相机系点云变换到世界系

模式（--mode，默认 light）：
  - light（默认）：只处理首/中/末 3 个位姿帧的 npy/png/ply + 生成深度视频
    depth_video.mp4 + 点云预览 preview.png。体积小、速度快。
  - full：逐帧处理全部位姿帧的 npy/png/ply，并聚合出世界系 aggregated_world.ply。
    体积与耗时显著增大（见 README 对比）。

统一配色：固定全局深度范围（自动统计 p2~p98）+ TURBO 色带 + 中值滤波，
消除逐帧独立归一化造成的帧间颜色漂移闪烁。

加速：多进程并行（默认 = CPU 核数）+ --num-scale 降低 SGBM 分辨率。

用法示例：
  python 03_depth_pointcloud.py --input-dir <样例>                 # light
  python 03_depth_pointcloud.py --input-dir <样例> --mode full     # full
  python 03_depth_pointcloud.py --input-dir <样例> --mode full --step 3 --voxel 0.02
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _00_common as C  # noqa: E402
from _00_common import (  # noqa: E402
    ensure_output_dirs, load_meta, load_data_json,
    quat_to_rotmat,
)

# 共享只读上下文（多进程用）
_W = {}


def _init_worker(shared):
    _W.clear()
    _W.update(shared)


# ---------------------------------------------------------------------------
# SGBM 深度 / 点云核心
# ---------------------------------------------------------------------------
def _sgbm_depth(left_gray, right_gray, num_disp=96, block_size=9):
    """SGBM 立体匹配，返回视差图 (float32)。"""
    stereo = cv2.StereoSGBM_create(
        minDisparity=0,
        numDisparities=num_disp,
        blockSize=block_size,
        P1=8 * block_size * block_size,
        P2=32 * block_size * block_size,
        disp12MaxDiff=1,
        uniquenessRatio=10,
        speckleWindowSize=100,
        speckleRange=32,
        preFilterCap=63,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
    )
    return stereo.compute(left_gray, right_gray).astype(np.float32) / 16.0


def _disparity_to_depth(disp, fx, baseline):
    depth = np.full_like(disp, np.nan, dtype=np.float32)
    valid = disp > 0.1
    depth[valid] = (fx * baseline) / disp[valid]
    return depth


def _depth_to_points(depth, rgb, intrinsics):
    h, w = depth.shape
    fx, fy = intrinsics["fx"], intrinsics["fy"]
    cx, cy = intrinsics["cx"], intrinsics["cy"]
    ys, xs = np.mgrid[0:h, 0:w]
    z = depth
    valid = np.isfinite(z)
    if not valid.any():
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.uint8)
    xs_v, ys_v, z_v = xs[valid].astype(np.float32), ys[valid].astype(np.float32), z[valid].astype(np.float32)
    x = (xs_v - cx) * z_v / fx
    y = (ys_v - cy) * z_v / fy
    return np.stack([x, y, z_v], axis=1), rgb[valid]


def _cam_to_world(points, cam2world):
    if points.shape[0] == 0:
        return points
    pts_h = np.hstack([points, np.ones((points.shape[0], 1), np.float32)])
    return (cam2world @ pts_h.T).T[:, :3]


def _imwrite_unicode(path, img):
    ext = "." + str(path).rsplit(".", 1)[-1]
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(str(path))
    return ok


# ---------------------------------------------------------------------------
# 深度可视化（固定范围 + 平滑 + 色带）
# ---------------------------------------------------------------------------
def _smooth_depth(depth, k=5):
    """中值滤波降噪（仅处理有效深度区），减轻单帧 SGBM 噪声闪烁。"""
    valid = np.isfinite(depth) & (depth > 0)
    if not valid.any() or k < 3:
        return depth
    d_fill = np.where(valid, depth, np.float32(999.0)).astype(np.float32)
    d_f = cv2.medianBlur(d_fill, k)
    out = depth.copy()
    out[valid] = d_f[valid]
    return out


def _depth_norm(depth, near, far):
    """深度映射到 [0,1] 归一化（固定全局范围 near~far，裁剪越界值）。"""
    valid = np.isfinite(depth) & (depth > 0)
    norm = np.zeros_like(depth, np.float32)
    if valid.any() and far > near:
        norm[valid] = np.clip((depth[valid] - near) / (far - near), 0.0, 1.0)
    return norm


def _apply_cmap(norm, cmap):
    u8 = (norm * 255).astype(np.uint8)
    return cv2.applyColorMap(u8, cmap)


def _depth_png(depth, out_png, near, far, cmap=cv2.COLORMAP_TURBO,
               smooth=True, smooth_k=5):
    d = _smooth_depth(depth, smooth_k) if smooth else depth
    norm = _depth_norm(d, near, far)
    _imwrite_unicode(out_png, _apply_cmap(norm, cmap))


def _depth_bgr(depth, near, far, cmap=cv2.COLORMAP_TURBO,
               smooth=True, smooth_k=5):
    d = _smooth_depth(depth, smooth_k) if smooth else depth
    norm = _depth_norm(d, near, far)
    return _apply_cmap(norm, cmap)


# ---------------------------------------------------------------------------
# 点云 I/O 与降采样
# ---------------------------------------------------------------------------
def _write_ply(path, pts, colors):
    n = pts.shape[0]
    with open(path, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {n}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("end_header\n")
        for i in range(n):
            x, y, z = pts[i]
            r, g, b = colors[i]
            f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(r)} {int(g)} {int(b)}\n")


def _read_ply(path):
    pts, cols = [], []
    with open(path) as f:
        lines = f.readlines()
    header_end = 0
    for i, ln in enumerate(lines):
        if ln.strip() == "end_header":
            header_end = i
            break
    for ln in lines[header_end + 1:]:
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split()
        if len(parts) >= 6:
            pts.append([float(parts[0]), float(parts[1]), float(parts[2])])
            cols.append([int(parts[3]), int(parts[4]), int(parts[5])])
    return (np.array(pts, np.float32), np.array(cols, np.uint8)) if pts else \
        (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.uint8))


def _random_downsample(points, colors, max_points):
    n = points.shape[0]
    if n <= max_points:
        return points, colors
    idx = np.random.choice(n, max_points, replace=False)
    return points[idx], colors[idx]


def _voxel_downsample(points, colors, voxel_size=0.01):
    if points.shape[0] == 0:
        return points, colors
    voxel_idx = np.floor(points / voxel_size).astype(np.int64)
    _, inverse, _ = np.unique(voxel_idx, axis=0, return_inverse=True, return_counts=True)
    seen = {}
    keep = []
    for i, v in enumerate(inverse):
        if v not in seen:
            seen[v] = i
            keep.append(i)
    keep = np.array(keep, dtype=np.int64)
    return points[keep], colors[keep]


def aggregate_from_frames(frame_dir, out_ply, voxel, max_per_frame):
    """仅从已有逐帧 PLY 重建聚合点云（免重跑 SGBM）。"""
    plies = sorted(Path(frame_dir).glob("frame_*.ply"))
    agg_pts, agg_cols = [], []
    for p in plies:
        pts, cols = _read_ply(p)
        if pts.shape[0] == 0:
            continue
        if max_per_frame and max_per_frame > 0:
            pts, cols = _random_downsample(pts, cols, max_per_frame)
        if voxel and voxel > 0:
            pts, cols = _voxel_downsample(pts, cols, voxel)
        agg_pts.append(pts)
        agg_cols.append(cols)
    if agg_pts:
        all_pts = np.concatenate(agg_pts, axis=0)
        all_cols = np.concatenate(agg_cols, axis=0)
        _write_ply(out_ply, all_pts, all_cols)
        print(f"[03] 聚合点云 {all_pts.shape[0]} 点 -> {out_ply}")
    else:
        print("[03][WARN] 无逐帧 PLY 可聚合")


def _write_preview(pts, cols, out_png, size=(1280, 720)):
    """用点云渲染顶视投影预览图（x-z 平面，颜色取点色）。"""
    h, w = size[1], size[0]
    canvas = np.full((h, w, 3), 24, np.uint8)
    if pts.shape[0] == 0:
        _imwrite_unicode(out_png, canvas)
        return
    xs, zs = pts[:, 0], pts[:, 2]
    xmin, xmax = xs.min(), xs.max()
    zmin, zmax = zs.min(), zs.max()
    if xmax - xmin < 1e-6:
        xmax = xmin + 1.0
    if zmax - zmin < 1e-6:
        zmax = zmin + 1.0
    pad = 40
    u = pad + (xs - xmin) / (xmax - xmin) * (w - 2 * pad)
    v = h - pad - (zs - zmin) / (zmax - zmin) * (h - 2 * pad)
    u = np.clip(u, 0, w - 1).astype(int)
    v = np.clip(v, 0, h - 1).astype(int)
    canvas[v, u] = cols
    _imwrite_unicode(out_png, canvas)


# ---------------------------------------------------------------------------
# 多进程 worker
# ---------------------------------------------------------------------------
def _compute_depth_core(fidx, want_pointcloud):
    """计算单个位姿帧的深度（可选点云）。返回 (depth_save, pts_world, colors)。

    fidx 是位姿帧索引；视频读取位置 = fidx 映射到的视频帧（位姿/视频异频，需换算）。
    want_pointcloud=False 时不计算点云（用于深度范围统计 Pass1，更快）。
    """
    sh = _W
    video_frame = int(fidx * sh["video_frames"] / max(sh["frame_count"], 1))
    video_frame = min(max(video_frame, 0), sh["video_frames"] - 1)
    cap = cv2.VideoCapture(sh["video_path"])
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, video_frame)
    ok, bgr = cap.read()
    cap.release()
    if not ok or bgr is None:
        return None
    if bgr.shape[1] != sh["eye_w"] * 2:
        bgr = cv2.resize(bgr, (sh["eye_w"] * 2, sh["video_h"]))
    left_bgr = bgr[:, :sh["eye_w"], :]
    right_bgr = bgr[:, sh["eye_w"]:, :]
    scale = sh["num_scale"]
    if scale != 1.0:
        nw, nh = int(sh["eye_w"] * scale), int(sh["video_h"] * scale)
        left_gray = cv2.resize(cv2.cvtColor(left_bgr, cv2.COLOR_BGR2GRAY), (nw, nh))
        right_gray = cv2.resize(cv2.cvtColor(right_bgr, cv2.COLOR_BGR2GRAY), (nw, nh))
    else:
        left_gray = cv2.cvtColor(left_bgr, cv2.COLOR_BGR2GRAY)
        right_gray = cv2.cvtColor(right_bgr, cv2.COLOR_BGR2GRAY)
    disp = _sgbm_depth(left_gray, right_gray, sh["num_disp"], sh["block_size"])
    intr = {k: (v * scale if k in ("fx", "fy", "cx", "cy") else v)
            for k, v in sh["intrinsics"].items()}
    depth = _disparity_to_depth(disp, intr["fx"], sh["baseline"])
    depth_save = depth.copy() if scale == 1.0 else cv2.resize(depth, (sh["eye_w"], sh["video_h"]))
    if not want_pointcloud:
        return (depth_save, None, None)
    left_rgb = left_bgr if scale == 1.0 else cv2.resize(left_bgr, (nw, nh))
    pts_cam, cols = _depth_to_points(depth, cv2.cvtColor(left_rgb, cv2.COLOR_BGR2RGB), intr)
    if pts_cam.shape[0] > 0:
        rec = sh["frames"][fidx]
        head = rec.get("head", {})
        hpos = np.array(head.get("position", [0, 0, 0]), dtype=np.float32)
        hrot = head.get("rotation", [0, 0, 0, 1])
        R_head = quat_to_rotmat(hrot).astype(np.float32)
        cam_pos = hpos + R_head @ sh["left_pos"]
        T_cw = np.eye(4, dtype=np.float32)
        T_cw[:3, :3] = R_head
        T_cw[:3, 3] = cam_pos
        pts_world = _cam_to_world(pts_cam, T_cw)
    else:
        pts_world = np.zeros((0, 3), np.float32)
    return (depth_save, pts_world, cols)


def _process_one_frame(fidx):
    """light 模式 worker：计算单帧深度+点云，不写盘。"""
    return _compute_depth_core(fidx, True)


def _process_full_frame(fidx):
    """full 模式 worker：写该帧 npy/png/ply，返回 (fidx, 降采样后的世界系点)。"""
    sh = _W
    if fidx < 0 or fidx >= sh["frame_count"]:
        return None
    res = _compute_depth_core(fidx, True)
    if res is None:
        return None
    depth_save, pts_world, cols = res
    dep_dir, pc_dir = sh["depth_dir"], sh["pc_frames_dir"]
    np.save(dep_dir / f"frame_{fidx:06d}.npy", depth_save.astype(np.float32))
    _depth_png(depth_save, dep_dir / f"frame_{fidx:06d}.png",
               sh["near"], sh["far"], cmap=sh["cmap"],
               smooth=sh["smooth"], smooth_k=sh["smooth_k"])
    agg = None
    if pts_world.shape[0] > 0:
        _write_ply(pc_dir / f"frame_{fidx:06d}.ply", pts_world, cols)
        pts_s, col_s = pts_world, cols
        if sh["max_per_frame"] and sh["max_per_frame"] > 0:
            pts_s, col_s = _random_downsample(pts_s, col_s, sh["max_per_frame"])
        if sh["voxel"] and sh["voxel"] > 0:
            pts_s, col_s = _voxel_downsample(pts_s, col_s, sh["voxel"])
        agg = (pts_s, col_s)
    return (fidx, agg)


def _stat_frame(fidx, nbins=2000, dmax=50.0):
    """统计单帧有效深度直方图（供全局范围 Pass1 用，不算点云）。"""
    res = _compute_depth_core(fidx, False)
    if res is None:
        return None
    depth = res[0]
    valid = np.isfinite(depth) & (depth > 0)
    if not valid.any():
        return None
    d = np.clip(depth[valid], 0.0, dmax)
    idx = (d / dmax * nbins).astype(np.int32)
    np.clip(idx, 0, nbins - 1, out=idx)
    return np.bincount(idx, minlength=nbins).astype(np.int64)


def _global_range_from_hists(hists, nbins=2000, dmax=50.0, p_lo=2, p_hi=98):
    """由各帧直方图聚合出全局深度范围 [near, far]（p_lo~p_hi 百分位）。"""
    total = np.zeros(nbins, np.int64)
    for h in hists:
        if h is not None:
            total += h
    cum = np.cumsum(total)
    s = int(cum[-1])
    if s == 0:
        return 0.3, 15.0
    lo = int(np.searchsorted(cum, s * p_lo / 100.0))
    hi = int(np.searchsorted(cum, s * p_hi / 100.0))
    near = max(0.05, lo / nbins * dmax)
    far = hi / nbins * dmax
    if far <= near:
        far = near + 0.1
    return float(near), float(far)


def main():
    ap = argparse.ArgumentParser(
        description="双目 SGBM 深度重建 + 彩色点云（light/full 一套脚本）")
    ap.add_argument("--input-dir", default=None, help="样例数据目录，默认项目根")
    ap.add_argument("--mode", choices=["light", "full"], default="light",
                    help="light=首/中/末帧+深度视频（默认）；full=逐帧全量+聚合点云")
    # SGBM / 并行
    ap.add_argument("--num-scale", type=float, default=0.5,
                    help="SGBM 深度分辨率缩放（默认 0.5；越小越快）")
    ap.add_argument("--num-disp", type=int, default=96)
    ap.add_argument("--block-size", type=int, default=9)
    ap.add_argument("--workers", type=int, default=None,
                    help="并行进程数（默认 = CPU 核数）")
    # light 模式参数
    ap.add_argument("--key-frames", nargs="+", type=int, default=None,
                    help="首/中/末帧索引，默认自动取 0 / 中 / 末")
    ap.add_argument("--depth-video-step", type=int, default=2,
                    help="light 深度视频抽帧步长（默认 2；设 0 跳过）")
    ap.add_argument("--depth-video-fps", type=float, default=None,
                    help="light 深度视频帧率（默认取视频帧率 / step）")
    ap.add_argument("--skip-preview", action="store_true", help="跳过点云预览图生成")
    # full 模式参数
    ap.add_argument("--frames", nargs="+", type=int, default=None,
                    help="full：只处理指定帧索引，如 --frames 0 50 100")
    ap.add_argument("--step", type=int, default=1,
                    help="full：每 N 帧处理 1 帧（抽帧，默认 1 全量）")
    ap.add_argument("--voxel", type=float, default=0.02,
                    help="full：聚合点云体素下采样尺寸(米)，默认 0.02；0 不降采样")
    ap.add_argument("--max-per-frame", type=int, default=15000,
                    help="full：每帧聚合前随机抽样最大点数（控制聚合体积）")
    ap.add_argument("--aggregate-only", action="store_true",
                    help="full：仅从已有逐帧 PLY 重建聚合点云（免重跑 SGBM）")
    ap.add_argument("--depth-png-only", action="store_true",
                    help="full：仅从已有 npy 深度图重建 PNG（免重跑 SGBM）")
    # 深度配色（light/full 通用）
    ap.add_argument("--depth-near", type=float, default=None,
                    help="固定深度范围近端(米)，默认自动统计全局 p2")
    ap.add_argument("--depth-far", type=float, default=None,
                    help="固定深度范围远端(米)，默认自动统计全局 p98")
    ap.add_argument("--colormap", choices=["turbo", "jet"], default="turbo",
                    help="深度色带（默认 turbo；jet 为传统红蓝）")
    ap.add_argument("--no-smooth", action="store_true",
                    help="关闭深度中值滤波平滑（默认开启）")
    ap.add_argument("--smooth-k", type=int, default=5,
                    help="深度中值滤波核尺寸（默认 5）")
    ap.add_argument("--range-percentile-lo", type=float, default=2,
                    help="全局范围低百分位（默认 2）")
    ap.add_argument("--range-percentile-hi", type=float, default=98,
                    help="全局范围高百分位（默认 98）")
    args = ap.parse_args()

    if args.input_dir:
        C.set_input_dir(args.input_dir)
    ensure_output_dirs()

    cmap = cv2.COLORMAP_TURBO if args.colormap == "turbo" else cv2.COLORMAP_JET
    smooth = not args.no_smooth

    # ---- full 模式：仅从已有 npy/png 重建 ----
    if args.depth_png_only:
        npys = sorted(C.DEPTH_DIR.glob("frame_*.npy"))
        near = args.depth_near or 0.3
        far = args.depth_far or 15.0
        for npf in npys:
            depth = np.load(npf)
            _depth_png(depth, C.DEPTH_DIR / npf.with_suffix(".png").name,
                       near, far, cmap=cmap, smooth=smooth, smooth_k=args.smooth_k)
        print(f"[03] 从 {len(npys)} 个 npy 重建深度 PNG 完成")
        return

    # ---- full 模式：仅聚合 ----
    if args.aggregate_only:
        aggregate_from_frames(C.POINTCLOUD_FRAMES_DIR,
                              C.POINTCLOUD_DIR / "aggregated_world.ply",
                              args.voxel, args.max_per_frame)
        print("[03] 聚合完成（aggregate-only）")
        return

    meta = load_meta()
    data = load_data_json()
    session = meta["session"]
    cam = meta["camera"]
    intrinsics = cam["intrinsics"]
    baseline = cam["baseline"]
    video_w, video_h = session["videoWidth"], session["videoHeight"]
    eye_w = video_w // 2
    frame_count = session["frameCount"]   # 位姿帧数
    probe = cv2.VideoCapture(str(C.VIDEO_MP4))
    video_frames = int(probe.get(cv2.CAP_PROP_FRAME_COUNT)) if probe.isOpened() else frame_count
    video_fps = probe.get(cv2.CAP_PROP_FPS) if probe.isOpened() else 30.0
    if video_fps <= 0:
        video_fps = float(session.get("videoFps", 30) or 30)
    probe.release()
    if video_frames < frame_count:
        video_frames = frame_count

    print(f"[03] video {video_w}x{video_h} -> 每眼 {eye_w}x{video_h}, "
          f"baseline={baseline:.4f}m, 位姿帧={frame_count}, 模式={args.mode}")

    left_pos = np.array(cam.get("left", {}).get("position", [0, 0, 0]), dtype=np.float32)
    workers = args.workers or os.cpu_count() or 1
    import multiprocessing as mp
    ctx = mp.get_context("spawn")

    # ---- 全局深度范围（Pass1 统计，light/full 通用） ----
    near, far = args.depth_near, args.depth_far
    if near is None or far is None:
        if args.mode == "full":
            stat_step = max(1, args.step * 20)
            stat_indices = list(range(0, frame_count, stat_step))
        else:
            stat_indices = (list(range(0, frame_count, args.depth_video_step))
                            if args.depth_video_step and args.depth_video_step > 0
                            else [0, frame_count // 2, frame_count - 1])
        print(f"[03] 统计全局深度范围（{len(stat_indices)} 帧，Pass1）...")
        t_r = time.time()
        shared_stat = {
            "video_path": str(C.VIDEO_MP4), "frames": data["frames"],
            "intrinsics": intrinsics, "baseline": baseline, "left_pos": left_pos,
            "eye_w": eye_w, "video_h": video_h, "num_scale": args.num_scale,
            "num_disp": args.num_disp, "block_size": args.block_size,
            "frame_count": frame_count, "video_frames": video_frames,
        }
        with ctx.Pool(workers, initializer=_init_worker, initargs=(shared_stat,)) as pool:
            hists = list(pool.imap(_stat_frame, stat_indices, chunksize=8))
        a_near, a_far = _global_range_from_hists(
            hists, p_lo=args.range_percentile_lo, p_hi=args.range_percentile_hi)
        near = args.depth_near if args.depth_near is not None else a_near
        far = args.depth_far if args.depth_far is not None else a_far
        print(f"[03] 全局深度范围 [{near:.3f}, {far:.3f}] m（Pass1 用时 {time.time()-t_r:.1f}s）")
    else:
        print(f"[03] 使用指定深度范围 [{near:.3f}, {far:.3f}] m")

    t_start = time.time()

    if args.mode == "full":
        # ================= full：逐帧 npy/png/ply + 聚合 =================
        C.DEPTH_DIR.mkdir(parents=True, exist_ok=True)
        C.POINTCLOUD_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        frame_indices = sorted(set(args.frames)) if args.frames else \
            list(range(0, frame_count, args.step))
        print(f"[03] full: 待处理帧数 = {len(frame_indices)}")

        shared = {
            "video_path": str(C.VIDEO_MP4), "frames": data["frames"],
            "intrinsics": intrinsics, "baseline": baseline, "left_pos": left_pos,
            "eye_w": eye_w, "video_h": video_h, "num_scale": args.num_scale,
            "num_disp": args.num_disp, "block_size": args.block_size,
            "frame_count": frame_count, "video_frames": video_frames,
            "depth_dir": C.DEPTH_DIR, "pc_frames_dir": C.POINTCLOUD_FRAMES_DIR,
            "near": near, "far": far, "cmap": cmap, "smooth": smooth,
            "smooth_k": args.smooth_k, "voxel": args.voxel,
            "max_per_frame": args.max_per_frame,
        }
        agg_pts, agg_cols = [], []
        with ctx.Pool(workers, initializer=_init_worker, initargs=(shared,)) as pool:
            done = 0
            for res in pool.imap_unordered(_process_full_frame, frame_indices, chunksize=4):
                done += 1
                if res is None:
                    continue
                _, agg = res
                if agg is not None:
                    agg_pts.append(agg[0])
                    agg_cols.append(agg[1])
                if done % 50 == 0 or done == len(frame_indices):
                    print(f"[03] full {done}/{len(frame_indices)} 帧 ({time.time()-t_start:.1f}s)",
                          flush=True)
        if agg_pts:
            all_pts = np.concatenate(agg_pts, axis=0)
            all_cols = np.concatenate(agg_cols, axis=0)
            agg_path = C.POINTCLOUD_DIR / "aggregated_world.ply"
            _write_ply(agg_path, all_pts, all_cols)
            print(f"[03] full 聚合点云 {all_pts.shape[0]} 点 -> {agg_path}")
        print(f"[03] full 完成，总用时 {time.time()-t_start:.1f}s")
    else:
        # ================= light：首/中/末 + 深度视频 + preview =================
        if args.key_frames:
            key_frames = sorted(set(args.key_frames))
        else:
            key_frames = sorted(set([0, frame_count // 2, frame_count - 1]))
        key_frames = [k for k in key_frames if 0 <= k < frame_count]
        print(f"[03-light] 首/中/末 位姿帧: {key_frames}")

        shared = {
            "video_path": str(C.VIDEO_MP4), "frames": data["frames"],
            "intrinsics": intrinsics, "baseline": baseline, "left_pos": left_pos,
            "eye_w": eye_w, "video_h": video_h, "num_scale": args.num_scale,
            "num_disp": args.num_disp, "block_size": args.block_size,
            "frame_count": frame_count, "video_frames": video_frames,
        }
        with ctx.Pool(workers, initializer=_init_worker, initargs=(shared,)) as pool:
            results = list(pool.map(_process_one_frame, key_frames))
        for fidx, res in zip(key_frames, results):
            if res is None:
                print(f"[03-light][WARN] 帧 {fidx} 处理失败")
                continue
            depth_save, pts_world, cols = res
            C.DEPTH_DIR.mkdir(parents=True, exist_ok=True)
            np.save(C.DEPTH_DIR / f"frame_{fidx:06d}.npy", depth_save.astype(np.float32))
            _depth_png(depth_save, C.DEPTH_DIR / f"frame_{fidx:06d}.png",
                       near, far, cmap=cmap, smooth=smooth, smooth_k=args.smooth_k)
            C.POINTCLOUD_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
            if pts_world.shape[0] > 0:
                _write_ply(C.POINTCLOUD_FRAMES_DIR / f"frame_{fidx:06d}.ply", pts_world, cols)
        print(f"[03-light] 首/中/末帧深度+点云完成，用时 {time.time()-t_start:.1f}s")

        if args.depth_video_step and args.depth_video_step > 0:
            indices = list(range(0, frame_count, args.depth_video_step))
            pose_fps = frame_count / (video_frames / video_fps) if video_frames > 0 else 25.0
            out_fps = args.depth_video_fps or (pose_fps / args.depth_video_step)
            print(f"[03-light] 深度视频: 抽帧 {len(indices)} 帧 (step={args.depth_video_step}), "
                  f"位姿率={pose_fps:.1f}fps, 输出fps={out_fps:.1f}")
            out_video = C.DEPTH_DIR / "depth_video.mp4"
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(out_video), fourcc, max(out_fps, 1.0), (eye_w, video_h))
            t_v = time.time()
            n_done = 0
            with ctx.Pool(workers, initializer=_init_worker, initargs=(shared,)) as pool:
                for res in pool.imap(_process_one_frame, indices):
                    if res is None:
                        continue
                    depth_save, _, _ = res
                    writer.write(_depth_bgr(depth_save, near, far, cmap=cmap,
                                            smooth=smooth, smooth_k=args.smooth_k))
                    n_done += 1
                    if n_done % 200 == 0:
                        print(f"[03-light] 深度视频 {n_done}/{len(indices)} "
                              f"({time.time()-t_v:.1f}s)", flush=True)
            writer.release()
            print(f"[03-light] 深度视频完成: {out_video}，用时 {time.time()-t_v:.1f}s")
        else:
            print("[03-light] 跳过深度视频")

        if not args.skip_preview:
            preview_ply = C.POINTCLOUD_FRAMES_DIR / f"frame_{key_frames[0]:06d}.ply"
            if preview_ply.exists():
                try:
                    pts, cols = _read_ply(preview_ply)
                except Exception:
                    pts = np.zeros((0, 3), np.float32)
                    cols = np.zeros((0, 3), np.uint8)
                if pts.shape[0] > 0:
                    _write_preview(pts, cols, C.POINTCLOUD_DIR / "preview.png")
                    print(f"[03-light] 点云预览图: {C.POINTCLOUD_DIR / 'preview.png'}")
        print(f"[03-light] 完成，总用时 {time.time()-t_start:.1f}s")


if __name__ == "__main__":
    main()
