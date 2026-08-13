using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using System.Collections.Generic;
using UnityEngine.XR;
using ISInputDevice = UnityEngine.InputSystem.InputDevice;
using ISButtonControl = UnityEngine.InputSystem.Controls.ButtonControl;

namespace PicoMultiModalCapture
{
    /// World Space Canvas 通用 VR 手柄交互组件。
    /// 用 Input System 直接读取 PICO4 Ultra 右手柄 PoseControl（devicePose），
    /// 同时获得实时位置与旋转，发射射线 + ExecuteEvents 模拟 pointer/click。
    public class VRCanvasInput : MonoBehaviour
    {
        public GraphicRaycaster raycaster;
        private EventSystem _eventSystem;
        private PointerEventData _pointerData;
        private List<RaycastResult> _results = new();
        private GameObject _hovered;

        private Camera _cam;
        private bool _wasPressed;
        private int _frameCount;

        private ISInputDevice _isDevice;    // Input System 设备
        private UnityEngine.XR.OpenXR.Input.PoseControl _devicePose;  // devicePose 控件（OpenXR Pose）
        private UnityEngine.XR.OpenXR.Input.PoseControl _pointerPose; // pointer 控件（OpenXR Pose）
        private UnityEngine.InputSystem.Controls.AxisControl _triggerAxis; // trigger 模拟扳机（0-1）
        private ISButtonControl _triggerBtn; // triggerpressed 按钮控件

        private LineRenderer _laser;

        void Start()
        {
            _eventSystem = EventSystem.current ?? FindObjectOfType<EventSystem>();
            if (raycaster == null) raycaster = GetComponentInParent<GraphicRaycaster>();
            _pointerData = new PointerEventData(_eventSystem);

            // 缓存相机引用 — XR 激活后会禁用 Camera，Camera.main 变成 null
            _cam = Camera.main;
            if (_cam != null)
            {
                var cv = raycaster?.GetComponent<Canvas>();
                if (cv != null) cv.worldCamera = _cam;
            }

            Debug.Log("[VRCanvasInput] initialized, cam=" + (_cam?.name ?? "NULL") + " raycaster=" + (raycaster != null ? raycaster.name : "NULL"));
        }

        // 在 LateUpdate 读取位姿：XR 追踪数据在每帧的 LateUpdate 阶段才更新完成，
        // 此时 ReadValue() 能拿到最新手柄位置/旋转
        void LateUpdate()
        {
            _frameCount++;
            if (raycaster == null || _eventSystem == null || _cam == null) return;

            Vector3 pos;
            Quaternion rot;
            bool pressed;

            if (!TryGetPose(out pos, out rot, out pressed))
            {
                return;
            }

            Vector3 fwd = rot * Vector3.forward;

            var canvasT = raycaster.transform;
            Plane plane = new Plane(canvasT.forward, canvasT.position);
            if (!plane.Raycast(new Ray(pos, fwd), out float enter)) { ClearHover(); _wasPressed = pressed; return; }

            Vector3 worldHit = pos + fwd * enter;
            Vector2 screenPoint = _cam.WorldToScreenPoint(worldHit);

            _pointerData.position = screenPoint;
            _pointerData.pressPosition = screenPoint;
            _pointerData.delta = Vector2.zero;

            _results.Clear();
            raycaster.Raycast(_pointerData, _results);

            if (_results.Count > 0)
            {
                var target = _results[0].gameObject;
                if (target != _hovered)
                {
                    if (_hovered != null)
                        ExecuteEvents.Execute(_hovered, _pointerData, ExecuteEvents.pointerExitHandler);
                    ExecuteEvents.Execute(target, _pointerData, ExecuteEvents.pointerEnterHandler);
                    _hovered = target;
                }

                ExecuteEvents.Execute(target, _pointerData, ExecuteEvents.pointerMoveHandler);

                if (pressed && !_wasPressed)
                {
                    ExecuteEvents.Execute(target, _pointerData, ExecuteEvents.pointerDownHandler);
                    ExecuteEvents.Execute(target, _pointerData, ExecuteEvents.pointerClickHandler);
                    Debug.Log("[VRCanvasInput] click on: " + target.name);
                }
                else if (!pressed && _wasPressed)
                {
                    ExecuteEvents.Execute(target, _pointerData, ExecuteEvents.pointerUpHandler);
                }
            }
            else
            {
                ClearHover();
            }

            _wasPressed = pressed;
        }

        // 读取右手柄位姿：用 Input System 设备直接读取 devicePose/pointer PoseControl
        bool TryGetPose(out Vector3 pos, out Quaternion rot, out bool pressed)
        {
            pos = Vector3.zero;
            rot = Quaternion.identity;
            pressed = false;

            // 每次尝试获取/刷新 Input System 设备（右手控制器）
            if (_isDevice == null || !_isDevice.added)
            {
                _isDevice = FindRightHandDevice();
                if (_isDevice == null)
                {
                    _devicePose = null;
                    _pointerPose = null;
                    _triggerAxis = null;
                    _triggerBtn = null;
                    return false;
                }
                // 获取 devicePose 与 pointer 两个 PoseControl（比较哪个位置实时更新）
                _devicePose = GetControl<UnityEngine.XR.OpenXR.Input.PoseControl>(_isDevice, "devicePose");
                _pointerPose = GetControl<UnityEngine.XR.OpenXR.Input.PoseControl>(_isDevice, "pointer");
                // 扳机：triggerpressed 按钮 + trigger 模拟值（AxisControl）双通道
                _triggerBtn = GetControl<ISButtonControl>(_isDevice, "triggerpressed");
                _triggerAxis = GetControl<UnityEngine.InputSystem.Controls.AxisControl>(_isDevice, "trigger");
                if (_devicePose == null && _pointerPose == null)
                {
                    Debug.LogWarning("[VRCanvasInput] devicePose/pointer control not found on " + _isDevice.displayName + "; controls: " + DumpControls());
                    return false;
                }
            }

            // 读取位姿。优先用 pointer（通常更贴近手柄尖端位置）；若不可用回退 devicePose
            var poseDev = _devicePose != null ? _devicePose.ReadValue() : default;
            var posePtr = _pointerPose != null ? _pointerPose.ReadValue() : default;

            bool tracked;
            if (_pointerPose != null && (posePtr.position != Vector3.zero || posePtr.rotation != Quaternion.identity))
            {
                pos = posePtr.position;
                rot = posePtr.rotation;
                tracked = posePtr.isTracked;
            }
            else if (_devicePose != null)
            {
                pos = poseDev.position;
                rot = poseDev.rotation;
                tracked = poseDev.isTracked;
            }
            else
            {
                return false;
            }

            // 用 InputTracking 覆盖（与 OpenXR 追踪空间同步，本地坐标）
            var trackPos = UnityEngine.XR.InputTracking.GetLocalPosition(XRNode.RightHand);
            if (trackPos != Vector3.zero)
                pos = trackPos;
            var trackRot = UnityEngine.XR.InputTracking.GetLocalRotation(XRNode.RightHand);
            if (trackRot != Quaternion.identity)
                rot = trackRot;

            // 手柄位姿：在 Floor 追踪原点下，InputTracking.GetLocalPosition(RightHand)
            // 已返回手柄的世界空间位置（高度 0.9m 左右），无需再加头显偏移。
            // 旋转同理已为世界方向。直接用即可与 Canvas 世界坐标对齐。
            Vector3 worldPos = pos;
            Quaternion worldRot = rot;
            pos = worldPos;
            rot = worldRot;

            // 记录头显位置用于诊断
            Vector3 hmdPos = UnityEngine.XR.InputTracking.GetLocalPosition(XRNode.CenterEye);

            // 扳机：按钮控件（triggerpressed）或模拟值（trigger > 0.5）
            if (_triggerBtn == null)
                _triggerBtn = GetControl<ISButtonControl>(_isDevice, "triggerpressed");
            if (_triggerAxis == null)
                _triggerAxis = GetControl<UnityEngine.InputSystem.Controls.AxisControl>(_isDevice, "trigger");
            if (_triggerBtn != null)
                pressed = _triggerBtn.isPressed;
            else if (_triggerAxis != null)
                pressed = _triggerAxis.ReadValue() > 0.5f;

            // 诊断日志已用完（坐标系已调通），改为极低频，避免淹没其他日志
            // 仅在编辑器（开发构建）下每 300 帧打印一次
#if DEVELOPMENT_BUILD || UNITY_EDITOR
            if (_frameCount % 300 == 0)
                Debug.Log($"[VRCanvasInput] hand={pos.ToString("F3")} rot={rot.eulerAngles.ToString("F0")}");
#endif

            return true;
        }

        // 安全获取设备子控件（避免 KeyNotFoundException）
        T GetControl<T>(ISInputDevice dev, string name) where T : UnityEngine.InputSystem.InputControl
        {
            if (dev == null) return null;
            try { return dev[name] as T; }
            catch (System.Collections.Generic.KeyNotFoundException) { return null; }
        }

        // 列出设备上所有控件路径（用于诊断 devicePose 是否存在）
        string DumpControls()
        {
            System.Text.StringBuilder sb = new System.Text.StringBuilder();
            foreach (var ctrl in _isDevice.allControls)
                sb.Append(ctrl.path).Append("; ");
            return sb.ToString();
        }

        // 打印设备所有控件路径与类型（用于确认 trigger/pointer/devicePose 的类型）
        void DumpControlTypes(ISInputDevice dev)
        {
            Debug.Log("[VRCanvasInput] controller found: " + dev.displayName);
            System.Text.StringBuilder sb = new System.Text.StringBuilder();
            foreach (var ctrl in dev.allControls)
                sb.Append(ctrl.path).Append("[").Append(ctrl.GetType().Name).Append("] ");
            Debug.Log("[VRCanvasInput] controls: " + sb.ToString());
        }

        // 查找 Input System 右手控制器设备（排除 XRHandDevice 手部追踪设备）
        ISInputDevice FindRightHandDevice()
        {
            // 优先：RightHand usage + 设备是 XRController 类型或设备名含 controller
            foreach (var dev in UnityEngine.InputSystem.InputSystem.devices)
            {
                bool isRight = false;
                foreach (var usage in dev.usages)
                {
                    if (usage == UnityEngine.InputSystem.CommonUsages.RightHand) { isRight = true; break; }
                }
                bool isXrController = dev is UnityEngine.InputSystem.XR.XRController;
                bool nameIsController = dev.displayName != null &&
                    dev.displayName.ToLowerInvariant().Contains("controller");
                if (isRight && (isXrController || nameIsController))
                {
                    DumpControlTypes(dev);
                    return dev;
                }
            }
            // 回退：设备名含 controller（最宽松匹配）
            foreach (var dev in UnityEngine.InputSystem.InputSystem.devices)
            {
                if (dev.displayName != null &&
                    dev.displayName.ToLowerInvariant().Contains("controller"))
                {
                    Debug.Log("[VRCanvasInput] InputSystem controller (fallback): " + dev.displayName);
                    return dev;
                }
            }
            return null;
        }

        void DrawLaser(Vector3 from, Vector3 to)
        {
            if (_laser == null)
            {
                var go = new GameObject("VRLaser", typeof(LineRenderer));
                DontDestroyOnLoad(go);
                _laser = go.GetComponent<LineRenderer>();
                _laser.startWidth = 0.003f; _laser.endWidth = 0.003f;
                _laser.material = new Material(Shader.Find("Sprites/Default"));
                _laser.startColor = new Color(0.4f, 0.8f, 1f, 1f);
                _laser.endColor = new Color(0.4f, 0.8f, 1f, 0.3f);
                _laser.positionCount = 2;
            }
            _laser.SetPosition(0, from);
            _laser.SetPosition(1, to);
        }

        void ClearHover()
        {
            if (_hovered != null)
            {
                ExecuteEvents.Execute(_hovered, _pointerData, ExecuteEvents.pointerExitHandler);
                _hovered = null;
            }
        }
    }
}
