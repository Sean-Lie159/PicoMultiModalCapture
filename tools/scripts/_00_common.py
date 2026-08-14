# -*- coding: utf-8 -*-
"""
00_common.py — 公共常量、路径、关节名、LeRobot 列定义与工具函数。

这是整个处理管线的基础模块，所有其它脚本都从这里导入常量与工具。
数据来源说明：
  - meta.json    : 相机内参 / 外参 / 基线 / 会话信息
  - data.json    : 逐帧多模态位姿（head 6DoF + body 24 关节 + hand 26*2 关节）
  - video.mp4    : 双目 SBS 第一人称 RGB 视频

坐标系约定（来自采集端）：
  - 所有位姿定义在 Unity 世界坐标系（local floor space, Y-up, 地平面为原点）
  - head / hand / body 三模态共享同一世界坐标系，可直接对齐
  - 相机内参为单眼（1280x720），左右眼共用一个内参，基线约 6.4cm
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
WORKSPACE = Path(os.getcwd())
# 若脚本被其它 cwd 调用，回退到脚本同级的上级目录（即项目根）
_SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _SCRIPT_DIR.parent

# 默认输入目录：项目根目录（数据文件 meta.json/data.json/data.csv/video.mp4 位于此）
INPUT_DIR = PROJECT_ROOT

# 输入文件
META_JSON = INPUT_DIR / "meta.json"
DATA_JSON = INPUT_DIR / "data.json"
DATA_CSV = INPUT_DIR / "data.csv"
VIDEO_MP4 = INPUT_DIR / "video.mp4"

# 输出目录
SCRIPTS_DIR = _SCRIPT_DIR
OUTPUT_DIR = INPUT_DIR / "output"
LERP_DIR = OUTPUT_DIR / "lerobot"
DEPTH_DIR = OUTPUT_DIR / "depth"
POINTCLOUD_DIR = OUTPUT_DIR / "pointcloud"
POINTCLOUD_FRAMES_DIR = POINTCLOUD_DIR / "frames"
SKELETON_DIR = OUTPUT_DIR / "skeleton"
VIS_DIR = OUTPUT_DIR / "vis"

# 各输出子目录（用于统一建目录）
OUTPUT_SUBDIRS = [
    LERP_DIR / "meta",
    LERP_DIR / "data" / "chunk-000",
    LERP_DIR / "videos" / "chunk-000",
    DEPTH_DIR,
    POINTCLOUD_FRAMES_DIR,
    SKELETON_DIR,
    VIS_DIR,
]


def set_input_dir(path) -> None:
    """重定向输入目录（样例文件夹）。

    调用后，输入文件与输出目录会指向 <path>/meta.json 等及 <path>/output/。
    各脚本应在其 main() 解析 --input-dir 后调用本函数。
    由于脚本多使用 `from _00_common import META_JSON, ...` 形式（import 时绑定值），
    本函数会通过 exec 重绑定本模块的模块级变量；脚本内以属性方式访问即可保持一致。
    """
    global INPUT_DIR, META_JSON, DATA_JSON, DATA_CSV, VIDEO_MP4
    global OUTPUT_DIR, LERP_DIR, DEPTH_DIR, POINTCLOUD_DIR, POINTCLOUD_FRAMES_DIR
    global SKELETON_DIR, VIS_DIR, OUTPUT_SUBDIRS

    INPUT_DIR = Path(path).resolve()
    META_JSON = INPUT_DIR / "meta.json"
    DATA_JSON = INPUT_DIR / "data.json"
    DATA_CSV = INPUT_DIR / "data.csv"
    VIDEO_MP4 = INPUT_DIR / "video.mp4"

    OUTPUT_DIR = INPUT_DIR / "output"
    LERP_DIR = OUTPUT_DIR / "lerobot"
    DEPTH_DIR = OUTPUT_DIR / "depth"
    POINTCLOUD_DIR = OUTPUT_DIR / "pointcloud"
    POINTCLOUD_FRAMES_DIR = POINTCLOUD_DIR / "frames"
    SKELETON_DIR = OUTPUT_DIR / "skeleton"
    VIS_DIR = OUTPUT_DIR / "vis"
    OUTPUT_SUBDIRS = [
        LERP_DIR / "meta",
        LERP_DIR / "data" / "chunk-000",
        LERP_DIR / "videos" / "chunk-000",
        DEPTH_DIR,
        POINTCLOUD_FRAMES_DIR,
        SKELETON_DIR,
        VIS_DIR,
    ]


def ensure_output_dirs() -> None:
    """创建全部输出子目录。"""
    for d in OUTPUT_SUBDIRS:
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 非标准 JSON 标记修复
# ---------------------------------------------------------------------------
# data.json 中存在 PICO 输出的非标准浮点标记，如 :F2 / :F4 需替换为 :0
def fix_data_json(raw: str) -> str:
    return re.sub(r":F(\d)", r":0", raw)


def load_meta() -> dict:
    """读取 meta.json。"""
    with open(META_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data_json() -> dict:
    """读取 data.json，自动修复非标准浮点标记。"""
    with open(DATA_JSON, "r", encoding="utf-8") as f:
        raw = f.read()
    return json.loads(fix_data_json(raw))


# ---------------------------------------------------------------------------
# 关节命名
# ---------------------------------------------------------------------------
# 身体 24 关节（来自 meta.json skeleton.bodyJointNames）
BODY_JOINT_NAMES = [
    "Pelvis", "LeftHip", "RightHip", "Spine1", "LeftKnee", "RightKnee",
    "Spine2", "LeftAnkle", "RightAnkle", "Spine3", "LeftFoot", "RightFoot",
    "Neck", "LeftCollar", "RightCollar", "Head", "LeftShoulder",
    "RightShoulder", "LeftElbow", "RightElbow", "LeftWrist", "RightWrist",
    "LeftHand", "RightHand",
]

# 手部 26 关节（来自 meta.json skeleton.handJointNames）
HAND_JOINT_NAMES = [
    "Wrist", "Palm",
    "ThumbMetacarpal", "ThumbProximal", "ThumbDistal", "ThumbTip",
    "IndexMetacarpal", "IndexProximal", "IndexIntermediate", "IndexDistal", "IndexTip",
    "MiddleMetacarpal", "MiddleProximal", "MiddleIntermediate", "MiddleDistal", "MiddleTip",
    "RingMetacarpal", "RingProximal", "RingIntermediate", "RingDistal", "RingTip",
    "LittleMetacarpal", "LittleProximal", "LittleIntermediate", "LittleDistal", "LittleTip",
]

# 身体骨架连接拓扑（用于可视化连线），索引指向 BODY_JOINT_NAMES
BODY_BONES = [
    (0, 1),   # Pelvis - LeftHip
    (0, 2),   # Pelvis - RightHip
    (0, 3),   # Pelvis - Spine1
    (3, 6),   # Spine1 - Spine2
    (6, 9),   # Spine2 - Spine3
    (9, 12),  # Spine3 - Neck
    (12, 15), # Neck - Head
    (12, 13), # Neck - LeftCollar
    (12, 14), # Neck - RightCollar
    (13, 16), # LeftCollar - LeftShoulder
    (14, 17), # RightCollar - RightShoulder
    (16, 18), # LeftShoulder - LeftElbow
    (17, 19), # RightShoulder - RightElbow
    (18, 20), # LeftElbow - LeftWrist
    (19, 21), # RightElbow - RightWrist
    (20, 22), # LeftWrist - LeftHand
    (21, 23), # RightWrist - RightHand
    (1, 4),   # LeftHip - LeftKnee
    (2, 5),   # RightHip - RightKnee
    (4, 7),   # LeftKnee - LeftAnkle
    (5, 8),   # RightKnee - RightAnkle
    (7, 10),  # LeftAnkle - LeftFoot
    (8, 11),  # RightAnkle - RightFoot
]


def load_skeleton_names(meta: dict) -> tuple:
    """从 meta.json 加载骨架关节名（回退到内置默认）。"""
    skel = meta.get("skeleton", {})
    body = skel.get("bodyJointNames") or BODY_JOINT_NAMES
    hand = skel.get("handJointNames") or HAND_JOINT_NAMES
    return body, hand


# ---------------------------------------------------------------------------
# 四元数 / 位姿工具（Unity / OpenXR 坐标系：右手系，X 左 / Y 上 / Z 朝向页面内）
# 注意：与常见 OpenCV/机器人坐标系存在差别，涉及渲染/点云时需按约定处理。
# ---------------------------------------------------------------------------
def quat_conjugate(q):
    """四元数共轭。q=(x,y,z,w)。"""
    x, y, z, w = q
    return (-x, -y, -z, w)


def quat_multiply(q1, q2):
    """四元数相乘 q1*q2。q=(x,y,z,w)。"""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return (
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    )


def quat_rotate(q, v):
    """用四元数 q 旋转向量 v（v 为 3 元组或长度 3 的数组）。"""
    x, y, z, w = q
    vx, vy, vz = v
    # t = 2 * cross(q.xyz, v)
    tx = 2 * (y * vz - z * vy)
    ty = 2 * (z * vx - x * vz)
    tz = 2 * (x * vy - y * vx)
    # v' = v + w*t + cross(q.xyz, t)
    ox = vx + w * tx + (y * tz - z * ty)
    oy = vy + w * ty + (z * tx - x * tz)
    oz = vz + w * tz + (x * ty - y * tx)
    return (ox, oy, oz)


def quat_to_rotmat(q):
    """四元数 (x,y,z,w) -> 3x3 旋转矩阵 (numpy)。"""
    import numpy as np
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def pos_quat_to_4x4(pos, quat):
    """位置 + 四元数 -> 4x4 齐次变换矩阵 T_world_from_local。"""
    import numpy as np
    R = quat_to_rotmat(quat)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = pos
    return T


def invert_pose(pos, quat):
    """返回位姿 (pos,quat) 的逆变换 (pos', quat')。"""
    q_inv = quat_conjugate(quat)
    p_inv = quat_rotate(q_inv, (-pos[0], -pos[1], -pos[2]))
    return tuple(p_inv), q_inv
