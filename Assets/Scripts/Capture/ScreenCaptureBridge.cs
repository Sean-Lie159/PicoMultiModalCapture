using UnityEngine;

namespace PicoMultiModalCapture
{
    /// 桥接 Android 的 MediaProjection 屏幕捕获（捕获含 passthrough 透视的真实画面）。
    /// 通过 AndroidJavaObject 调用 VolumeKeyActivity 的静态方法。
    /// 首次录制前需先调用 RequestPermission() 请求授权（弹窗）。
    public static class ScreenCaptureBridge
    {
        private const string PackageName = "com.DefaultCompany.PicoMultiModalCapture";

        static AndroidJavaObject GetActivityInstance()
        {
            try
            {
                using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                {
                    return unityPlayer.GetStatic<AndroidJavaObject>("currentActivity");
                }
            }
            catch (System.Exception e)
            {
                Debug.LogWarning("[ScreenCaptureBridge] get activity failed: " + e.Message);
                return null;
            }
        }

        static AndroidJavaClass GetActivityClass()
        {
            try
            {
                return new AndroidJavaClass(PackageName + ".VolumeKeyActivity");
            }
            catch (System.Exception e)
            {
                Debug.LogWarning("[ScreenCaptureBridge] get class failed: " + e.Message);
                return null;
            }
        }

        // 请求屏幕捕获授权（首次弹窗）
        public static void RequestPermission()
        {
            using (var cls = GetActivityClass())
            {
                if (cls != null) cls.CallStatic("RequestScreenPermission");
            }
        }

        // 开始屏幕捕获到指定路径
        public static void StartRecording(string filePath)
        {
            using (var cls = GetActivityClass())
            {
                if (cls != null) cls.CallStatic("StartScreenCapture", filePath);
            }
        }

        // 停止屏幕捕获
        public static void StopRecording()
        {
            using (var cls = GetActivityClass())
            {
                if (cls != null) cls.CallStatic("StopScreenCapture");
            }
        }

        // 是否已获得授权
        public static bool HasPermission()
        {
            using (var cls = GetActivityClass())
            {
                if (cls == null) return false;
                return cls.CallStatic<bool>("HasScreenPermission");
            }
        }
    }
}
