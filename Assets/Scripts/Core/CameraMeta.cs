using UnityEngine;

namespace PicoMultiModalCapture
{
    // 双目 RGB 相机标定参数（左右眼内参/外参），供离线立体匹配/深度/点云使用。
    // 由 PICOFor4UCapture 从 PICO 企业服务（GetCameraParametersNewfor4U / GetCameraExtrinsicsfor4U）获取，
    // 经 CaptureManager 传给 DataExporter 写入 meta.json。
    public class CameraMeta
    {
        public bool available;          // 是否成功获取到真实相机参数（可能受 PICO 企业授权 getCameraInfo 影响）
        // 实际视频帧率（由 CaptureManager 依据编码帧数/录制时长计算，反映 Surface 直通后的真实 fps，如 60）
        public int actualVideoFps = 0;
        // 内参（对应单眼 1280x720）
        public double fx, fy, cx, cy;
        // 左相机外参（位置 + 四元数旋转）
        public float lpx, lpy, lpz;
        public float lqx, lqy, lqz, lqw;
        // 右相机外参
        public float rpx, rpy, rpz;
        public float rqx, rqy, rqz, rqw;
        // 双目基线（两相机光学中心距离，米）
        public float baseline;

        public CameraMeta()
        {
            available = false;
            fx = fy = cx = cy = 0;
            lpx = lpy = lpz = 0; lqx = lqy = lqz = lqw = 1;
            rpx = rpy = rpz = 0; rqx = rqy = rqz = rqw = 1;
            baseline = 0;
        }

        // 由左右外参位置计算基线长度（世界坐标下的欧氏距离）
        public void ComputeBaseline()
        {
            Vector3 l = new Vector3(lpx, lpy, lpz);
            Vector3 r = new Vector3(rpx, rpy, rpz);
            baseline = Vector3.Distance(l, r);
        }
    }
}
