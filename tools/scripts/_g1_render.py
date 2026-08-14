# -*- coding: utf-8 -*-
"""
_g1_render.py — 人骨架 3D 透视可视化（供 04/06 复用）。

实现：把 PICO 采集的 Unity Y-up 世界系关节位置，用针孔透视投影画到 2D 画布，
并叠加地面网格 + 按深度排序的骨头连线 + 关节球，形成"3D 动捕骨架"效果。

（历史说明：本模块早期承载 URDF G1 渲染（FK/Lambert/STL），因 URDF 重定向在
本离线数据管线内无法达到参考图级别的完整真实效果，已按决策 B 移除 URDF 相关代码，
仅保留骨架 3D 可视化部分。）
"""
from __future__ import annotations

import numpy as np
import cv2


def _project_to_2d(points_unity, cam_pos, f_px, w, h, v_offset=0.0):
    """Unity Y-up 世界点 -> 屏幕 2D + 深度（透视投影，相机看向 -Z）。

    cam_pos: 相机在 Unity 世界的位置（如 (0, 0, 3) 看向 -Z，即看向原点）。
    points_unity: (N, 3) Unity Y-up 世界点。
    v_offset: 画布垂直偏移（正数下移）。
    返回: (u, v, z_cam, valid) 数组。
    """
    rel = points_unity - cam_pos
    z_cam = -rel[:, 2]                 # 相机看向 -Z，所以 -rel.z 才是相机前方
    valid = z_cam > 0.05
    z_safe = np.where(valid, z_cam, 1.0)
    u = rel[:, 0] / z_safe * f_px + w / 2
    v = -rel[:, 1] / z_safe * f_px + h / 2 + v_offset
    return u, v, z_cam, valid


def draw_skeleton_3d(canvas, pose_k, cam_pos, f_px=None,
                     ground_center=None, ground_y=0.0, draw_ground=True):
    """3D 透视投影绘制人骨架（身体 24 + 手部 26x2）。

    pose_k: (J, 7) 单帧位姿（Unity Y-up 世界系），索引布局同 _align.build_pose_arrays:
      0=head, 1..24=body, 25..=left hand, ...=right hand。
    cam_pos: 相机在 Unity 世界的位置（跟随 Pelvis/head 即可保持人在画面中央）。
    ground_center: 地面网格中心 (x, z)，默认取 pose 所有点 x/z 均值。
    f_px: 焦距（像素），默认 w*1.1。
    返回: 画好的 canvas。
    """
    from _00_common import BODY_BONES, BODY_JOINT_NAMES, HAND_JOINT_NAMES
    from _04_hand_topo import HAND_BONES, BODY_COLORS, HAND_COLORS

    h, w = canvas.shape[:2]
    if f_px is None:
        f_px = w * 1.1
    body_n = len(BODY_JOINT_NAMES)
    hand_n = len(HAND_JOINT_NAMES)
    body_start, left_start, right_start = 1, 1 + body_n, 1 + body_n + hand_n

    def proj(idx):
        u, v, z, valid = _project_to_2d(pose_k[idx:idx + 1, :3], cam_pos, f_px, w, h)
        return u[0], v[0], z[0], valid[0]

    # 地面网格（Unity XZ 平面，Y=地面；PICO 系 floor origin 即 Y=0）
    if draw_ground:
        valid_pts = pose_k[1:1 + body_n, :3]
        valid_pts = valid_pts[np.isfinite(valid_pts).all(axis=1)]
        if ground_center is None:
            if len(valid_pts):
                ground_center = (float(valid_pts[:, 0].mean()), float(valid_pts[:, 2].mean()))
            else:
                # 回退：取 Pelvis/Head 任一有限点
                for idx in (1, 0):
                    p = pose_k[idx, :3]
                    if np.isfinite(p).all():
                        ground_center = (float(p[0]), float(p[2]))
                        break
        if ground_center is not None:
            cxw, czw = ground_center
            grid_color = (110, 120, 140)
            ext, step = 1.8, 0.3
            for gx in np.arange(cxw - ext, cxw + ext + 1e-6, step):
                pts3 = np.array([[gx, ground_y, czw - ext], [gx, ground_y, czw + ext]], np.float32)
                u_g, v_g, zg, vg = _project_to_2d(pts3, cam_pos, f_px, w, h)
                if vg[0] and vg[1]:
                    p1 = (int(np.clip(u_g[0], -w, 2*w)), int(np.clip(v_g[0], -h, 2*h)))
                    p2 = (int(np.clip(u_g[1], -w, 2*w)), int(np.clip(v_g[1], -h, 2*h)))
                    cv2.line(canvas, p1, p2, grid_color, 1, cv2.LINE_AA)
            for gz in np.arange(czw - ext, czw + ext + 1e-6, step):
                pts3 = np.array([[cxw - ext, ground_y, gz], [cxw + ext, ground_y, gz]], np.float32)
                u_g, v_g, zg, vg = _project_to_2d(pts3, cam_pos, f_px, w, h)
                if vg[0] and vg[1]:
                    p1 = (int(np.clip(u_g[0], -w, 2*w)), int(np.clip(v_g[0], -h, 2*h)))
                    p2 = (int(np.clip(u_g[1], -w, 2*w)), int(np.clip(v_g[1], -h, 2*h)))
                    cv2.line(canvas, p1, p2, grid_color, 1, cv2.LINE_AA)

    # 骨头连线（按深度排序，远的先画）
    bones = []
    for a, b in BODY_BONES:
        ua, va, za, va_ = proj(body_start + a)
        ub, vb, zb, vb_ = proj(body_start + b)
        if va_ and vb_:
            bones.append((min(za, zb), (int(ua), int(va)), (int(ub), int(vb)), (200, 200, 200), 4))
    for s, col in ((left_start, HAND_COLORS["L"]), (right_start, HAND_COLORS["R"])):
        for a, b in HAND_BONES:
            ua, va, za, va_ = proj(s + a)
            ub, vb, zb, vb_ = proj(s + b)
            if va_ and vb_:
                bones.append((min(za, zb), (int(ua), int(va)), (int(ub), int(vb)), col, 3))
    bones.sort(key=lambda t: t[0])
    for d, p1, p2, col, th in bones:
        cv2.line(canvas, p1, p2, col, th)

    # 关节球
    for i in range(body_n):
        u, v, z, val = proj(body_start + i)
        if val:
            cv2.circle(canvas, (int(u), int(v)), 8, BODY_COLORS[i], -1)
            cv2.circle(canvas, (int(u), int(v)), 8, (0, 0, 0), 1)
    for i in range(hand_n):
        for s in (left_start, right_start):
            u, v, z, val = proj(s + i)
            if val:
                cv2.circle(canvas, (int(u), int(v)), 5, (255, 255, 255), -1)
                cv2.circle(canvas, (int(u), int(v)), 5, (0, 0, 0), 1)
    return canvas
