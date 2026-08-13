using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.XR;
using UnityEngine.XR.Management;
#if ENABLE_PICO_XR_SDK
using Unity.XR.OpenXR.Features.PICOSupport;
#endif

namespace PicoMultiModalCapture
{
    // 运行时引导：确保 CaptureManager 与 RecorderUI 存在，并创建 UI 必需的 EventSystem。
    // 这样无需预先制作 Scene/Prefab，工程打开即可运行。
    public static class CaptureBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        static void Init()
        {
            if (Object.FindObjectOfType<EventSystem>() == null)
            {
                new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));
            }

            if (Object.FindObjectOfType<CaptureManager>() == null)
            {
                new GameObject("CaptureManager").AddComponent<CaptureManager>();
            }

            var ui = Object.FindObjectOfType<RecorderUI>();
            if (ui == null)
            {
                var go = new GameObject("RecorderUI");
                ui = go.AddComponent<RecorderUI>();
                ui.manager = Object.FindObjectOfType<CaptureManager>();
            }

            // 音量键触发录制（头显物理按键，无需手柄交互）
            if (Object.FindObjectOfType<VolumeKeyTrigger>() == null)
            {
                var vg = new GameObject("VolumeKeyTrigger");
                var vt = vg.AddComponent<VolumeKeyTrigger>();
                vt.manager = Object.FindObjectOfType<CaptureManager>();
            }
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void SetupXR()
        {
            // 确保 XR 初始化
            var manager = XRGeneralSettings.Instance?.Manager;
            if (manager != null && !manager.isInitializationComplete)
            {
                manager.InitializeLoaderSync();
                if (manager.activeLoader != null)
                    manager.StartSubsystems();
            }

            // 为相机添加头部追踪保底
            var cam = Camera.main;
            if (cam != null)
            {
                // 强制设到原点，XR 会接管相机位置
                cam.transform.position = Vector3.zero;
                cam.transform.rotation = Quaternion.identity;
                var tracker = cam.gameObject.AddComponent<XRCameraTracker>();
                tracker.cam = cam;
            }
        }
    }

    // XR 头部追踪组件：兼容新旧 XR API
    public class XRCameraTracker : MonoBehaviour
    {
        public Camera cam;
        private bool xrActive;

        void Start()
        {
            if (cam != null)
            {
                cam.stereoTargetEye = StereoTargetEyeMask.Both;
                // Passthrough 要求 SolidColor + Alpha=0，透视画面作为 Underlay 合成
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0, 0, 0, 0);
                // 初始保持相机启用，避免 XR 未就绪时黑屏。
                // 当 XR 确认接管渲染后，由 OnXRPresent 关闭相机。
                cam.enabled = true;
            }

            // 启用视频透视（Passthrough）
            EnablePassthrough();

            // 检查 XR 初始化状态
            var loader = XRGeneralSettings.Instance?.Manager?.activeLoader;
            xrActive = loader != null;
            Debug.Log($"[XRCameraTracker] Start - XR active: {xrActive}, loader: {loader?.GetType().Name ?? "null"}");
        }

        // 启用视频透视。仅在 ENABLE_PICO_XR_SDK 定义下编译（与 BodyCapture 一致）。
        // 前提：Project Settings → XR Plug-in Management → OpenXR → Features 已勾选 "OpenXR Passthrough"。
        void EnablePassthrough()
        {
#if ENABLE_PICO_XR_SDK
            try
            {
                if (PassthroughFeature.IsPassthroughSupported())
                {
                    PassthroughFeature.EnableVideoSeeThrough = true;
                    Debug.Log("[XRCameraTracker] Passthrough enabled via PassthroughFeature");
                }
                else
                {
                    Debug.LogWarning("[XRCameraTracker] Passthrough not supported on this device");
                }
            }
            catch (System.Exception e)
            {
                Debug.LogWarning("[XRCameraTracker] PassthroughFeature not available: " + e.Message);
            }
#else
            Debug.LogWarning("[XRCameraTracker] ENABLE_PICO_XR_SDK not defined, passthrough skipped");
#endif
        }

        void OnEnable()
        {
            if (cam != null) cam.stereoTargetEye = StereoTargetEyeMask.Both;
            // 订阅 XR 显示事件
            Application.onBeforeRender += OnBeforeRender;
        }

        void OnDisable()
        {
            Application.onBeforeRender -= OnBeforeRender;
        }

        void OnBeforeRender()
        {
            // XR 开始提交渲染帧时，确认启动成功，此时可安全禁用独立相机渲染
            if (!xrActive && XRGeneralSettings.Instance?.Manager?.activeLoader != null)
            {
                xrActive = true;
                if (cam != null)
                {
                    cam.enabled = false;
                    Debug.Log("[XRCameraTracker] XR rendering confirmed, camera disabled");
                }
            }
        }

        void Update()
        {
            if (cam == null) return;

            // 如果 XR 仍未激活，每帧尝试初始化（带超时保护）
            if (!xrActive)
            {
                var manager = XRGeneralSettings.Instance?.Manager;
                if (manager != null && !manager.isInitializationComplete)
                {
                    manager.InitializeLoaderSync();
                    if (manager.activeLoader != null)
                        manager.StartSubsystems();
                }
                if (manager?.activeLoader != null)
                {
                    xrActive = true;
                    Debug.Log("[XRCameraTracker] XR loader activated in Update");
                }
            }
        }

    }
}
