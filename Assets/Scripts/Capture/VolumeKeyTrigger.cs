using UnityEngine;

namespace PicoMultiModalCapture
{
    /// 用 PICO 头显物理音量键触发录制：
    ///   "+" 音量加  = 开始录制
    ///   "-" 音量减  = 停止并导出
    /// 采集员无需手柄交互，戴着头显按头显侧键即可控制。
    ///
    /// 音量键由自定义 Android Activity（VolumeKeyActivity）拦截，
    /// 通过 UnitySendMessage("VolumeKeyTrigger", "OnVolumeKeyEvent", "up|down") 回调本组件。
    public class VolumeKeyTrigger : MonoBehaviour
    {
        public CaptureManager manager;

        void Start()
        {
            if (manager == null) manager = FindObjectOfType<CaptureManager>();
            Debug.Log("[VolumeKeyTrigger] initialized, manager=" + (manager != null ? "OK" : "NULL"));
        }

        // 由 Android 层（UnitySendMessage）调用
        public void OnVolumeKeyEvent(string direction)
        {
            Debug.Log("[VolumeKeyTrigger] volume key event: " + direction + ", state=" + (manager != null ? manager.CurrentState.ToString() : "no-manager"));
            if (manager == null) return;

            if (direction == "up")
            {
                if (manager.CurrentState == CaptureManager.State.Idle)
                    manager.StartRecording();
            }
            else if (direction == "down")
            {
                if (manager.CurrentState == CaptureManager.State.Recording)
                    manager.StopRecording();
            }
        }
    }
}
