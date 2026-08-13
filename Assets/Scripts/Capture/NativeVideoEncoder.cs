using UnityEngine;

namespace PicoMultiModalCapture
{
    // JNI 桥接到 Android 原生插件 com.picocapture.VideoEncoder（基于 MediaCodec+MediaMuxer）。
    // 非 Android 平台（编辑器）下为 no-op，便于在 Editor 中调试逻辑。
    public class NativeVideoEncoder : System.IDisposable
    {
        private AndroidJavaObject encoder;

        public void Init(string filePath, int w, int h, int fps)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            encoder = new AndroidJavaObject("com.picocapture.VideoEncoder", filePath, w, h, fps);
#else
            Debug.Log("[VideoEncoder] 非 Android 构建：视频编码为 no-op（不写文件）。");
#endif
        }

        public void EncodeFrame(byte[] rgba)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            if (encoder != null) encoder.Call("encodeFrame", rgba);
#endif
        }

        public void Finish()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            if (encoder != null) { encoder.Call("finish"); encoder.Dispose(); encoder = null; }
#endif
        }

        public void Dispose() { Finish(); }
    }
}
