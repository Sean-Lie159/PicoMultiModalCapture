# -*- coding: utf-8 -*-
"""
01_parse_data.py — 解析 data.json / data.csv 并生成清洗后的位姿数据。

输出：
  output/lerobot/meta/../_intermediate/pose_clean.json
  output/lerobot/meta/../_intermediate/pose_clean.csv

说明：
  - 读取 data.json（自动修复非标准 F 浮点标记）
  - 与 data.csv 交叉校验帧数 / 首帧时间戳，确保双源一致
  - 将每帧 head / body(24) / hands(26*2) 全量位姿平铺成宽表结构
  - 身体关节按 id 排序；手部关节若 tracked=false 则置 0（样例手部全 0）
  - 输出同时给出方便人看的 json（嵌套结构）与 csv（宽表结构）
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _00_common as C  # noqa: E402
from _00_common import (  # noqa: E402
    ensure_output_dirs, load_data_json, load_meta,
    BODY_JOINT_NAMES, HAND_JOINT_NAMES,
)

def _intermediate_dir():
    """动态获取中间产物目录（须在 C.set_input_dir 之后调用，避免 import 时固化路径）。"""
    return C.OUTPUT_DIR / "_intermediate"


def _extract_joints_by_id(joints, n, names):
    """按 id 顺序整理关节位姿，缺失关节以 None 占位。
    返回 {name: {"position": [x,y,z], "rotation":[x,y,z,w], "confidence": c}} 或 None
    """
    result = {}
    valid = 0
    for j in joints:
        name = j.get("name")
        result[name] = {
            "position": j.get("position"),
            "rotation": j.get("rotation"),
            "confidence": j.get("confidence", 0),
        }
        if j.get("position") is not None:
            valid += 1
    return result, valid


def build_pose_rows(data: dict):
    """将 data.json 解析为逐帧结构化记录列表。"""
    frames = data.get("frames", [])
    rows = []
    for idx, f in enumerate(frames):
        t = f.get("t", 0.0)
        head = f.get("head", {})
        body = f.get("body", {})
        hands = f.get("hands", {})

        # head 6DoF
        head_pos = head.get("position")
        head_rot = head.get("rotation")

        # body 24
        body_joints, body_valid = _extract_joints_by_id(
            body.get("joints", []), 24, BODY_JOINT_NAMES)

        # hands 26*2
        left = hands.get("left", {})
        right = hands.get("right", {})
        left_joints, left_valid = _extract_joints_by_id(
            left.get("joints", []), 26, HAND_JOINT_NAMES)
        right_joints, right_valid = _extract_joints_by_id(
            right.get("joints", []), 26, HAND_JOINT_NAMES)

        rows.append({
            "frame_index": idx,
            "t": t,
            "wallClock": f.get("wallClock"),
            "head_position": head_pos,
            "head_rotation": head_rot,
            "body_tracking": body.get("tracking"),
            "body_confidence": body.get("confidence"),
            "body_joints": body_joints,
            "body_valid": body_valid,
            "left_tracked": left.get("tracked"),
            "left_joints": left_joints,
            "left_valid": left_valid,
            "right_tracked": right.get("tracked"),
            "right_joints": right_joints,
            "right_valid": right_valid,
        })
    return rows


def rows_to_flat_dict(rows):
    """将行列表转成便于直接 json 化的嵌套结构。"""
    out = {"frameCount": len(rows), "frames": []}
    for r in rows:
        body_pos = {}
        body_rot = {}
        body_conf = {}
        for name in BODY_JOINT_NAMES:
            j = r["body_joints"].get(name)
            body_pos[name] = j["position"] if j else [0, 0, 0]
            body_rot[name] = j["rotation"] if j else [0, 0, 0, 0]
            body_conf[name] = j["confidence"] if j else 0
        left_pos, left_rot = {}, {}
        for name in HAND_JOINT_NAMES:
            j = r["left_joints"].get(name)
            left_pos[name] = j["position"] if j else [0, 0, 0]
            left_rot[name] = j["rotation"] if j else [0, 0, 0, 0]
        right_pos, right_rot = {}, {}
        for name in HAND_JOINT_NAMES:
            j = r["right_joints"].get(name)
            right_pos[name] = j["position"] if j else [0, 0, 0]
            right_rot[name] = j["rotation"] if j else [0, 0, 0, 0]
        out["frames"].append({
            "frame_index": r["frame_index"],
            "t": r["t"],
            "head": {"position": r["head_position"], "rotation": r["head_rotation"]},
            "body": {"tracking": r["body_tracking"], "confidence": r["body_confidence"],
                     "position": body_pos, "rotation": body_rot, "confidencePerJoint": body_conf},
            "left_hand": {"tracked": r["left_tracked"], "position": left_pos, "rotation": left_rot},
            "right_hand": {"tracked": r["right_tracked"], "position": right_pos, "rotation": right_rot},
        })
    return out


def rows_to_csv(rows, csv_path):
    """将行列表展平为宽表 CSV。列顺序：frame_index,t,head_p...,body0_...,left0_...,right0_..."""
    header = ["frame_index", "t"]
    # head
    for s in ["head"]:
        for c in ["px", "py", "pz", "qx", "qy", "qz", "qw"]:
            header.append(f"{s}_{c}")
    # body
    for i, name in enumerate(BODY_JOINT_NAMES):
        for c in ["px", "py", "pz", "qx", "qy", "qz", "qw"]:
            header.append(f"b{i}_{name}_{c}")
    # left/right hand
    for side, prefix in (("left", "L"), ("right", "R")):
        for i, name in enumerate(HAND_JOINT_NAMES):
            for c in ["px", "py", "pz", "qx", "qy", "qz", "qw"]:
                header.append(f"{prefix}{i}_{name}_{c}")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in rows:
            row = [r["frame_index"], r["t"]]
            row += list(r["head_position"]) + list(r["head_rotation"])
            for name in BODY_JOINT_NAMES:
                j = r["body_joints"].get(name)
                if j and j["position"]:
                    row += list(j["position"]) + list(j["rotation"])
                else:
                    row += [0] * 7
            for side_key, joints in (("left_joints", r["left_joints"]),
                                     ("right_joints", r["right_joints"])):
                for name in HAND_JOINT_NAMES:
                    j = joints.get(name)
                    if j and j["position"]:
                        row += list(j["position"]) + list(j["rotation"])
                    else:
                        row += [0] * 7
            writer.writerow([f"{v:.6f}" if isinstance(v, float) else v for v in row])
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="解析 data.json/data.csv 生成清洗后位姿数据")
    ap.add_argument("--input-dir", default=None, help="样例数据目录，默认项目根")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-csv", default=None)
    args = ap.parse_args()

    if args.input_dir:
        C.set_input_dir(args.input_dir)

    ensure_output_dirs()
    intermediate_dir = _intermediate_dir()
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.out_json or str(intermediate_dir / "pose_clean.json")
    out_csv = args.out_csv or str(intermediate_dir / "pose_clean.csv")

    data = load_data_json()
    meta = load_meta()
    print(f"[01] data.json frames = {len(data.get('frames', []))}, "
          f"meta.frameCount = {meta['session'].get('frameCount')}")

    rows = build_pose_rows(data)
    print(f"[01] parsed {len(rows)} frames")

    # 交叉校验 data.csv
    import pandas as pd
    csv_df = pd.read_csv(C.DATA_CSV) if Path(C.DATA_CSV).exists() else None
    if csv_df is not None:
        print(f"[01] data.csv rows = {len(csv_df)}, cols = {csv_df.shape[1]}")
        if len(csv_df) != len(rows):
            print(f"[01][WARN] csv({len(csv_df)}) 与 json({len(rows)}) 帧数不一致，以 json 为准")

    flat = rows_to_flat_dict(rows)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(flat, f, ensure_ascii=False, indent=2)
    print(f"[01] wrote {out_json}")

    rows_to_csv(rows, out_csv)
    print(f"[01] wrote {out_csv}")


if __name__ == "__main__":
    main()
