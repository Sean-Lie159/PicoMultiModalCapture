using System.Collections.Generic;
using System.Diagnostics;
using UnityEngine;

namespace PicoMultiModalCapture
{
    // 采集系统总控：统一管理录制启停、统一时间戳采样与导出。
    // 四类数据（头6DoF/身体24/双手26x2/视频）均在 Update 同一帧循环内按统一时钟采样，确保严格对齐。
    public class CaptureManager : MonoBehaviour
    {
        [Header("录制设置")]
        public int videoWidth = 2560; // 双目 SBS 拼接宽度（左右各 1280 并排），实际编码尺寸
        public int videoHeight = 720;
        public int videoFps = 30;
        public float captureRateHz = 30f;     // 姿态采样率（Hz）
        public bool enableHead = true;
        public bool enableHands = true;
        public bool enableBody = true;
        public bool enableVideo = true;
        public bool writeJson = true;
        public bool writeCsv = true;
        public string rootFolderName = "PicoMultiModalCapture";

        [Header("引用")]
        public Camera captureCamera;

        public System.Action<State> OnStateChanged;
        public System.Action<string> OnStatus;

        public enum State { Idle, Recording, Stopping }

        private State state = State.Idle;
        private List<FrameSample> frames = new List<FrameSample>();
        private Stopwatch sw;
        private double lastSampleT;
        private string sessionFolder;
        private PICOFor4UCapture for4UCapture;
        // 主线程回调队列：后台导出线程完成后，把"更新状态/提示"回拨到主线程执行（UI 线程安全）。
        private readonly System.Collections.Generic.Queue<System.Action> mainThreadActions =
            new System.Collections.Generic.Queue<System.Action>();
        private readonly object mainThreadLock = new object();
        // 缓存 Unity 版本（主线程读取），供后台导出线程使用——避免后台线程调用 Application.unityVersion（主线程 API）。
        public string unityVersionCache;
        // 双目 RGB 相机标定参数，录制停止时从 for4UCapture 拷贝，供 meta.json 导出。
        public CameraMeta cameraMeta = new CameraMeta();

        void Awake()
        {
            unityVersionCache = Application.unityVersion; // 主线程缓存，供后台导出线程用
            // Camera.main 只返回 tag=MainCamera 且 enabled 的相机。
            // XRCameraTracker 在 OpenXR 接管渲染后会禁用相机（cam.enabled=false），
            // 导致 Camera.main 返回 null。必须用 FindObjectOfType 找到被禁用的相机。
            if (captureCamera == null)
            {
                captureCamera = Camera.main;
                if (captureCamera == null)
                {
                    captureCamera = FindObjectOfType<Camera>();
                    if (captureCamera != null)
                        UnityEngine.Debug.Log("[CaptureManager] camera via FindObjectOfType: " + captureCamera.name);
                }
            }
        }

        public State CurrentState => state;

        public void StartRecording()
        {
            if (state != State.Idle) return;
            frames.Clear();
            sw = new Stopwatch();
            lastSampleT = -1;
            sessionFolder = System.IO.Path.Combine(
                Application.persistentDataPath, rootFolderName,
                System.DateTime.UtcNow.ToString("yyyyMMdd_HHmmss"));
            System.IO.Directory.CreateDirectory(sessionFolder);

            if (enableBody) BodyCapture.StartTracking();

            if (enableVideo)
            {
                // 视频用 PICO Enterprise for4U 相机 API（CameraRenderingPlugin.so）获取真实世界第一人称 RGB 画面。
                // 现在以 3D 双目 SBS 模式采集（左右并排 2560x720），PICOFor4UCapture 内部处理。
                // 相机初始化在后台线程异步执行，不阻塞主线程，保证音量键仍可响应。
                string videoPath = System.IO.Path.Combine(sessionFolder, "video.mp4");
                var camCapture = gameObject.AddComponent<PICOFor4UCapture>();
                camCapture.StartCapture(videoPath, videoWidth, videoHeight);
                for4UCapture = camCapture;
                UnityEngine.Debug.Log("[CaptureManager] PICO for4U 3D SBS camera capture starting (async, Surface direct 60fps)");
            }
            sw.Start();
            state = State.Recording;
            OnStateChanged?.Invoke(state);
            OnStatus?.Invoke("录制中…");
        }

        public void StopRecording()
        {
            if (state != State.Recording) return;
            state = State.Stopping;
            sw?.Stop();
            // 停录时清除身体丢失提示（避免残留）
            if (bodyTrackingLost)
            {
                bodyTrackingLost = false;
                OnBodyTrackingLostChanged?.Invoke();
            }
            // 立即通知 UI 进入"保存中"，避免长时间导出期间无反馈、主线程卡死导致按键无响应。
            OnStatus?.Invoke("正在保存…");
            OnStateChanged?.Invoke(state);
            if (enableVideo && for4UCapture != null)
            {
                // 先拷贝相机标定参数（之后组件被销毁），供 meta.json 导出
                cameraMeta = for4UCapture.cameraMeta;
                // 计算实际视频帧率（Surface 直通后通常 ~60fps，非配置值 videoFps=30）：
                // 用已编码帧数 / 录制时长。避免除零。
                double dur = sw != null ? sw.Elapsed.TotalSeconds : 0;
                if (dur > 0.5 && for4UCapture.ActualEncodedFrames > 0)
                {
                    cameraMeta.actualVideoFps = (int)System.Math.Round(for4UCapture.ActualEncodedFrames / dur);
                    UnityEngine.Debug.Log("[CaptureManager] actual video fps=" + cameraMeta.actualVideoFps + " frames=" + for4UCapture.ActualEncodedFrames + " dur=" + dur.ToString("F2") + "s");
                }
                for4UCapture.StopCapture();
                Destroy(for4UCapture);
                for4UCapture = null;
                UnityEngine.Debug.Log("[CaptureManager] PICO for4U camera capture stopped, camMeta.available=" + cameraMeta.available);
            }
            if (enableBody) BodyCapture.StopTracking();

            // 异步导出：长时间录制（几分钟）时 data.json/csv 可达数 MB，同步导出会阻塞主线程数秒，
            // 期间 UI 无反馈、state 卡在 Stopping 导致 "+" 键被拒。改为后台线程导出，
            // 完成后回主线程更新状态。frames 录制已停止不再变更，后台线程读取安全。
            var folder = sessionFolder;
            var cfgSnapshot = this;
            var framesSnapshot = frames;
            var worker = new System.Threading.Thread(() =>
            {
#if UNITY_ANDROID
                AndroidJNI.AttachCurrentThread();
#endif
                string err = null;
                try
                {
                    DataExporter.Export(folder, framesSnapshot, cfgSnapshot);
                }
                catch (System.Exception e)
                {
                    err = e.Message;
                    UnityEngine.Debug.LogError("[CaptureManager] export failed: " + e);
                }
                // 回主线程更新状态（UI 操作必须在主线程）
                var result = err;
                lock (mainThreadLock)
                {
                    mainThreadActions.Enqueue(() =>
                    {
                        state = State.Idle;
                        OnStateChanged?.Invoke(state);
                        if (result == null) OnStatus?.Invoke("已保存: " + folder);
                        else OnStatus?.Invoke("保存失败: " + result);
                    });
                }
#if UNITY_ANDROID
                AndroidJNI.DetachCurrentThread();
#endif
            });
            worker.IsBackground = true;
            worker.Start();
        }

        void Update()
        {
            // 消费主线程回调队列（后台导出完成后的状态更新）
            lock (mainThreadLock)
            {
                while (mainThreadActions.Count > 0) mainThreadActions.Dequeue()?.Invoke();
            }
            if (state != State.Recording) return;
            double t = sw.Elapsed.TotalSeconds;
            if (t - lastSampleT < (1.0 / captureRateHz) - 1e-4) return;
            lastSampleT = t;

            var frame = new FrameSample();
            frame.t = t;
            frame.wallClock = System.DateTime.UtcNow.ToString("o");

            if (enableHead) frame.head = HeadPoseCapture.Capture(captureCamera);

            if (enableBody)
            {
                var (ok, conf, joints) = BodyCapture.Capture();
                frame.hasBody = ok;
                frame.bodyConfidence = conf;
                frame.bodyJoints = joints;
            }

            if (enableHands)
            {
                frame.leftHand = HandCapture.CaptureLeft();
                frame.rightHand = HandCapture.CaptureRight();
            }

            frames.Add(frame);

            // 身体追踪丢失检测：录制中且身体置信度为 0（未佩戴 Motion Tracker/追踪失效）时，
            // 置 bodyTrackingLost 并触发事件，供 RecorderUI 显示一行轻量提示。
            // 数据本身已在上述 BodyCapture.Capture() 获取，此处仅复用，无额外开销。
            if (enableBody)
            {
                bool lost = frame.hasBody == false || frame.bodyConfidence <= 0f;
                if (lost != bodyTrackingLost)
                {
                    bodyTrackingLost = lost;
                    OnBodyTrackingLostChanged?.Invoke();
                }
            }
            // 视频由 Android MediaProjection 原生捕获，Unity 端无需逐帧处理。
        }

        // ===== 身体追踪丢失提示状态 =====
        // 身体数据为 0（未佩戴 Motion Tracker 或追踪失效）时置 true，供 UI 显示一行提示。
        // 注意：无追踪器时 isTracking 仍可能为 true，故用置信度 conf<=0 判定（与 AGENTS.md 记录一致）。
        public bool bodyTrackingLost { get; private set; }
        public event System.Action OnBodyTrackingLostChanged;
    }
}
