using System.Collections.Generic;
using UnityEngine;
#if ENABLE_PICO_XR_SDK
using Unity.XR.OpenXR.Features.PICOSupport;
#endif

namespace PicoMultiModalCapture
{
    // 全身 24 关键点骨骼采集。
    // 依赖 PICO Motion Tracker（本项目使用 5 个：双腕/双踝/腰部），
    // 通过 PICO Unity OpenXR Integration SDK 的 BodyTrackingFeature 获取数据。
    // 需在 OpenXR 设置中启用 "PICO Body Tracking" 特性。
    public static class BodyCapture
    {
        private static bool started;

#if ENABLE_PICO_XR_SDK
        private static BodyTrackingData s_data;
        private static BodyTrackingGetDataInfo s_info;
#endif

        // 启动身体追踪。返回是否成功。
        public static bool StartTracking()
        {
            if (started) return true;
#if ENABLE_PICO_XR_SDK
            if (!BodyTrackingFeature.isEnable)
            {
                Debug.LogWarning("[BodyCapture] XR_BD_body_tracking 扩展未启用，请在 OpenXR 设置中勾选 PICO Body Tracking。");
                return false;
            }

            // 预分配 24 个关节数据槽位，供 native 层回填。
            s_data = new BodyTrackingData
            {
                roleDatas = new BodyTrackingRoleData[(int)BodyTrackerRole.ROLE_NUM]
            };
            s_info = new BodyTrackingGetDataInfo { displayTime = 0 };

            // 全身模式：BodyTrackerRole 0..23 全部返回数据。
            // boneLength 全部留 0 表示使用 SDK 默认骨长。
            var boneLength = new BodyTrackingBoneLength();
            int ret = BodyTrackingFeature.StartBodyTracking(BodyJointSet.BODY_JOINT_SET_BODY_FULL_START, boneLength);
            if (ret != 0)
            {
                Debug.LogWarning("[BodyCapture] StartBodyTracking 失败，返回码 " + ret + "。请确认 Motion Tracker 已连接并完成标定。");
                return false;
            }
            started = true;
            return true;
#else
            return false;
#endif
        }

        public static void StopTracking()
        {
            if (!started) return;
#if ENABLE_PICO_XR_SDK
            BodyTrackingFeature.StopBodyTracking();
#endif
            started = false;
        }

        // 打开 PICO Motion Tracker 标定 App（未标定时需先执行）。
        public static void OpenCalibrationApp()
        {
#if ENABLE_PICO_XR_SDK
            BodyTrackingFeature.StartMotionTrackerCalibApp();
#endif
        }

        // 返回：(是否有效, 整体置信度, 24 个关节采样)
        public static (bool, float, List<JointSample>) Capture()
        {
            var joints = new List<JointSample>();
#if ENABLE_PICO_XR_SDK
            if (!started || s_data.roleDatas == null) return (false, 0f, joints);

            if (BodyTrackingFeature.GetBodyTrackingData(ref s_info, ref s_data) != 0)
                return (false, 0f, joints);

            bool isTracking = false;
            var status = new BodyTrackingStatus();
            BodyTrackingFeature.GetBodyTrackingState(ref isTracking, ref status);

            float confidence;
            switch (status.stateCode)
            {
                case BodyTrackingStatusCode.BT_VALID: confidence = 1f; break;
                case BodyTrackingStatusCode.BT_LIMITED: confidence = 0.5f; break;
                default: confidence = 0f; break;
            }

            int count = (int)BodyTrackerRole.ROLE_NUM;
            for (int i = 0; i < count; i++)
            {
                var rd = s_data.roleDatas[i];
                var p = rd.localPose;
                joints.Add(new JointSample
                {
                    id = i,
                    px = (float)p.PosX,
                    py = (float)p.PosY,
                    pz = (float)p.PosZ,
                    qx = (float)p.RotQx,
                    qy = (float)p.RotQy,
                    qz = (float)p.RotQz,
                    qw = (float)p.RotQw,
                    radius = 0f,
                    confidence = rd.role == BodyTrackerRole.NONE_ROLE ? 0f : confidence
                });
            }
            return (isTracking, confidence, joints);
#else
            return (false, 0f, joints);
#endif
        }
    }
}
