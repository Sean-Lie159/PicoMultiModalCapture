using UnityEngine;

namespace PicoMultiModalCapture
{
    // 第一人称视频录制：将主相机渲染到 RenderTexture，读取像素后以 RGBA 字节流
    // 推送给 NativeVideoEncoder（Android 端由 MediaCodec 编码为 H.264 MP4）。
    public class VideoRecorder
    {
        private Camera cam;
        private RenderTexture rt;
        private Texture2D tex;
        private NativeVideoEncoder enc;
        private int w, h;

        private int frameCount;
        private float lastLog;

        public void Start(Camera camera, int width, int height, int fps, string path)
        {
            cam = camera;
            w = width; h = height;
            rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
            rt.Create();
            tex = new Texture2D(width, height, TextureFormat.RGBA32, false);
            enc = new NativeVideoEncoder();
            enc.Init(path, width, height, fps);
            Debug.Log("[VideoRecorder] Start cam=" + (cam != null ? cam.name : "null") + " size=" + width + "x" + height + " fps=" + fps);
        }

        public void CaptureFrame()
        {
            frameCount++;
            if (cam == null || enc == null) return;
            // XRCameraTracker 会禁用主相机（cam.enabled=false）以让 XR 接管渲染。
            // 被禁用的相机调用 Render() 不会产生任何帧。因此此处临时启用相机，
            // 手动渲染到 RT 后再恢复原始状态，保证能捕获透视画面。
            bool wasEnabled = cam.enabled;
            var prevTarget = cam.targetTexture;
            try
            {
                cam.enabled = true;
                cam.targetTexture = rt;
                cam.Render();
            }
            catch (System.Exception e)
            {
                Debug.LogWarning("[VideoRecorder] RenderToRT failed: " + e.Message);
            }
            finally
            {
                cam.targetTexture = prevTarget;
                cam.enabled = wasEnabled;
            }

            RenderTexture.active = rt;
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            RenderTexture.active = null;

            byte[] rgba = tex.GetRawTextureData();
            enc.EncodeFrame(rgba);

            // 诊断：每 30 帧打印一次，确认 CaptureFrame 被调用且 RT 有有效像素
            if (frameCount % 30 == 0 || frameCount == 1)
            {
                // 检查 RT 是否有有效内容（非全黑）：采样几个像素
                bool hasContent = false;
                if (tex != null)
                {
                    var p = tex.GetPixel(w / 2, h / 2);
                    hasContent = p.a > 0.01f || p.r > 0.01f || p.g > 0.01f || p.b > 0.01f;
                }
                Debug.Log("[VideoRecorder] frame=" + frameCount + " rgbaLen=" + (rgba != null ? rgba.Length : 0) + " center=" + (hasContent ? "content" : "EMPTY"));
            }
        }

        public void Stop()
        {
            enc?.Finish();
            if (rt != null) { rt.Release(); Object.Destroy(rt); rt = null; }
            if (tex != null) { Object.Destroy(tex); tex = null; }
        }
    }
}
