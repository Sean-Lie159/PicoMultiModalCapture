using System.Collections.Generic;
using UnityEngine;
#if ENABLE_PICO_XR_SDK
using UnityEngine.XR.Hands;
#endif

namespace PicoMultiModalCapture
{
    // 双手各 26 关键点姿态。
    // PICO Unity OpenXR Integration SDK 1.4.0 本身不提供手部 API，
    // 手部追踪由 Unity 官方 XR Hands 包（com.unity.xr.hands）的 XRHandSubsystem 提供，
    // 恰好为 26 个关节（XRHandJointID.BeginMarker..EndMarker）。
    // 需在 OpenXR 设置中启用 "Hand Tracking Subsystem" 特性。
    public static class HandCapture
    {
        private static int diagCount;
#if ENABLE_PICO_XR_SDK
        private static XRHandSubsystem s_subsystem;
        private static readonly List<XRHandSubsystem> s_buffer = new List<XRHandSubsystem>();

        private static XRHandSubsystem GetSubsystem()
        {
            if (s_subsystem != null && s_subsystem.running) return s_subsystem;
            s_buffer.Clear();
            SubsystemManager.GetSubsystems(s_buffer);
            for (int i = 0; i < s_buffer.Count; i++)
            {
                if (s_buffer[i].running) { s_subsystem = s_buffer[i]; return s_subsystem; }
            }
            if (s_buffer.Count > 0)
            {
                s_subsystem = s_buffer[0];
                // 若存在但未运行，主动 Start（XRHandSubsystem 需 running 才能追踪手部）
                if (s_subsystem != null && !s_subsystem.running)
                {
                    try
                    {
                        s_subsystem.Start();
                        UnityEngine.Debug.Log("[HandCapture] XRHandSubsystem.Start() called");
                    }
                    catch (System.Exception e)
                    {
                        UnityEngine.Debug.LogWarning("[HandCapture] Start subsystem failed: " + e.Message);
                    }
                }
                return s_subsystem;
            }
            s_subsystem = null;
            return null;
        }
#endif

        public static HandSample CaptureLeft() { return Capture(true); }

        public static HandSample CaptureRight() { return Capture(false); }

        private static HandSample Capture(bool isLeft)
        {
            var sample = new HandSample { tracked = false, scale = 1f, joints = new List<JointSample>() };
#if ENABLE_PICO_XR_SDK
            var sub = GetSubsystem();
            if (sub == null)
            {
                // 每 120 帧诊断一次：subsystem 不存在
                if (++diagCount % 120 == 0) UnityEngine.Debug.Log("[HandCapture] XRHandSubsystem NOT found");
                return sample;
            }
            if (!sub.running)
            {
                if (++diagCount % 120 == 0) UnityEngine.Debug.Log("[HandCapture] XRHandSubsystem not running");
            }

            XRHand hand = isLeft ? sub.leftHand : sub.rightHand;
            if (!hand.isTracked)
            {
                if (++diagCount % 120 == 0)
                    UnityEngine.Debug.Log("[HandCapture] hand not tracked (isLeft=" + isLeft + ") subRunning=" + sub.running);
                return sample;
            }

            sample.tracked = true;
            // 关节 pose 已是世界坐标（相对 tracking origin/设备原点）。
            // 注意：XRHandJointID 的枚举值 == ToIndex()+1（BeginMarker/Wrist 枚举值=1 但 ToIndex=0）。
            // 循环变量 i 是 ToIndex，必须用 XRHandJointIDUtility.FromIndex(i)（即 (XRHandJointID)(i+1)）
            // 得到正确的关节 ID，否则强转 (XRHandJointID)i 会导致整体错位一位，Wrist 取到 Invalid 空关节。
            int begin = XRHandJointID.BeginMarker.ToIndex();
            int end = XRHandJointID.EndMarker.ToIndex();
            for (int i = begin; i < end && i - begin < CaptureConst.HandJointCount; i++)
            {
                var js = new JointSample { id = i - begin };
                XRHandJointID jointId = XRHandJointIDUtility.FromIndex(i);
                XRHandJoint joint = hand.GetJoint(jointId);
                if (jointId == XRHandJointID.Wrist)
                {
                    // PICO 有时把 Wrist(rootPose) 返回为 0；优先用真实 Wrist，若为 0 则用相邻 Palm 位置近似。
                    Pose wristPose = default;
                    bool wristOk = joint.TryGetPose(out wristPose);
                    if (wristOk && !(wristPose.position == Vector3.zero))
                    {
                        js.px = wristPose.position.x; js.py = wristPose.position.y; js.pz = wristPose.position.z;
                        js.qx = wristPose.rotation.x; js.qy = wristPose.rotation.y;
                        js.qz = wristPose.rotation.z; js.qw = wristPose.rotation.w;
                        js.confidence = 1f;
                    }
                    else if (hand.GetJoint(XRHandJointID.Palm).TryGetPose(out Pose palmPose))
                    {
                        // Wrist=0 → 用相邻 Palm 位置近似手腕世界位置
                        js.px = palmPose.position.x; js.py = palmPose.position.y; js.pz = palmPose.position.z;
                        js.qx = palmPose.rotation.x; js.qy = palmPose.rotation.y;
                        js.qz = palmPose.rotation.z; js.qw = palmPose.rotation.w;
                        js.confidence = 1f;
                    }
                    else
                    {
                        js.px = wristPose.position.x; js.py = wristPose.position.y; js.pz = wristPose.position.z;
                        js.qx = wristPose.rotation.x; js.qy = wristPose.rotation.y;
                        js.qz = wristPose.rotation.z; js.qw = wristPose.rotation.w;
                    }
                }
                else
                {
                    if (joint.TryGetPose(out Pose pose))
                    {
                        js.px = pose.position.x; js.py = pose.position.y; js.pz = pose.position.z;
                        js.qx = pose.rotation.x; js.qy = pose.rotation.y;
                        js.qz = pose.rotation.z; js.qw = pose.rotation.w;
                    }
                    if (joint.TryGetRadius(out float radius)) js.radius = radius;
                    js.confidence = (joint.trackingState & XRHandJointTrackingState.Pose) != 0 ? 1f : 0f;
                }
                sample.joints.Add(js);
            }
#endif
            return sample;
        }
    }
}
