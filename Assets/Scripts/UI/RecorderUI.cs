using UnityEngine;
using UnityEngine.UI;

namespace PicoMultiModalCapture
{
    // 录制控制 UI：运行时动态创建 Canvas + 启停按钮 + 状态文本（无需预先制作 Prefab）。
    // 按钮交互依赖 EventSystem（已在 CaptureBootstrap 中创建）。
    public class RecorderUI : MonoBehaviour
    {
        public CaptureManager manager;
        private Text statusText;
        private Button startBtn, stopBtn;
        private RectTransform _canvasRect;
        private GameObject _canvasGO;
        private Transform _camTransform;
        // 身体丢失提示（录制中独立常驻的小字，不影响录制的 for4U 视频画面）
        private GameObject _bodyLostGO;
        private Text _bodyLostText;

        void Start()
        {
            Debug.Log("[RecorderUI] Start()");
            if (manager == null) manager = FindObjectOfType<CaptureManager>();
            _camTransform = Camera.main?.transform;
            BuildUI();
            if (manager != null)
            {
                manager.OnStateChanged += s => Refresh();
                manager.OnStatus += msg => { if (statusText != null) statusText.text = msg; };
                manager.OnBodyTrackingLostChanged += OnBodyLostChanged;
            }
            Refresh();
            Debug.Log("[RecorderUI] UI built, font=" + (statusText?.font?.name ?? "null"));
        }

        void LateUpdate()
        {
            // 让 UI 面板始终跟随头部，保持在视野前方
            if (_canvasRect == null || _camTransform == null) return;
            _canvasRect.position = _camTransform.position + _camTransform.forward * 2.5f
                                   + _camTransform.up * 0.3f;
            _canvasRect.rotation = Quaternion.LookRotation(
                _camTransform.forward, Vector3.up);
        }

        void BuildUI()
        {
            var canvas = new GameObject("RecorderCanvas", typeof(Canvas));
            _canvasGO = canvas;
            var cv = canvas.GetComponent<Canvas>();
            cv.renderMode = RenderMode.WorldSpace;
            // Canvas 已自动携带 RectTransform，不能再次 AddComponent
            _canvasRect = canvas.GetComponent<RectTransform>();
            _canvasRect.sizeDelta = new Vector2(800, 450);
            // 初始位置（后续由 LateUpdate 跟随相机动态更新）
            _canvasRect.position = (_camTransform != null
                ? _camTransform.position + _camTransform.forward * 2.5f + _camTransform.up * 0.3f
                : new Vector3(0f, 0.3f, 2.5f));
            _canvasRect.localScale = new Vector3(0.002f, 0.002f, 0.002f);
            canvas.AddComponent<GraphicRaycaster>();

            var panel = new GameObject("Panel", typeof(RectTransform), typeof(Image));
            panel.transform.SetParent(canvas.transform, false);
            var prt = panel.GetComponent<RectTransform>();
            prt.anchorMin = new Vector2(0, 0); prt.anchorMax = new Vector2(1, 0);
            prt.pivot = new Vector2(0.5f, 0); prt.sizeDelta = new Vector2(0, 140);
            panel.GetComponent<Image>().color = new Color(0, 0, 0, 0.55f);

            startBtn = MakeButton(panel.transform, "开始录制", new Vector2(0.27f, 0.5f));
            stopBtn = MakeButton(panel.transform, "停止并导出", new Vector2(0.73f, 0.5f));
            if (manager != null)
            {
                startBtn.onClick.AddListener(manager.StartRecording);
                stopBtn.onClick.AddListener(manager.StopRecording);
            }

            var st = new GameObject("Status", typeof(RectTransform), typeof(Text));
            st.transform.SetParent(panel.transform, false);
            statusText = st.GetComponent<Text>();
            statusText.text = "就绪";
            statusText.color = Color.white;
            statusText.fontSize = 28;
            statusText.font = ResolveFont();
            statusText.alignment = TextAnchor.MiddleCenter;
            var srt = st.GetComponent<RectTransform>();
            srt.anchorMin = new Vector2(0.1f, 0.58f); srt.anchorMax = new Vector2(0.9f, 0.96f);
            srt.offsetMin = Vector2.zero; srt.offsetMax = Vector2.zero;

            // 为 World Space Canvas 创建 VR 手柄交互控制器
            var vrInput = canvas.gameObject.AddComponent<VRCanvasInput>();
            vrInput.raycaster = canvas.GetComponent<GraphicRaycaster>();

            BuildBodyLostHint();
            Debug.Log("[RecorderUI] VRCanvasInput attached to canvas");
        }

        // 录制中"身体数据丢失"提示：一个独立、常驻视野底部的小字（半透明、不显眼）。
        // 视频来自 PICO for4U 相机（不含 Unity UI），此提示不会进入录制的 video.mp4。
        void BuildBodyLostHint()
        {
            var canvas = new GameObject("BodyLostCanvas", typeof(Canvas));
            _bodyLostGO = canvas;
            var cv = canvas.GetComponent<Canvas>();
            cv.renderMode = RenderMode.WorldSpace;
            var rect = canvas.GetComponent<RectTransform>();
            rect.sizeDelta = new Vector2(1200, 120);
            rect.localScale = new Vector3(0.0015f, 0.0015f, 0.0015f);
            // 位于视野底部偏下（2.5m 前，0.8m 下），不遮挡中央视野
            rect.position = (_camTransform != null
                ? _camTransform.position + _camTransform.forward * 2.5f - _camTransform.up * 0.8f
                : new Vector3(0f, -0.8f, 2.5f));
            rect.rotation = Quaternion.LookRotation(
                (_camTransform != null ? _camTransform.forward : Vector3.forward), Vector3.up);

            var st = new GameObject("Hint", typeof(RectTransform), typeof(Text));
            st.transform.SetParent(canvas.transform, false);
            _bodyLostText = st.GetComponent<Text>();
            _bodyLostText.text = "⚠ 身体数据丢失（未佩戴追踪器）";
            _bodyLostText.color = new Color(1f, 0.8f, 0.2f, 0.9f);
            _bodyLostText.fontSize = 40;
            _bodyLostText.font = ResolveFont();
            _bodyLostText.alignment = TextAnchor.MiddleCenter;
            _bodyLostText.raycastTarget = false;
            var srt = st.GetComponent<RectTransform>();
            srt.anchorMin = Vector2.zero; srt.anchorMax = Vector2.one;
            srt.offsetMin = Vector2.zero; srt.offsetMax = Vector2.zero;

            _bodyLostGO.SetActive(false); // 默认隐藏，仅在身体丢失时显示
        }

        void OnBodyLostChanged()
        {
            if (_bodyLostGO == null) return;
            bool show = manager != null && manager.bodyTrackingLost;
            _bodyLostGO.SetActive(show);
        }

        static Font ResolveFont()
        {
            // PICO Android 上 Arial 不含 CJK 字形，导致中文文本不可见。
            // 按优先级尝试多个已知支持中文的系统字体名称。
            string[] cjkFonts = { "NotoSansCJKsc-Regular", "NotoSansSC-Regular",
                                   "DroidSansFallback", "NotoSansCJK-Regular",
                                   "Noto Sans CJK SC", "sans-serif", "Arial" };
            foreach (var name in cjkFonts)
            {
                var f = Font.CreateDynamicFontFromOSFont(name, 24);
                if (f != null)
                {
                    Debug.Log("[RecorderUI] ResolveFont OK: " + name);
                    return f;
                }
            }
            // 最终回退到 Unity 内置字体
            Debug.Log("[RecorderUI] ResolveFont fallback to builtin Arial");
            return Resources.GetBuiltinResource<Font>("Arial.ttf");
        }

        void Refresh()
        {
            if (manager == null) return;
            if (startBtn) startBtn.interactable = manager.CurrentState == CaptureManager.State.Idle;
            if (stopBtn) stopBtn.interactable = manager.CurrentState == CaptureManager.State.Recording;

            // 录制时隐藏 UI，保证录制的视频画面是干净的透视现实画面（不含 UI 框）。
            // Stopping（保存中）也显示 UI，让用户能看到"正在保存…"反馈。
            if (_canvasGO != null)
            {
                bool showUI = manager.CurrentState == CaptureManager.State.Idle
                           || manager.CurrentState == CaptureManager.State.Stopping;
                _canvasGO.SetActive(showUI);
            }
        }

        static Button MakeButton(Transform parent, string label, Vector2 anchor)
        {
            var go = new GameObject(label, typeof(RectTransform), typeof(RawImage), typeof(Button));
            go.transform.SetParent(parent, false);
            var r = go.GetComponent<RectTransform>();
            r.anchorMin = anchor; r.anchorMax = anchor;
            r.sizeDelta = new Vector2(220, 64); r.anchoredPosition = Vector2.zero;

            // 使用 RawImage 直接渲染纹理（避免 IL2CPP 下 Sprite.Create 失败）
            var tex = new Texture2D(1, 1, TextureFormat.RGBA32, false);
            tex.SetPixel(0, 0, new Color(0.22f, 0.55f, 0.88f, 0.85f));
            tex.Apply();
            var rawImg = go.GetComponent<RawImage>();
            rawImg.texture = tex;
            rawImg.color = Color.white;

            var t = new GameObject("Txt", typeof(RectTransform), typeof(Text));
            t.transform.SetParent(go.transform, false);
            var tx = t.GetComponent<Text>();
            tx.text = label; tx.color = Color.white;
            tx.fontSize = 28;
            tx.alignment = TextAnchor.MiddleCenter;
            tx.font = ResolveFont();
            var trt = t.GetComponent<RectTransform>();
            trt.anchorMin = Vector2.zero; trt.anchorMax = Vector2.one;
            trt.offsetMin = Vector2.zero; trt.offsetMax = Vector2.zero;
            return go.GetComponent<Button>();
        }
    }
}
