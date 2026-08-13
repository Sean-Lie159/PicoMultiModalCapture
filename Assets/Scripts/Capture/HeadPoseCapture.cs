using UnityEngine;
using UnityEngine.XR;

namespace PicoMultiModalCapture
{
    // 头部 6DoF：优先用 InputTracking 读取头显（CenterEye）实时位姿。
    // 不能依赖 Camera.main.transform —— OpenXR 接管渲染后 XRCameraTracker 会禁用相机
    // （cam.enabled=false），其 transform.position 被固定在 (0,0,0) 且不再更新。
    // 时间戳与其它模态在 CaptureManager 同一帧循环内严格对齐。
    public static class HeadPoseCapture
    {
        public static HeadSample Capture(Camera mainCamera)
        {
            var s = new HeadSample();

            // 主方案：InputTracking 头显实时位姿（与 OpenXR 追踪空间同步）
            Vector3 p = InputTracking.GetLocalPosition(XRNode.CenterEye);
            Quaternion q = InputTracking.GetLocalRotation(XRNode.CenterEye);

            // 回退：若头显位姿为零（未初始化），用相机 transform（若相机 transform 有效）
            if (p == Vector3.zero && q == Quaternion.identity && mainCamera != null)
            {
                p = mainCamera.transform.position;
                q = mainCamera.transform.rotation;
            }

            s.px = p.x; s.py = p.y; s.pz = p.z;
            s.qx = q.x; s.qy = q.y; s.qz = q.z; s.qw = q.w;
            s.confidence = 1f;
            return s;
        }
    }
}
