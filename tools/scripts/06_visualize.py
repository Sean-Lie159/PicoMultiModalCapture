# -*- coding: utf-8 -*-
"""
06_visualize.py — 合成可视化：双目 RGB 视频 + 3D 透视人骨架。

布局（尺寸 2560x1440）：
  +----------------------------+   <- 上方：双目 SBS 原始视频（2560x720，直接取 video.mp4）
  +----------------------------+
  +----------------------------+   <- 下方：3D 透视动捕骨架（2560x720，
  |   3D 透视人骨架 + 地面网格    |       身体 24 + 双手 26x2 关节，相机跟随 Pelvis）
  +----------------------------+

说明：
  - 骨架与上方视频逐帧时间对齐（_align 插值）。
  - 3D 透视 + 地面网格由 _g1_render.draw_skeleton_3d 提供（v14 骨架可视化部分）。
  - 本脚本不含 URDF/G1 渲染（URDF 重定向已按决策 B 移除，见 AGENTS.md §4.19）。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _00_common as C
import _align
import _g1_render
import _text_overlay

OUT_W, OUT_H = 2560, 1440
LOWER_W, LOWER_H = 2560, 720  # 下方 3D 骨架全宽画布
UPPER_W, UPPER_H = 2560, 720  # 上方双目视频

# 美观叠加：文字标签 / 时间戳帧号 / 区域分隔线
UPPER_LABEL = "原始双目 RGB 视频"
LOWER_LABEL = "动捕同步 | Motion Capture"
SEP_COLOR = (60, 65, 75)
SEP_THICK = 2
LABEL_FONT_PX = 44
STAMP_FONT_PX = 34


def _apply_overlay(combined, frame_idx, video_fps):
    """在合成帧上叠加：区域左上角标签、右下角时间戳+帧号、上下分隔线。

    combined: (OUT_H, OUT_W, 3) BGR（上视频 + 下骨架）。
    frame_idx: 当前帧号（0-based），用于计算时间戳。
    video_fps: 视频帧率。
    """
    # 上下分隔线
    cv2.line(combined, (0, UPPER_H), (OUT_W, UPPER_H), SEP_COLOR, SEP_THICK)

    # 上方标签（左上角）
    _text_overlay.text_overlay(combined, UPPER_LABEL, (18, 14),
                               size_px=LABEL_FONT_PX, color=(230, 235, 240),
                               bg_color=(10, 10, 14), bg_pad=(12, 6))
    # 下方标签（左上角，相对下方区域顶部）
    _text_overlay.text_overlay(combined, LOWER_LABEL, (18, UPPER_H + 14),
                               size_px=LABEL_FONT_PX, color=(230, 235, 240),
                               bg_color=(10, 10, 14), bg_pad=(12, 6))

    # 右下角时间戳 + 帧号（叠加在最上层，浅色小字）
    t_sec = frame_idx / video_fps if video_fps else 0.0
    ms = int((t_sec - int(t_sec)) * 1000)
    s = int(t_sec) % 60
    m = int(t_sec // 60)
    stamp = f"{m:02d}:{s:02d}.{ms:03d}   f{frame_idx:04d}"
    _text_overlay.text_overlay(combined, stamp, (OUT_W - 18, OUT_H - 14),
                               size_px=STAMP_FONT_PX, color=(200, 205, 210),
                               bg_color=(10, 10, 14), bg_pad=(10, 4),
                               anchor="right-bottom")
    return combined


def _unsharp_mask(img, sigma=1.5, strength=1.2):
    """对图像做 unsharp mask 锐化，用于改善采集端失焦/运动模糊帧。"""
    blurred = cv2.GaussianBlur(img, (0, 0), sigma)
    sharp = cv2.addWeighted(img, 1.0 + strength, blurred, -strength, 0)
    return sharp


def _per_frame_sharpness(bgr):
    """计算单帧拉普拉斯方差（清晰度指标）。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _render_chunk_worker(args):
    """多进程 worker：渲染一段帧的"上视频 + 下3D骨架"，写临时 MJPG(.avi)。

    args: (start, end, video_path, pose_vid, tmp_out, out_w, out_h,
           sharpen_blur, blur_threshold, sharpen_strength, video_fps)
    """
    (start, end, video_path, pose_vid, tmp_out, out_w, out_h,
     sharpen_blur, blur_threshold, sharpen_strength, video_fps) = args
    import cv2
    import numpy as np
    import _g1_render as _gr
    import _text_overlay as _to

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return tmp_out
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0

    # 画布尺寸
    upper_h = out_h // 2
    lower_h = out_h - upper_h
    lower_w = out_w

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(tmp_out), fourcc, fps, (out_w, out_h))

    for k in range(start, end):
        cap.set(cv2.CAP_PROP_POS_FRAMES, k)
        ok, bgr = cap.read()
        if not ok or bgr is None:
            continue
        if bgr.shape[1] != out_w or bgr.shape[0] != upper_h:
            bgr = cv2.resize(bgr, (out_w, upper_h))
        if sharpen_blur:
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            sh = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            if sh < blur_threshold:
                blurred = cv2.GaussianBlur(bgr, (0, 0), 1.5)
                bgr = cv2.addWeighted(bgr, 1.0 + sharpen_strength, blurred, -sharpen_strength, 0)

        # 下方 3D 透视骨架（相机跟随 Pelvis，地面网格）
        skel = np.zeros((lower_h, lower_w, 3), np.uint8)
        skel[:] = (20, 20, 25)
        pelvis = pose_vid[k, 1, :3]
        feet_y = float(np.nanmin(pose_vid[k, 1:1 + 24, 1]))
        cam_pos = np.array([pelvis[0], 0.5, pelvis[2] + 4.5])
        f_px_3d = lower_w * 0.55   # 全宽画布下让全身入画
        _gr.draw_skeleton_3d(skel, pose_vid[k], cam_pos,
                             f_px=f_px_3d, ground_y=feet_y)

        combined = np.vstack([bgr, skel])
        _to.text_overlay(combined, "原始双目 RGB 视频", (18, 14),
                         size_px=44, color=(230, 235, 240),
                         bg_color=(10, 10, 14), bg_pad=(12, 6))
        _to.text_overlay(combined, "动捕同步 | Motion Capture", (18, upper_h + 14),
                         size_px=44, color=(230, 235, 240),
                         bg_color=(10, 10, 14), bg_pad=(12, 6))
        cv2.line(combined, (0, upper_h), (out_w, upper_h), (60, 65, 75), 2)
        t_sec = k / video_fps if video_fps else 0.0
        ms = int((t_sec - int(t_sec)) * 1000)
        s = int(t_sec) % 60
        m = int(t_sec // 60)
        stamp = f"{m:02d}:{s:02d}.{ms:03d}   f{k:04d}"
        _to.text_overlay(combined, stamp, (out_w - 18, out_h - 14),
                         size_px=34, color=(200, 205, 210),
                         bg_color=(10, 10, 14), bg_pad=(10, 4),
                         anchor="right-bottom")
        writer.write(combined)
    cap.release()
    writer.release()
    return tmp_out


def main():
    ap = argparse.ArgumentParser(description="双目 RGB + 3D 透视人骨架 合屏可视化")
    ap.add_argument("--input-dir", default=None, help="样例数据目录，默认项目根")
    ap.add_argument("--max-frames", type=int, default=None, help="只渲染前 N 帧（调试用）")
    ap.add_argument("--start-frame", type=int, default=0, help="起始帧索引")
    ap.add_argument("--workers", type=int, default=None, help="并行进程数（默认 = CPU 核数）")
    ap.add_argument("--sharpen-blur", action="store_true",
                    help="对拉普拉斯方差低于阈值的模糊帧自动做 unsharp mask 锐化")
    ap.add_argument("--blur-threshold", type=float, default=150.0,
                    help="低于此清晰度视为模糊并锐化（默认 150）")
    ap.add_argument("--sharpen-strength", type=float, default=1.2,
                    help="unsharp mask 锐化强度（默认 1.2）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.input_dir:
        C.set_input_dir(args.input_dir)
    C.ensure_output_dirs()
    vis_dir = C.VIS_DIR
    vis_dir.mkdir(parents=True, exist_ok=True)
    out = args.out or str(vis_dir / "combined.mp4")

    meta = C.load_meta()
    data = C.load_data_json()

    cap = cv2.VideoCapture(str(C.VIDEO_MP4))
    video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if video_fps <= 0:
        video_fps = float(meta["session"].get("videoFps", 30))
    print(f"[06] video {video_w}x{video_h}, {video_frames} 帧, fps={video_fps:.1f}")

    # 人骨架：位姿 -> 重采样到视频帧
    t_arr, pose, names = _align.build_pose_arrays(data)
    pose_vid = _align.resample_pose_to_video(t_arr, pose, video_frames, video_fps)
    print(f"[06] 人位姿重采样 {pose.shape[0]} -> {video_frames} 帧")

    # 计算实际渲染范围
    n_to_render = min(video_frames, args.max_frames) if args.max_frames else video_frames
    render_start = args.start_frame
    render_end = args.start_frame + n_to_render
    n_to_render = min(n_to_render, video_frames - render_start)

    # 决定是否用多进程
    workers = args.workers if args.workers is not None else os.cpu_count() or 1
    use_mp = (workers > 1) and (n_to_render >= 20)

    if not use_mp:
        # 单进程模式
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out, fourcc, video_fps, (OUT_W, OUT_H))
        for k in range(render_start, render_end):
            cap.set(cv2.CAP_PROP_POS_FRAMES, k)
            ok, bgr = cap.read()
            if not ok or bgr is None:
                continue
            bgr = cv2.resize(bgr, (video_w, video_h)) if bgr.shape[1] != video_w else bgr
            if args.sharpen_blur:
                sh = _per_frame_sharpness(bgr)
                if sh < args.blur_threshold:
                    bgr = _unsharp_mask(bgr, strength=args.sharpen_strength)
            skel = np.zeros((LOWER_H, LOWER_W, 3), np.uint8)
            skel[:] = (20, 20, 25)
            pelvis = pose_vid[k, 1, :3]
            feet_y = float(np.nanmin(pose_vid[k, 1:1 + 24, 1]))
            cam_pos = np.array([pelvis[0], 0.5, pelvis[2] + 4.5])
            f_px_3d = LOWER_W * 0.55
            _g1_render.draw_skeleton_3d(skel, pose_vid[k], cam_pos,
                                         f_px=f_px_3d, ground_y=feet_y)
            combined = np.vstack([bgr, skel])
            _apply_overlay(combined, k, video_fps)
            writer.write(combined)
            if (k + 1) % 100 == 0 or k == render_end - 1:
                print(f"[06] {k - render_start + 1}/{n_to_render}", flush=True)
        cap.release()
        writer.release()
    else:
        # 多进程模式：分块并发渲染到临时 mp4，再合并
        import multiprocessing as mp
        import time
        ctx = mp.get_context("spawn")
        chunk_size = max(1, (n_to_render + workers - 1) // workers)
        tmp_dir = Path(vis_dir) / "_chunks"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tasks = []
        for wi in range(workers):
            c_start = render_start + wi * chunk_size
            c_end = min(render_start + (wi + 1) * chunk_size, render_end)
            if c_start >= c_end:
                break
            tmp_out = tmp_dir / f"chunk_{wi:03d}.avi"
            tasks.append((c_start, c_end, str(C.VIDEO_MP4), pose_vid,
                          str(tmp_out), OUT_W, OUT_H,
                          args.sharpen_blur, args.blur_threshold, args.sharpen_strength,
                          video_fps))
        print(f"[06] 多进程: {len(tasks)} chunks, workers={workers}, "
              f"每块约 {chunk_size} 帧")
        t0 = time.time()
        with ctx.Pool(workers) as pool:
            for i, _ in enumerate(pool.imap_unordered(_render_chunk_worker, tasks)):
                print(f"[06]  chunk {i+1}/{len(tasks)} done ({time.time()-t0:.1f}s)",
                      flush=True)

        # 合并所有 chunk 到最终 mp4
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out, fourcc, video_fps, (OUT_W, OUT_H))
        chunks = sorted(tmp_dir.glob("chunk_*.avi"))
        for cf in chunks:
            ccap = cv2.VideoCapture(str(cf))
            while True:
                ok, fr = ccap.read()
                if not ok or fr is None:
                    break
                writer.write(fr)
            ccap.release()
        writer.release()
        for cf in chunks:
            cf.unlink()
        tmp_dir.rmdir()
        print(f"[06] 合并完成，用时 {time.time()-t0:.1f}s")

    cap.release()
    print(f"[06] wrote {out} (fps={video_fps:.1f}, frames={n_to_render}/{video_frames}, "
          f"{OUT_W}x{OUT_H})")
    print("[06] 完成")


if __name__ == "__main__":
    main()
