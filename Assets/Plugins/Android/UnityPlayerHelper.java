package com.DefaultCompany.PicoMultiModalCapture;

import com.unity3d.player.UnityPlayer;

/**
 * 简化 UnitySendMessage 调用。
 */
public final class UnityPlayerHelper {
    private UnityPlayerHelper() {}

    // 向 Unity 指定 GameObject 的指定方法发送消息
    public static void sendToUnity(String gameObject, String method, String value) {
        try {
            UnityPlayer.UnitySendMessage(gameObject, method, value);
        } catch (Throwable t) {
            android.util.Log.w("UnityPlayerHelper", "sendToUnity failed: " + t.getMessage());
        }
    }
}
