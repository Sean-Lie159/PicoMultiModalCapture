# -*- coding: utf-8 -*-
"""
_04_hand_topo.py — 骨架可视化的共享拓扑与配色（供 04_skeleton_viz / 06_visualize 复用）。

包含：
  - HAND_BONES：手部 26 关节的连线拓扑（索引指向 HAND_JOINT_NAMES）
  - BODY_COLORS / HAND_COLORS：身体与手部的 BGR 配色
"""
from __future__ import annotations

from _00_common import BODY_JOINT_NAMES, HAND_JOINT_NAMES

_H = HAND_JOINT_NAMES
HAND_BONES = [
    (_H.index("Wrist"), _H.index("Palm")),
    (_H.index("Palm"), _H.index("ThumbMetacarpal")),
    (_H.index("Palm"), _H.index("IndexMetacarpal")),
    (_H.index("Palm"), _H.index("MiddleMetacarpal")),
    (_H.index("Palm"), _H.index("RingMetacarpal")),
    (_H.index("Palm"), _H.index("LittleMetacarpal")),
    (_H.index("ThumbMetacarpal"), _H.index("ThumbProximal")),
    (_H.index("ThumbProximal"), _H.index("ThumbDistal")),
    (_H.index("ThumbDistal"), _H.index("ThumbTip")),
    (_H.index("IndexMetacarpal"), _H.index("IndexProximal")),
    (_H.index("IndexProximal"), _H.index("IndexIntermediate")),
    (_H.index("IndexIntermediate"), _H.index("IndexDistal")),
    (_H.index("IndexDistal"), _H.index("IndexTip")),
    (_H.index("MiddleMetacarpal"), _H.index("MiddleProximal")),
    (_H.index("MiddleProximal"), _H.index("MiddleIntermediate")),
    (_H.index("MiddleIntermediate"), _H.index("MiddleDistal")),
    (_H.index("MiddleDistal"), _H.index("MiddleTip")),
    (_H.index("RingMetacarpal"), _H.index("RingProximal")),
    (_H.index("RingProximal"), _H.index("RingIntermediate")),
    (_H.index("RingIntermediate"), _H.index("RingDistal")),
    (_H.index("RingDistal"), _H.index("RingTip")),
    (_H.index("LittleMetacarpal"), _H.index("LittleProximal")),
    (_H.index("LittleProximal"), _H.index("LittleIntermediate")),
    (_H.index("LittleIntermediate"), _H.index("LittleDistal")),
    (_H.index("LittleDistal"), _H.index("LittleTip")),
]

BODY_COLORS = {}
for i, name in enumerate(BODY_JOINT_NAMES):
    if "Left" in name:
        BODY_COLORS[i] = (0, 140, 255)      # BGR 橙（左）
    elif "Right" in name:
        BODY_COLORS[i] = (255, 140, 0)      # BGR 蓝（右）
    else:
        BODY_COLORS[i] = (80, 200, 80)      # BGR 绿（主干）

HAND_COLORS = {
    "L": (200, 80, 255),   # 左手：洋红
    "R": (255, 220, 0),    # 右手：青黄
}
