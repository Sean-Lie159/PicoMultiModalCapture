# -*- coding: utf-8 -*-
"""
02_build_lerobot.py — 将清洗后的位姿数据规范化为 LeRobot 标准格式。

遵循 LeRobot v2.1 / v3.0 目录规范：
  output/lerobot/
  ├── meta/
  │   ├── info.json          # 数据集元数据（fps, robot_type, features）
  │   ├── tasks.jsonl        # 任务描述列表
  │   └── stats.json         # 特征统计
  ├── data/chunk-000/
  │   └── episode_000000.parquet
  └── videos/chunk-000/      # 可选视频观测（本脚本可选切出左眼单目流）

列结构遵循"LeRobot 规范 + 自有全量骨骼列"：
  - 索引列：timestamp / frame_index / episode_index / task_index
  - 观测列：observation.head_pose(7)、observation.full_body(24*7)、
            observation.left_hand/right_hand(26*7)
  - 动作列：action（与观测骨骼同构，作为预留动作/重定向输出）
同时生成同构的 .json 文件，便于随时打开查看。

注意：data.json 手部在本样例中 tracked=false，关节全 0，脚本会自动检测并在
json/info 中标记，不报错。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import importlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _00_common as C  # noqa: E402
from _00_common import (  # noqa: E402
    ensure_output_dirs, load_data_json, load_meta,
    BODY_JOINT_NAMES, HAND_JOINT_NAMES,
)
import cv2  # noqa: E402

# 01_parse_data.py 模块名以数字开头，不能用常规 import，用 importlib 动态加载
_parse_mod = importlib.import_module("01_parse_data")
build_pose_rows = _parse_mod.build_pose_rows

EPISODE_INDEX = 0
TASK_INDEX = 0


def build_episode_table(rows, meta, task_desc=None):
    """由解析出的行构建 LeRobot episode DataFrame。"""
    fps = meta["session"].get("videoFps", 59)
    frame_count = len(rows)
    records = []
    for i, r in enumerate(rows):
        # 时间戳：从 episode 起始累计（秒）
        t = r["t"]

        # --- observation.head_pose [7] ---
        hp = np.array(r["head_position"] + r["head_rotation"], dtype=np.float32)

        # --- observation.full_body [24*7] ---
        fb = []
        for name in BODY_JOINT_NAMES:
            j = r["body_joints"].get(name)
            if j and j["position"] is not None:
                fb += list(j["position"]) + list(j["rotation"])
            else:
                fb += [0.0] * 7
        fb = np.array(fb, dtype=np.float32)

        # --- observation.left_hand / right_hand [26*7] ---
        lh, rh = [], []
        for name in HAND_JOINT_NAMES:
            j = r["left_joints"].get(name)
            lh += list(j["position"]) + list(j["rotation"]) if j and j["position"] else [0.0] * 7
            j2 = r["right_joints"].get(name)
            rh += list(j2["position"]) + list(j2["rotation"]) if j2 and j2["position"] else [0.0] * 7
        lh = np.array(lh, dtype=np.float32)
        rh = np.array(rh, dtype=np.float32)

        # --- action：与观测骨骼同构（预留动作/重定向输出占位）---
        action = np.concatenate([fb, lh, rh]).astype(np.float32)

        records.append({
            "timestamp": np.float32(t),
            "frame_index": np.int64(i),
            "episode_index": np.int64(EPISODE_INDEX),
            "task_index": np.int64(TASK_INDEX),
            "observation.head_pose": hp,
            "observation.full_body": fb,
            "observation.left_hand": lh,
            "observation.right_hand": rh,
            "action": action,
        })

    df = pd.DataFrame(records)
    return df, fps


def features_schema():
    """构造 info.json 的 features 字段。"""
    return {
        "observation.head_pose": {"dtype": "float32", "shape": [7],
                                  "names": ["px", "py", "pz", "qx", "qy", "qz", "qw"]},
        "observation.full_body": {"dtype": "float32", "shape": [24 * 7],
                                  "names": ["body_24x7"]},
        "observation.left_hand": {"dtype": "float32", "shape": [26 * 7],
                                  "names": ["left_hand_26x7"]},
        "observation.right_hand": {"dtype": "float32", "shape": [26 * 7],
                                   "names": ["right_hand_26x7"]},
        "action": {"dtype": "float32", "shape": [24 * 7 + 26 * 7 * 2], "names": ["action_fullbody_hands"]},
        "timestamp": {"dtype": "float32", "shape": [1]},
        "frame_index": {"dtype": "int64", "shape": [1]},
        "episode_index": {"dtype": "int64", "shape": [1]},
        "task_index": {"dtype": "int64", "shape": [1]},
    }


def build_info_json(df, fps, task_desc):
    meta = load_meta()
    session = meta["session"]
    hand_tracked = bool(df["observation.left_hand"].iloc[0].any() or
                        df["observation.right_hand"].iloc[0].any())
    info = {
        "repo_id": "pico4u-firstperson-human/v1",
        "total_episodes": 1,
        "total_frames": int(len(df)),
        "fps": int(fps),
        "robot_type": "PICO4Ultra-Human",
        "source": {
            "device": session.get("device"),
            "durationSec": session.get("durationSec"),
            "videoFile": session.get("videoFile"),
            "videoStereoLayout": session.get("videoStereoLayout"),
        },
        "coordinate_frame": meta["skeleton"].get("coordinateFrame"),
        "hand_tracked": hand_tracked,
        "task": task_desc or "",
        "features": features_schema(),
    }
    return info


def build_stats_json(df):
    """计算各数值特征列的均值/方差，用于归一化。"""
    stats = {"computed_on": "episode_000000", "features": {}}
    for col in ["observation.head_pose", "observation.full_body",
                "observation.left_hand", "observation.right_hand", "action"]:
        arr = np.stack(df[col].to_numpy())
        stats["features"][col] = {
            "mean": arr.mean(axis=0).tolist(),
            "std": arr.std(axis=0).tolist(),
            "min": arr.min(axis=0).tolist(),
            "max": arr.max(axis=0).tolist(),
        }
    return stats


def df_to_records_with_numpy(df):
    """将 DataFrame（含数组列）转成可直接 json.dump 的 dict 列表。"""
    out = []
    for _, row in df.iterrows():
        rec = {}
        for k, v in row.items():
            if isinstance(v, np.ndarray):
                rec[k] = v.tolist()
            elif isinstance(v, (np.float32, np.int64)):
                rec[k] = v.item()
            else:
                rec[k] = v
        out.append(rec)
    return out


def write_lerobot_video(out_dir, meta):
    """从 video.mp4 切左眼单目，写入 <out_dir>/videos/chunk-000/episode_000000.mp4。

    贴合 LeRobot 规范：videos/chunk-000/<episode>.mp4 为观测图像流。
    本脚本使用左眼单目（1280x720），与逐帧位姿时间轴一致（同一 video.mp4）。
    """
    src = str(C.VIDEO_MP4)
    vcap = cv2.VideoCapture(src)
    if not vcap.isOpened():
        print(f"[02][WARN] 无法打开 video.mp4（{src}），跳过 videos/ 写入")
        return None
    fps = vcap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = float(meta["session"].get("videoFps", 30))
    eye_w = meta["session"]["videoWidth"] // 2
    video_h = meta["session"]["videoHeight"]
    video_dir = out_dir / "videos" / "chunk-000"
    video_dir.mkdir(parents=True, exist_ok=True)
    out_path = video_dir / "episode_000000.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (eye_w, video_h))
    n = 0
    while True:
        ok, bgr = vcap.read()
        if not ok or bgr is None:
            break
        left = bgr[:, :eye_w, :]
        writer.write(left)
        n += 1
    vcap.release()
    writer.release()
    print(f"[02] wrote {out_path} (左眼 {eye_w}x{video_h}, {n} 帧, fps={fps:.1f})")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="生成 LeRobot 标准格式数据集")
    ap.add_argument("--input-dir", default=None, help="样例数据目录，默认项目根")
    ap.add_argument("--episode", default=0, type=int)
    ap.add_argument("--task", default="第一人称抓取演示", help="任务描述")
    ap.add_argument("--out", default=None, help="输出目录，默认 <样例>/output/lerobot")
    args = ap.parse_args()

    if args.input_dir:
        C.set_input_dir(args.input_dir)

    ensure_output_dirs()
    data = load_data_json()
    meta = load_meta()
    rows = build_pose_rows(data)

    df, fps = build_episode_table(rows, meta, args.task)
    print(f"[02] episode table: {len(df)} frames, {df.shape[1]} columns")

    out_dir = Path(args.out) if args.out else C.LERP_DIR
    meta_dir = out_dir / "meta"
    data_chunk = out_dir / "data" / "chunk-000"
    for d in (meta_dir, data_chunk, out_dir / "videos" / "chunk-000"):
        d.mkdir(parents=True, exist_ok=True)

    # ---- info.json ----
    info = build_info_json(df, fps, args.task)
    with open(meta_dir / "info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"[02] wrote {meta_dir / 'info.json'}")

    # ---- tasks.jsonl ----
    tasks_path = meta_dir / "tasks.jsonl"
    with open(tasks_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"task_index": TASK_INDEX, "task": args.task}, ensure_ascii=False) + "\n")
    print(f"[02] wrote {tasks_path}")

    # ---- stats.json ----
    stats = build_stats_json(df)
    with open(meta_dir / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False)
    print(f"[02] wrote {meta_dir / 'stats.json'}")

    # ---- episode parquet ----
    ep_name = f"episode_{args.episode:06d}"
    pq_path = data_chunk / f"{ep_name}.parquet"
    df.to_parquet(pq_path, index=False)
    print(f"[02] wrote {pq_path}")

    # ---- episode json（同构，方便查看）----
    js_path = data_chunk / f"{ep_name}.json"
    records = df_to_records_with_numpy(df)
    with open(js_path, "w", encoding="utf-8") as f:
        json.dump({"episode_index": args.episode, "task_index": TASK_INDEX,
                   "fps": int(fps), "frames": records},
                  f, ensure_ascii=False, indent=2)
    print(f"[02] wrote {js_path}")

    # ---- 观测视频（左眼单目）----
    write_lerobot_video(out_dir, meta)

    # ---- 手部追踪检测 ----
    if not info["hand_tracked"]:
        print("[02][INFO] 检测到手部关节全 0（样例未追踪手部），hand 列保留全 0 占位。")

    print("[02] 完成")


if __name__ == "__main__":
    main()
