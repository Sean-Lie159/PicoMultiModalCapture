# -*- coding: utf-8 -*-
"""
04_skeleton_viz.py — 身体 + 手部动捕骨架可视化（与视频逐帧时间对齐）。

功能（相对旧版改进）：
  1. 完整时长：用 _align.py 把 data.json 的低采样位姿（~26fps）按时间戳
     插值到 video.mp4 每一帧（60fps），骨架视频时长 = 视频时长（不再被压缩到 12s）。
  2. 全量骨架：绘制身体 24 关节 + 左手 26 关节 + 右手 26 关节（样例手部有效）。
  3. 自适应缩放：按关节坐标范围自动计算缩放与平移，骨架铺满画布而非挤在一角。
  4. 支持 --input-dir 指定样例目录（输出到 <样例>/output/skeleton/）。

输出：
  output/skeleton/skeleton_XXXXXX.png  （关键帧）
  output/skeleton/episode_skeleton.mp4 （完整时长骨架动画，与视频帧对齐）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _00_common as C
import _align
import _g1_render
from _04_hand_topo import HAND_BONES, BODY_COLORS, HAND_COLORS

# 骨架画布（与组合视频下方区域一致：2560x720）
CANVAS_W, CANVAS_H = 2560, 720


def _imwrite_unicode(path, img):
    ext = "." + str(path).rsplit(".", 1)[-1]
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(str(path))
    return ok


def _compute_projection(pose_frames, view="front"):
    """基于全部帧关节坐标计算自适应正交投影（返回缩放与中心偏移）。

    用 y 跨度与 x/z 跨度共同决定 scale，保证骨架铺满画布且不变形。
    返回 dict: {center2d, scale_px_per_m}
    """
    # 只取身体 + 双手的三维点（跳过头部也可，但头部有助于确定上方范围；保留身体即可）
    body_idx = list(range(1, 1 + len(C.BODY_JOINT_NAMES)))
    all_xyz = pose_frames[:, body_idx, :3]   # (V, 24, 3)
    x = all_xyz[:, :, 0]
    y = all_xyz[:, :, 1]
    z = all_xyz[:, :, 2]
    if view == "front":
        xs, ys = x, y
    else:  # side
        xs, ys = z, y
    x_min, x_max = np.nanmin(xs), np.nanmax(xs)
    y_min, y_max = np.nanmin(ys), np.nanmax(ys)
    x_span = max(x_max - x_min, 1e-6)
    y_span = max(y_max - y_min, 1e-6)
    x_c, y_c = (x_min + x_max) / 2, (y_min + y_max) / 2

    # 取能同时容纳两个方向的缩放（留 12% 边距）
    sx = (CANVAS_W * 0.88) / x_span
    sy = (CANVAS_H * 0.88) / y_span
    scale = min(sx, sy)
    return {"center": (float(x_c), float(y_c)), "scale": float(scale)}


def _draw_frame(canvas, pose_k, names, proj, view="front"):
    """在画布上绘制第 k 帧（视频帧）的骨架。

    pose_k: (J, 7) 单帧位姿（J=1+24+52）。
    names:  关节名列表（与 _align.build_pose_arrays 一致）。
    """
    center_x, center_y = proj["center"]
    scale = proj["scale"]
    body_n = len(C.BODY_JOINT_NAMES)
    hand_n = len(C.HAND_JOINT_NAMES)
    body_start = 1
    left_start = 1 + body_n
    right_start = 1 + body_n + hand_n

    def to_uv(x, y):
        # 取 X,Y（front）或 Z,Y（side）
        if view == "front":
            u = (x - center_x) * scale + CANVAS_W / 2
            v = CANVAS_H / 2 - (y - center_y) * scale
        else:
            u = (x - center_x) * scale + CANVAS_W / 2
            v = CANVAS_H / 2 - (y - center_y) * scale
        return int(u), int(v)

    def joint_uv(idx):
        p = pose_k[idx, :3]
        return to_uv(p[0], p[1])

    # --- 身体连线 ---
    for a, b in C.BODY_BONES:
        p1 = joint_uv(body_start + a)
        p2 = joint_uv(body_start + b)
        cv2.line(canvas, p1, p2, (200, 200, 200), 3)
    # --- 左手连线 ---
    for a, b in HAND_BONES:
        p1 = joint_uv(left_start + a)
        p2 = joint_uv(left_start + b)
        cv2.line(canvas, p1, p2, HAND_COLORS["L"], 2)
    # --- 右手连线 ---
    for a, b in HAND_BONES:
        p1 = joint_uv(right_start + a)
        p2 = joint_uv(right_start + b)
        cv2.line(canvas, p1, p2, HAND_COLORS["R"], 2)

    # --- 身体关节圆点 ---
    for i in range(body_n):
        u, v = joint_uv(body_start + i)
        col = BODY_COLORS[i]
        cv2.circle(canvas, (u, v), 7, col, -1)
        cv2.circle(canvas, (u, v), 7, (0, 0, 0), 1)
    # --- 手部关节圆点（小一点）---
    for i in range(hand_n):
        for s in (left_start, right_start):
            u, v = joint_uv(s + i)
            cv2.circle(canvas, (u, v), 4, (255, 255, 255), -1)
            cv2.circle(canvas, (u, v), 4, (0, 0, 0), 1)
    return canvas


def main():
    ap = argparse.ArgumentParser(description="身体+手部动捕骨架可视化（与视频逐帧对齐）")
    ap.add_argument("--input-dir", default=None,
                    help="样例数据目录（含 meta.json/data.json/video.mp4），默认项目根")
    ap.add_argument("--view", default="front", choices=["front", "side"],
                    help="投影视角：front 正视 / side 侧视")
    ap.add_argument("--out", default=None,
                    help="输出 MP4 文件名（相对 skeleton 目录），默认 episode_skeleton_3d.mp4")
    args = ap.parse_args()

    if args.input_dir:
        C.set_input_dir(args.input_dir)

    C.ensure_output_dirs()
    skel_dir = C.SKELETON_DIR
    skel_dir.mkdir(parents=True, exist_ok=True)

    meta = C.load_meta()
    data = C.load_data_json()

    # 视频帧数/帧率（用 cv2 读取 video.mp4 的真实信息）
    cap = cv2.VideoCapture(str(C.VIDEO_MP4))
    video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if video_fps <= 0:
        video_fps = float(meta["session"].get("videoFps", 30))

    # 位姿 -> 重采样到视频帧
    t_arr, pose, names = _align.build_pose_arrays(data)
    pose_vid = _align.resample_pose_to_video(t_arr, pose, video_frames, video_fps)
    print(f"[04] 位姿 {pose.shape[0]} 帧 -> 视频 {video_frames} 帧 ({video_fps:.1f}fps, "
          f"{video_frames/video_fps:.2f}s)，关节 {names.__len__()}")

    # 自适应投影参数
    proj = _compute_projection(pose_vid, args.view)
    print(f"[04] 自适应投影 scale={proj['scale']:.1f}px/m, center={proj['center']}")

    # 关键帧 PNG（v14：3D 透视 + 地面网格 + 相机跟随 Pelvis）
    # 04 画布很宽（2560），把人物控制在合适比例；缩 0.55 让全身入画
    f_px_3d = CANVAS_W * 0.55
    sample_idx = sorted(set([0, video_frames // 2, video_frames - 1]))
    for si in sample_idx:
        canvas = np.zeros((CANVAS_H, CANVAS_W, 3), np.uint8)
        canvas[:] = (20, 20, 25)
        pelvis = pose_vid[si, 1, :3]
        feet_y = float(np.nanmin(pose_vid[si, 1:1+24, 1]))
        cam_pos = np.array([pelvis[0], 0.5, pelvis[2] + 4.5])
        _g1_render.draw_skeleton_3d(canvas, pose_vid[si], cam_pos,
                                     f_px=f_px_3d, ground_y=feet_y)
        png = skel_dir / f"skeleton_{si:06d}.png"
        ok = _imwrite_unicode(png, canvas)
        print(f"[04] wrote {png} -> {ok}")

    # 合成完整 MP4（时长 = 视频时长）
    out_mp4 = skel_dir / (args.out or "episode_skeleton_3d.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_mp4), fourcc, video_fps, (CANVAS_W, CANVAS_H))
    for k in range(video_frames):
        canvas = np.zeros((CANVAS_H, CANVAS_W, 3), np.uint8)
        canvas[:] = (20, 20, 25)
        pelvis = pose_vid[k, 1, :3]
        feet_y = float(np.nanmin(pose_vid[k, 1:1+24, 1]))
        cam_pos = np.array([pelvis[0], 0.5, pelvis[2] + 4.5])
        _g1_render.draw_skeleton_3d(canvas, pose_vid[k], cam_pos,
                                     f_px=f_px_3d, ground_y=feet_y)
        writer.write(canvas)
    writer.release()
    print(f"[04] wrote {out_mp4} (fps={video_fps:.1f}, frames={video_frames})")
    print("[04] 完成")


if __name__ == "__main__":
    main()
