# -*- coding: utf-8 -*-
"""
_align.py — 位姿-视频时间对齐与插值工具（逐帧对齐，方案 A）。

背景：
  - data.json 的位姿采样率约 26fps（747 帧 / 29.47s），
  - 而 video.mp4 为 60fps（1737 帧 / 28.95s），两者异频且帧数不等。
  - 为让"骨架动画"与"视频每一帧"严格同步，需按时间轴把低采样位姿
    插值（重采样）到视频每一帧对应时刻。

方法：
  - 视频帧时刻 t_vid[k] = k / video_fps（视频帧均匀）
  - 对每个 t_vid[k]，在 data.json 位姿时间戳 t_pose 中找到前后两帧 [i, i+1]，
    线性插值位置 (LERP)、球面插值四元数 (Slerp)：
        q_slerp = q_i * sin((1-f)*Ω)/sinΩ + q_{i+1} * sin(f*Ω)/sinΩ
  - 覆盖头部 6DoF、身体 24 关节、左右手各 26 关节（每关节 位置3 + 旋转4）。
  - 边界：t_vid 早于首帧用首帧；晚于末帧用末帧（hold）。

输出：
  - 与视频逐帧对应的插值位姿数组，shape = (video_frames, joints_total, 7)
  - 提供关节名顺序，便于可视化按拓扑连线。

注意：该模块不依赖 OpenCV，纯 numpy 实现，便于复用。
"""
from __future__ import annotations

import numpy as np

from _00_common import BODY_JOINT_NAMES, HAND_JOINT_NAMES


def build_pose_arrays(data: dict):
    """从 data.json 提取逐帧位姿矩阵 (N, total, 7) 与时间戳 (N,)。

    列顺序 = 头部(1) + 身体(24) + 左手(26) + 右手(26)，每项 [px,py,pz,qx,qy,qz,qw]。
    返回 (t_array, pose_array, joint_names)。
    """
    frames = data.get("frames", [])
    n = len(frames)
    # 1 head + 24 body + 26 L + 26 R
    names = ["head"] + BODY_JOINT_NAMES + \
            [f"L_{h}" for h in HAND_JOINT_NAMES] + \
            [f"R_{h}" for h in HAND_JOINT_NAMES]
    total = len(names)
    t_arr = np.zeros(n, dtype=np.float64)
    pose = np.zeros((n, total, 7), dtype=np.float64)
    # 每帧每只手是否被追踪到（joints 非空 且 tracked）
    hand_tracked = np.zeros((n, 2), dtype=bool)  # [:,0]=left, [:,1]=right

    for i, f in enumerate(frames):
        t_arr[i] = float(f.get("t", 0.0))
        # head
        hp = f.get("head", {})
        pose[i, 0] = _get_pose(hp)
        # body 24 (按 BODY_JOINT_NAMES 顺序)
        bj = {j.get("name"): j for j in f.get("body", {}).get("joints", [])}
        for k, name in enumerate(BODY_JOINT_NAMES, start=1):
            pose[i, k] = _get_pose(bj.get(name))
        # left hand 26
        lj = {j.get("name"): j for j in f.get("hands", {}).get("left", {}).get("joints", [])}
        base = 1 + len(BODY_JOINT_NAMES)
        for k, name in enumerate(HAND_JOINT_NAMES):
            pose[i, base + k] = _get_pose(lj.get(name))
        hand_tracked[i, 0] = bool(lj) and bool(
            f.get("hands", {}).get("left", {}).get("tracked", bool(lj)))
        # right hand 26
        rj = {j.get("name"): j for j in f.get("hands", {}).get("right", {}).get("joints", [])}
        base = 1 + len(BODY_JOINT_NAMES) + len(HAND_JOINT_NAMES)
        for k, name in enumerate(HAND_JOINT_NAMES):
            pose[i, base + k] = _get_pose(rj.get(name))
        hand_tracked[i, 1] = bool(rj) and bool(
            f.get("hands", {}).get("right", {}).get("tracked", bool(rj)))

    # 层面 A：手部丢失时用手腕保持位置 + 短时插值，避免塌缩到原点
    _fix_lost_hands(pose, hand_tracked)

    return t_arr, pose, names


def _fix_lost_hands(pose, hand_tracked, short_win=15):
    """层面 A：手部丢失时修正，避免手部关节塌缩到世界原点。

    原理：
      - 采集端在手部从视野丢失/被遮挡/追踪失败时，把 hands.{left,right}.joints
        置为空列表并 tracked=False。此时 pose 里该手 26 关节被 _get_pose 填为
        全零 [0,0,0]，骨架可视化会把整手画到世界原点（"手掉下去/塌缩成团"）。
      - 但身体 LeftWrist/RightWrist 通常仍被身体追踪（手部丢失 ≠ 手臂丢失）。
        因此：把手部关节整体"钉"在身体手腕位置附近，手形用最近有效帧的姿态
        （短丢失段在前后有效帧之间插值），这样手会停在合理位置而不是跳到原点。

    参数：
      pose: (N, total, 7) 就地修正。
      hand_tracked: (N, 2) bool，[:,0]=left, [:,1]=right。
      short_win: 短丢失段帧数阈值；段长 ≤ 此值则前后插值，否则保持最后有效手形。
    """
    n_body = len(BODY_JOINT_NAMES)          # 24
    n_hand = len(HAND_JOINT_NAMES)          # 26
    # 身体 Wrist / Elbow 在 pose 列（body 从索引1开始）
    lw_col = 1 + BODY_JOINT_NAMES.index("LeftWrist")
    rw_col = 1 + BODY_JOINT_NAMES.index("RightWrist")
    le_col = 1 + BODY_JOINT_NAMES.index("LeftElbow")
    re_col = 1 + BODY_JOINT_NAMES.index("RightElbow")
    # 手部 Wrist 是 HAND_JOINT_NAMES[0]
    hand_base_l = 1 + n_body                # 左手起始列
    hand_base_r = 1 + n_body + n_hand       # 右手起始列

    def _fill_hand(col_base, wrist_col, elbow_col, tracked):
        """col_base: 手部26关节起始列；wrist_col: 身体手腕列；elbow_col: 身体肘部列；
        tracked: (N,) bool。"""
        # 手部 Wrist（手部根）列 = col_base + 0
        # 遍历每一帧，对丢失帧做修正
        # 先找丢失段
        n = len(tracked)
        # 段起点过渡帧数（平滑度尽量低）：只消除丢失瞬间的 0.1m/84° 硬跳
        transition_frames = 3
        blend_frames = 6
        i = 0
        while i < n:
            if tracked[i]:
                i += 1
                continue
            # 进入丢失段
            s = i
            while i < n and not tracked[i]:
                i += 1
            e = i - 1  # 段结束（含）
            # 段前有效帧 ps（s-1），段后有效帧 pe（e+1）
            ps = s - 1
            pe = e + 1
            seg_len = e - s + 1
            # 手形模板来源（含手腕旋转，用于长段旋转跟随）
            if ps >= 0:
                tpl_pos, tpl_wrist, tpl_q = _hand_template(pose, col_base, wrist_col, ps)
            elif pe < n:
                tpl_pos, tpl_wrist, tpl_q = _hand_template(pose, col_base, wrist_col, pe)
            else:
                # 前后都没有有效帧，无法修正，跳过
                continue
            # 段前身体手腕位置/旋转（用于起点过渡起点）
            if ps >= 0:
                ps_w = pose[ps, wrist_col, :3].copy()
                ps_q = pose[ps, wrist_col, 3:7].copy()
                if np.linalg.norm(ps_q) < 1e-4:
                    ps_q = np.array([0.0, 0.0, 0.0, 1.0])
            else:
                ps_w = tpl_wrist.copy()
                ps_q = tpl_q.copy()
            # 段后模板（用于短段插值 / 长段末渐入）
            tpl_pos_e = None
            tpl_wrist_e = None
            tpl_q_e = None
            if pe < n:
                tpl_pos_e, tpl_wrist_e, tpl_q_e = _hand_template(pose, col_base, wrist_col, pe)
            # 前臂 IK 长度约束参考值：缺失前（ps）的前臂长度 |Elbow-Wrist|
            ref_arm_len = None
            if ps >= 0:
                el_ps = pose[ps, elbow_col, :3]
                wr_ps = pose[ps, wrist_col, :3]
                ref_arm_len = float(np.linalg.norm(wr_ps - el_ps))
            elif pe < n:
                el_pe = pose[pe, elbow_col, :3]
                wr_pe = pose[pe, wrist_col, :3]
                ref_arm_len = float(np.linalg.norm(wr_pe - el_pe))
            # 逐帧填充
            # 长段用 EMA 轻平滑身体手腕位置/旋转，消除逐帧小抖动传入手指团
            ema_pos = None
            ema_q = None
            ema_alpha = 0.5   # EMA 平滑系数（轻平滑，延迟约 1-2 帧）
            for j in range(s, e + 1):
                wj = pose[j, wrist_col, :3]
                wq = pose[j, wrist_col, 3:7]
                if np.linalg.norm(wq) < 1e-4:
                    wq = np.array([0.0, 0.0, 0.0, 1.0])
                # 前臂 IK 长度约束：若当前前臂长与参考长差异大，把腕部沿 Elbow->Wrist
                # 方向拉/推到参考长度，使腕部始终在前臂末端（修复采集端前臂长度跳变）。
                if ref_arm_len is not None and ref_arm_len > 1e-4:
                    el_j = pose[j, elbow_col, :3]
                    dir_aw = wj - el_j
                    len_aw = float(np.linalg.norm(dir_aw))
                    if len_aw > 1e-6 and abs(len_aw - ref_arm_len) > 0.02:
                        wj = el_j + dir_aw / len_aw * ref_arm_len
                        pose[j, wrist_col, :3] = wj
                idx_in_seg = j - s
                if seg_len <= short_win and tpl_pos_e is not None:
                    # 短段：完全依赖前后有效帧插值（ps→pe），手严格在腕附近且平滑
                    f = (j - s + 1) / (seg_len + 1)  # 0..1 趋向 pe
                    root = (1.0 - f) * tpl_wrist + f * tpl_wrist_e
                    shape = (1.0 - f) * (tpl_pos - tpl_wrist) + f * (tpl_pos_e - tpl_wrist_e)
                    q_interp = _q_slerp_scalar(tpl_q, tpl_q_e, f)
                    dq = _q_mult(q_interp, _q_conjugate(tpl_q))
                    shape = np.array([_q_rotate_vec(dq, sv) for sv in shape])
                    pose[j, col_base:col_base + n_hand, :3] = root + shape
                else:
                    # 长段：手部根 = 身体手腕（严格钉在腕上），手指方向重设为
                    # **沿胳膊方向**（肘→腕延伸），让手"贴在胳膊上"，不脱离。
                    #   - EMA 轻平滑身体手腕位置，消除逐帧小抖动传入手指团。
                    #   - 段起点过渡（前 transition_frames 帧）：手部根从 ps 位置
                    #     平滑过渡到当前腕（消除丢失瞬间的 0.1m 硬跳）。
                    #   - 段内：手部根 = EMA 平滑后腕位。
                    #   - 手指：模板手形（缺失前）重排到"沿胳膊方向"。
                    #   - 段末（最后 blend_frames 帧）：向 pe 真实手部根/手形渐入。
                    # EMA 平滑手腕位置
                    if ema_pos is None:
                        ema_pos = wj.copy()
                    else:
                        ema_pos = ema_alpha * wj + (1.0 - ema_alpha) * ema_pos
                    # 起点过渡位置
                    if idx_in_seg < transition_frames and ps >= 0:
                        t = (idx_in_seg + 1) / (transition_frames + 1)
                        root = (1.0 - t) * ps_w + t * ema_pos
                    else:
                        root = ema_pos
                    # 手指沿胳膊方向：肘→腕方向
                    el = pose[j, elbow_col, :3]
                    arm_dir = root - el
                    arm_len = np.linalg.norm(arm_dir)
                    if arm_len < 1e-6:
                        arm_dir = np.array([0.0, 0.0, 1.0])
                    else:
                        arm_dir = arm_dir / arm_len
                    # 模板手指主方向（缺失前 Palm/MCP 相对腕的平均方向）
                    fwd = np.zeros(3)
                    cnt = 0
                    for k in (2, 5, 10, 15, 20):   # Palm / IndexMCP / MiddleMCP / RingMCP / PinkyMCP
                        off = tpl_pos[k] - tpl_wrist
                        if np.linalg.norm(off) > 1e-4:
                            fwd = fwd + off
                            cnt += 1
                    if cnt == 0 or np.linalg.norm(fwd) < 1e-6:
                        fwd = np.array([0.0, 0.0, 1.0])
                    else:
                        fwd = fwd / np.linalg.norm(fwd)
                    # 构建旋转：模板手指主方向 -> 胳膊方向
                    q_align = _q_align_vectors(fwd, arm_dir)
                    shape = np.array([_q_rotate_vec(q_align, sv)
                                      for sv in (tpl_pos - tpl_wrist)])
                    # 段末向 pe 渐入（位置 + 手形）
                    if pe < n and idx_in_seg >= seg_len - blend_frames:
                        t = (idx_in_seg - (seg_len - blend_frames)) / blend_frames
                        t = min(1.0, max(0.0, t))
                        root_blend = (1.0 - t) * root + t * tpl_wrist_e
                        if tpl_pos_e is not None:
                            shape_blend = (1.0 - t) * shape + t * (tpl_pos_e - tpl_wrist_e)
                        else:
                            shape_blend = shape
                        pose[j, col_base:col_base + n_hand, :3] = shape_blend + root_blend
                    else:
                        pose[j, col_base:col_base + n_hand, :3] = shape + root

    def _hand_template(pose, col_base, wrist_col, idx):
        """返回 idx 帧的手部26关节位置(不含旋转)、手腕位置、手腕旋转四元数。"""
        hand_pos = pose[idx, col_base:col_base + n_hand, :3].copy()
        # 手形参考：优先用该帧手部 Wrist（若有效），否则用身体手腕
        hw = pose[idx, col_base + 0, :3]
        if np.linalg.norm(hw) < 1e-6:
            hw = pose[idx, wrist_col, :3].copy()
        # 手腕旋转：优先用身体手腕旋转（已验证丢失帧时有效）；退化用单位四元数
        wq = pose[idx, wrist_col, 3:7]
        if np.linalg.norm(wq) < 1e-4:
            wq = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
        return hand_pos, hw, wq

    _fill_hand(hand_base_l, lw_col, le_col, hand_tracked[:, 0])
    _fill_hand(hand_base_r, rw_col, re_col, hand_tracked[:, 1])


def _get_pose(j):
    """从关节 dict 提取 [px,py,pz,qx,qy,qz,qw]；缺失置 0。"""
    if not j:
        return np.zeros(7, dtype=np.float64)
    pos = j.get("position")
    rot = j.get("rotation")
    out = np.zeros(7, dtype=np.float64)
    if pos:
        out[:3] = pos
    if rot:
        out[3:7] = rot
    return out


def _q_align_vectors(a, b):
    """构建四元数 q，把单位向量 a 旋转到单位向量 b（最短弧，处理平行/反向）。"""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    d = float(np.dot(a, b))
    if d > 0.9999:
        return np.array([0.0, 0.0, 0.0, 1.0])
    if d < -0.9999:
        # 反向：绕任一垂直轴转 180°
        perp = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        axis = np.cross(a, perp)
        axis = axis / np.linalg.norm(axis)
        return np.array([axis[0], axis[1], axis[2], 0.0])
    v = np.cross(a, b)
    w = 1.0 + d
    q = np.array([v[0], v[1], v[2], w])
    return q / np.linalg.norm(q)


def _q_rotate_vec(q, v):
    """用四元数 q=(qx,qy,qz,qw) 旋转向量 v（3,）→ (3,)。"""
    q = np.asarray(q, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    qv = q[:3]
    qw = q[3]
    # v' = v + 2*qv × (qv × v + qw*v)
    cross1 = np.cross(qv, v) + qw * v
    return v + 2.0 * np.cross(qv, cross1)


def _q_conjugate(q):
    """四元数共轭（qw 不变，虚部取反）。"""
    q = np.asarray(q, dtype=np.float64)
    return np.array([-q[0], -q[1], -q[2], q[3]], dtype=np.float64)


def _q_slerp_scalar(q0, q1, f):
    """标量四元数 (4,) 的球面插值，f∈[0,1]。用于单个四元数（非数组）。"""
    q0 = np.asarray(q0, dtype=np.float64)
    q1 = np.asarray(q1, dtype=np.float64)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        # 几乎平行，线性近似
        return q0 + f * (q1 - q0)
    theta = np.arccos(np.clip(dot, -1.0, 1.0))
    return (np.sin((1.0 - f) * theta) * q0 + np.sin(f * theta) * q1) / np.sin(theta)


def _q_mult(q1, q2):
    """四元数乘法 q1 * q2（Hamilton，顺序敏感）。"""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return np.array([
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    ], dtype=np.float64)


def _q_slerp(q0, q1, f):
    """两个四元数 (...,4, w 在最后) 的球面插值，f∈[0,1]。自动处理符号翻转。"""
    q0 = np.asarray(q0, dtype=np.float64)
    q1 = np.asarray(q1, dtype=np.float64)
    dot = np.sum(q0 * q1, axis=-1)
    # 符号翻转避免长弧路径
    neg = dot < 0
    q1 = q1.copy()
    q1[neg] = -q1[neg]
    dot[neg] = -dot[neg]
    dot = np.clip(dot, -1.0, 1.0)
    omega = np.arccos(dot)
    sin_omega = np.sin(omega)
    # 避免除零
    mask = np.abs(sin_omega) < 1e-6
    sin_omega = np.where(mask, 1.0, sin_omega)
    w0 = np.where(mask, 1.0 - f, np.sin((1.0 - f) * omega) / sin_omega)
    w1 = np.where(mask, f, np.sin(f * omega) / sin_omega)
    out = w0[..., None] * q0 + w1[..., None] * q1
    # 归一化
    norm = np.linalg.norm(out, axis=-1, keepdims=True)
    norm = np.where(norm < 1e-8, 1.0, norm)
    return out / norm


def resample_pose_to_video(t_arr, pose, video_frames, video_fps):
    """把 (N, J, 7) 位姿重采样到视频每帧 (V, J, 7)。

    t_arr: (N,) 位姿时间戳（秒）
    pose:   (N, J, 7) 位姿
    video_frames: 视频总帧数 V
    video_fps: 视频帧率
    返回 (V, J, 7)。位置线性插值，四元数 Slerp。
    """
    J = pose.shape[1]
    out = np.zeros((video_frames, J, 7), dtype=np.float64)
    for k in range(video_frames):
        tv = k / video_fps if video_fps > 0 else k
        i = np.searchsorted(t_arr, tv, side="right") - 1
        i = int(np.clip(i, 0, len(t_arr) - 2))
        t0, t1 = t_arr[i], t_arr[i + 1]
        dt = t1 - t0
        f = (tv - t0) / dt if dt > 0 else 0.0
        f = float(np.clip(f, 0.0, 1.0))
        # 位置（线性插值）
        p0 = pose[i, :, :3]
        p1 = pose[i + 1, :, :3]
        out[k, :, :3] = p0 * (1.0 - f) + p1 * f
        # 旋转（Slerp）
        out[k, :, 3:7] = _q_slerp(pose[i, :, 3:7], pose[i + 1, :, 3:7], f)
    return out


def video_frame_times(video_frames, video_fps):
    """视频每帧时刻（秒），均匀 k / fps。"""
    if video_fps <= 0:
        raise ValueError("video_fps must be > 0")
    return np.arange(video_frames, dtype=np.float64) / video_fps
