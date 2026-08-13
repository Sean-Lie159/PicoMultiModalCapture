using System;
using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;

namespace PicoMultiModalCapture
{
    /// 通过 PICO Enterprise for4U 相机 API（CameraRenderingPlugin.so）获取 PICO 4 Ultra
    /// 双 RGB 彩色相机真实世界第一人称画面。不依赖 libPxrPlatform.so，与 OpenXR 共存不冲突。
    ///
    /// for4U 的 JNI 调用必须在 Unity 主线程（有正确类加载器），官方示例即主线程调用。
    /// 用协程在主线程分步初始化，避免阻塞；原生回调只置标记，主线程 Update 排空编码输出。
    ///
    /// 编码方案（方案 A，Surface 直通硬编码，已实测 60fps）：
    /// 用 MediaCodec.createInputSurface() 创建输入 Surface，把该 Surface 的 JNI 引用传给
    /// CameraRenderingPlugin.so 的 startPreview，让 PICO 相机把双目 SBS 帧直接渲染到这个
    /// Surface，由硬件编码器自动消费。完全绕开 CPU 的 rgbaToNv12 逐像素转换（旧 CPU 编码
    /// 管线仅 22fps），帧率提升到相机原始 ~60fps。主线程只需周期性 drain 编码输出写 MP4。
    public class PICOFor4UCapture : MonoBehaviour
    {
        // ===== struct =====
        [StructLayout(LayoutKind.Sequential)]
        struct CameraFrame
        {
            public uint width;
            public uint height;
            public uint size;
            public IntPtr data;
            public ulong time;
        }

        enum PXRCaptureRenderMode { LEFT = 0, RIGHT = 1, _3D = 2, INTERLACE = 3 }

        // ===== P/Invoke (CameraRenderingPlugin.so) =====
        public delegate void CapturelibCallBack(int type);
        [DllImport("CameraRenderingPlugin")] static extern void setCameraFrameBuffer(ref CameraFrame t);
        [DllImport("CameraRenderingPlugin")] static extern void setCapturelibCallBack(CapturelibCallBack callback);
        [DllImport("CameraRenderingPlugin")] static extern void setConfigureDefault();
        // 返回 bool（1=true 成功，0=false 失败）。openCameraAsync 原生日志证实返回 1=成功。
        [DllImport("CameraRenderingPlugin")] static extern bool openCameraAsync();
        [DllImport("CameraRenderingPlugin")] static extern bool closeCamera();
        [DllImport("CameraRenderingPlugin")] static extern bool startPerformance(int mode, int width, int height);
        // 方案 A（正式）：把相机画面直接渲染到任意传入的 Android Surface（MediaCodec 输入 Surface），
        // 绕开 CPU rgbaToNv12。原生签名见 PXR_EnterprisePlugin.cs: startPreview(IntPtr androidSurface,int mode,int w,int h)。
        // 实测（2026-08-07）startPreview + MediaCodec Surface 直通 = 60fps，SBS 双目正确。
        [DllImport("CameraRenderingPlugin")] static extern bool startPreview(IntPtr androidSurface, int mode, int width, int height);

        // ===== 字段 =====
        // 双目 SBS：宽为 2560（左右各 1280 并排），高 720。3D 模式输出左右拼接图。
        private int width = 2560, height = 720;
        // 双目 RGB 相机标定参数（内参/外参/基线），供离线立体匹配/深度/点云。
        // 在相机打开成功后获取，供 CaptureManager 写入 meta.json。
        public CameraMeta cameraMeta = new CameraMeta();
        private string outputPath;
        private Coroutine initCoroutine;
        private volatile bool running;
        private string error;

        // ===== 方案 A Surface 直通编码字段 =====
        private AndroidJavaObject encoder;        // SurfaceEncoder
        private IntPtr surfaceGlobalRef;          // MediaCodec 输入 Surface 的 JNI 全局引用（NewGlobalRef）
        private float drainTimer;
        private int encodedCount;
        private bool captureStarted;
        // 已编码帧数（drain 累计），供 CaptureManager 依据录制时长计算实际帧率写入 meta.json。
        public int ActualEncodedFrames => encodedCount;

        public string Error => error;
        public bool IsRunning => running;

        [AOT.MonoPInvokeCallback(typeof(CapturelibCallBack))]
        static void OnCaptureEvent(int type)
        {
            var inst = _instance;
            if (inst == null) return;
            if (type == 0)
            {
                inst.cameraFrameCount++; // 图像可用（原生线程），Surface 路径下无需取帧，只统计
            }
            else if (type == 1) inst.cameraOpened = true; // 相机打开完成
        }

        private int cameraFrameCount;

        private static PICOFor4UCapture _instance;
        private volatile bool cameraOpened;

        void Awake()
        {
            _instance = this;
        }

        // 主线程 Update：Surface 路径下相机异步渲染到 MediaCodec 输入 Surface，编码器自动消费，
        // 只需周期性 drain 编码输出写 MP4。
        void Update()
        {
            if (captureStarted && encoder != null)
            {
                drainTimer += Time.unscaledDeltaTime;
                if (drainTimer >= 0.05f) // 每 50ms drain 一次，拉取已编码帧
                {
                    drainTimer = 0f;
                    try
                    {
                        encodedCount = (int)encoder.Call<long>("encodeAndDrain");
                    }
                    catch (Exception e)
                    {
                        Debug.LogWarning("[PICOFor4UCapture] drain: " + e.Message);
                    }
                }
            }
        }

        // 协程在主线程初始化 for4U 相机
        public bool StartCapture(string path, int w, int h)
        {
            outputPath = path;
            // 双目 SBS（side-by-side）：3D 模式把左右 RGB 相机拼接成一张 2560x720 图输出（每眼 1280x720），
            // 单流单编码器编 2560x720 mp4，左右眼在解码后按宽/2 切分（与常见 SBS 立体单流格式一致）。
            // 编码走方案 A Surface 直通（MediaCodec 输入 Surface + startPreview），60fps。
            width = 2560;
            height = 720;
            error = null;
            running = true;
            Debug.Log("[PICOFor4UCapture] StartCapture (3D SBS Surface direct) called, size=" + width + "x" + height);
            initCoroutine = StartCoroutine(InitCoroutine());
            Debug.Log("[PICOFor4UCapture] coroutine started");
            return true;
        }

        // 获取双目 RGB 相机标定参数。相机内参对应单眼分辨率（1280x720，SBS 视频左/右各半）。
        // 需要 PICO 企业服务授权 getCameraInfo；失败则 CameraMeta.available=false（不阻断录制）。
        void FetchCameraParams()
        {
            try
            {
#if ENABLE_PICO_XR_SDK
                bool init = Unity.XR.PICO.TOBSupport.PXR_Enterprise.InitEnterpriseService(true);
                Debug.Log("[PICOFor4UCapture] InitEnterpriseService=" + init);
                // 单眼内参/外参（RGBCameraParamsNew 含 fx/fy/cx/cy + l_pos/l_rot/r_pos/r_rot）
                // 注：GetCameraIntrinsicsfor4U 已实测只返回 [cx,cy,fx,fy]（4 元素），无畸变系数；
                //     畸变系数需离线棋盘格标定（见 AGENTS.md DISTORTION COEFFICIENTS NOT EXPORTABLE）。
                var p = Unity.XR.PICO.TOBSupport.PXR_Enterprise.GetCameraParametersNewfor4U(1280, 720);
                if (p.fx > 0 || p.fy > 0 || p.cx > 0 || p.cy > 0 || p.l_pos != UnityEngine.Vector3.zero || p.r_pos != UnityEngine.Vector3.zero)
                {
                    cameraMeta.fx = p.fx; cameraMeta.fy = p.fy; cameraMeta.cx = p.cx; cameraMeta.cy = p.cy;
                    // 若 SDK 未返回 cx/cy（NaN/0），用分辨率中心兜底（单眼 1280x720 光心应为 640/360）。
                    if (double.IsNaN(cameraMeta.cy) || cameraMeta.cy <= 0) cameraMeta.cy = 720.0 / 2;
                    if (double.IsNaN(cameraMeta.cx) || cameraMeta.cx <= 0) cameraMeta.cx = 1280.0 / 2;
                    cameraMeta.lpx = p.l_pos.x; cameraMeta.lpy = p.l_pos.y; cameraMeta.lpz = p.l_pos.z;
                    cameraMeta.lqx = p.l_rot.x; cameraMeta.lqy = p.l_rot.y; cameraMeta.lqz = p.l_rot.z; cameraMeta.lqw = p.l_rot.w;
                    cameraMeta.rpx = p.r_pos.x; cameraMeta.rpy = p.r_pos.y; cameraMeta.rpz = p.r_pos.z;
                    cameraMeta.rqx = p.r_rot.x; cameraMeta.rqy = p.r_rot.y; cameraMeta.rqz = p.r_rot.z; cameraMeta.rqw = p.r_rot.w;
                    cameraMeta.available = true;
                    cameraMeta.ComputeBaseline();
                    Debug.Log(string.Format("[PICOFor4UCapture] cam params OK fx={0} fy={1} cx={2} cy={3} (raw) | baseline={4:F4} | lpos={5:F3},{6:F3},{7:F3} rpos={8:F3},{9:F3},{10:F3}",
                        p.fx, p.fy, p.cx, p.cy, cameraMeta.baseline, p.l_pos.x, p.l_pos.y, p.l_pos.z, p.r_pos.x, p.r_pos.y, p.r_pos.z));
                }
                else
                {
                    cameraMeta.available = false;
                    Debug.LogWarning("[PICOFor4UCapture] GetCameraParametersNewfor4U returned empty/zero -> PICO auth (getCameraInfo) may be missing");
                }
#else
                cameraMeta.available = false;
                Debug.LogWarning("[PICOFor4UCapture] ENABLE_PICO_XR_SDK not defined, camera params unavailable");
#endif
            }
            catch (Exception e)
            {
                cameraMeta.available = false;
                Debug.LogWarning("[PICOFor4UCapture] FetchCameraParams exception: " + e.Message);
            }
        }

        private IEnumerator InitCoroutine()
        {
            Debug.Log("[PICOFor4UCapture] InitCoroutine begin");
            try
            {
                Debug.Log("[PICOFor4UCapture] calling setConfigureDefault...");
                setConfigureDefault();
                Debug.Log("[PICOFor4UCapture] configured");

                Debug.Log("[PICOFor4UCapture] calling setCapturelibCallBack...");
                setCapturelibCallBack(OnCaptureEvent);

                Debug.Log("[PICOFor4UCapture] calling openCameraAsync...");
                bool open = openCameraAsync();
                Debug.Log("[PICOFor4UCapture] openCameraAsync returned=" + open);
                if (!open)
                {
                    error = "openCameraAsync failed";
                    Debug.LogError("[PICOFor4UCapture] " + error);
                    yield break;
                }
                Debug.Log("[PICOFor4UCapture] openCameraAsync OK, waiting for camera opened callback...");
            }
            catch (Exception e)
            {
                error = e.Message;
                Debug.LogError("[PICOFor4UCapture] init failed: " + e);
                yield break;
            }

            // 等待相机打开完成回调（type==1），期间不阻塞主线程（yield 不能在 try/catch 块内）
            float wait = 0f;
            while (!cameraOpened && wait < 8f)
            {
                yield return null;
                wait += Time.deltaTime;
            }
            if (!cameraOpened)
            {
                error = "camera open callback timeout";
                Debug.LogError("[PICOFor4UCapture] " + error);
                yield break;
            }
            Debug.Log("[PICOFor4UCapture] camera opened callback received");

            // 相机打开成功后，获取双目相机标定参数（内参/外参/基线），供 meta.json 导出。
            // 需要 PICO 企业服务授权（getCameraInfo token），失败时 CameraMeta.available=false，不阻断录制。
            FetchCameraParams();

            // ===== 方案 A：Surface 直通硬编码 =====
            // 创建 SurfaceEncoder，拿到 MediaCodec 输入 Surface 的 JNI 全局引用，
            // 走 startPreview 让相机 SBS 帧直接渲染到该 Surface，绕开 CPU rgbaToNv12。
            try
            {
                Debug.Log("[PICOFor4UCapture] creating SurfaceEncoder (" + width + "x" + height + ")");
                encoder = new AndroidJavaObject("com.picocapture.SurfaceEncoder", outputPath, width, height, 30);
                AndroidJavaObject surface = encoder.Call<AndroidJavaObject>("getInputSurface");
                if (surface == null)
                {
                    error = "getInputSurface null";
                    Debug.LogError("[PICOFor4UCapture] " + error);
                    yield break;
                }
                // GetRawObject 返回 local ref，转全局引用以保证 startPreview 跨帧调用仍有效。
                surfaceGlobalRef = AndroidJNI.NewGlobalRef(surface.GetRawObject());
                surface.Dispose();
                Debug.Log("[PICOFor4UCapture] input surface globalRef=" + surfaceGlobalRef);

                // startPreview 必须在主线程调用。相机已就绪（cameraOpened 回调），主线程调用不会阻塞。
                int mode = (int)PXRCaptureRenderMode._3D;
                bool started = startPreview(surfaceGlobalRef, mode, width, height);
                Debug.Log("[PICOFor4UCapture] startPreview mode=" + mode + " size=" + width + "x" + height + " returned=" + started);
                if (!started)
                {
                    error = "startPreview failed";
                    Debug.LogError("[PICOFor4UCapture] " + error);
                    yield break;
                }
                captureStarted = true;
                drainTimer = 0f;
                Debug.Log("[PICOFor4UCapture] capture started (surface direct) -> " + outputPath);
            }
            catch (Exception e)
            {
                error = e.Message;
                Debug.LogError("[PICOFor4UCapture] init failed: " + e);
            }
        }

        public void StopCapture()
        {
            running = false;
            captureStarted = false;
            if (initCoroutine != null) { StopCoroutine(initCoroutine); initCoroutine = null; }

            // closeCamera 是 JNI 调用，必须在主线程（与 openCameraAsync 一致），同步确保相机真正关闭，
            // 否则第二次录制 openCameraAsync 会与未完成的 closeCamera 冲突导致失败（0KB）。
            try { closeCamera(); }
            catch (Exception e) { Debug.LogWarning("[PICOFor4UCapture] closeCamera: " + e.Message); }

            // Surface 编码器收尾（finish + 释放）放后台线程（AndroidJavaObject.Call 传参在后台需 Attach）。
            // 不阻塞主线程。finish() 内部 signalEndOfInputStream + drain 至 EOS。
            if (encoder != null)
            {
                var ft = new System.Threading.Thread(() =>
                {
#if UNITY_ANDROID
                    AndroidJNI.AttachCurrentThread();
#endif
                    try
                    {
                        Debug.Log("[PICOFor4UCapture] final drain, encoded=" + encodedCount + " camFrames=" + cameraFrameCount);
                        encoder.Call("finish");
                        string st = encoder.Call<string>("stats");
                        UnityEngine.Debug.Log("[PICOFor4UCapture] encoder stats: " + st);
                    }
                    catch (Exception e) { UnityEngine.Debug.LogWarning("[PICOFor4UCapture] finish: " + e.Message); }
                    try { encoder.Dispose(); } catch (Exception) { }
                    encoder = null;
#if UNITY_ANDROID
                    AndroidJNI.DetachCurrentThread();
#endif
                });
                ft.IsBackground = true;
                ft.Start();
            }
            // 释放 MediaCodec 输入 Surface 的 JNI 全局引用（closeCamera 之后相机已停止渲染，安全）。
            if (surfaceGlobalRef != IntPtr.Zero)
            {
                try { AndroidJNI.DeleteGlobalRef(surfaceGlobalRef); } catch (Exception) { }
                surfaceGlobalRef = IntPtr.Zero;
            }
        }

        void OnDestroy()
        {
            running = false;
            if (_instance == this) _instance = null;
        }
    }
}
