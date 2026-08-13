package com.DefaultCompany.PicoMultiModalCapture;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.KeyEvent;
import com.unity3d.player.UnityPlayer;
import com.unity3d.player.UnityPlayerActivity;

/**
 * 继承 UnityPlayerActivity：
 * 1) 拦截音量键触发录制/停止（"+"开始，"-"停止）
 * 2) 管理 MediaProjection 屏幕捕获授权，并把授权结果交给 MediaProjectionService（前台服务）录制。
 *
 * 供 Unity C# 调用的静态方法（通过 AndroidJavaClass）：
 *   RequestScreenPermission(): 请求屏幕捕获授权（弹窗）
 *   StartScreenCapture(String path): 开始屏幕捕获（须先授权）
 *   StopScreenCapture(): 停止捕获
 *   HasScreenPermission(): 是否已授权
 */
public class VolumeKeyActivity extends UnityPlayerActivity {

    private static final String TAG = "VolumeKeyActivity";
    private static final int KEYCODE_VOLUME_UP = 24;
    private static final int KEYCODE_VOLUME_DOWN = 25;
    private static final int REQUEST_MEDIA_PROJECTION = 10001;
    private static final int REQUEST_POST_NOTIFICATIONS = 10002;

    private static int lastResultCode = -1;
    private static Intent lastResultData;

    private static VolumeKeyActivity instance;
    private String pendingVideoPath;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        instance = this;
        requestPermissionsIfNeeded();
    }

    private void requestPermissionsIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQUEST_POST_NOTIFICATIONS);
            }
        }
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KEYCODE_VOLUME_UP) {
            UnityPlayer.UnitySendMessage("VolumeKeyTrigger", "OnVolumeKeyEvent", "up");
            return true;
        } else if (keyCode == KEYCODE_VOLUME_DOWN) {
            UnityPlayer.UnitySendMessage("VolumeKeyTrigger", "OnVolumeKeyEvent", "down");
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_MEDIA_PROJECTION) {
            if (resultCode == Activity.RESULT_OK && data != null) {
                lastResultCode = resultCode;
                lastResultData = data;
                Log.i(TAG, "MediaProjection permission granted");
                UnityPlayer.UnitySendMessage("ScreenCaptureMgr", "OnPermissionResult", "granted");
            } else {
                lastResultCode = -1;
                lastResultData = null;
                Log.w(TAG, "MediaProjection permission denied");
                UnityPlayer.UnitySendMessage("ScreenCaptureMgr", "OnPermissionResult", "denied");
            }
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        instance = null;
    }

    // ===== 供 Unity C# 调用的静态方法 =====

    // 请求屏幕捕获授权
    public static void RequestScreenPermission() {
        VolumeKeyActivity act = getInstance();
        if (act == null) return;
        act.runOnUiThread(new Runnable() {
            @Override public void run() {
                try {
                    Intent intent = ((android.media.projection.MediaProjectionManager)
                            act.getSystemService("media_projection")).createScreenCaptureIntent();
                    act.startActivityForResult(intent, REQUEST_MEDIA_PROJECTION);
                } catch (Exception e) {
                    Log.e(TAG, "RequestScreenPermission failed: " + e.getMessage());
                }
            }
        });
    }

    // 开始屏幕捕获到指定路径（须已授权）
    public static void StartScreenCapture(String filePath) {
        VolumeKeyActivity act = getInstance();
        if (act == null || lastResultData == null) {
            Log.w(TAG, "StartScreenCapture: no permission");
            UnityPlayer.UnitySendMessage("ScreenCaptureMgr", "OnRecordingError", "no permission");
            return;
        }
        Intent intent = new Intent(act, MediaProjectionService.class);
        intent.putExtra("resultCode", lastResultCode);
        intent.putExtra("resultData", lastResultData);
        intent.putExtra("filePath", filePath);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            act.startForegroundService(intent);
        } else {
            act.startService(intent);
        }
        Log.i(TAG, "StartScreenCapture -> service: " + filePath);
    }

    // 停止屏幕捕获
    public static void StopScreenCapture() {
        VolumeKeyActivity act = getInstance();
        if (act == null) return;
        Intent intent = new Intent(act, MediaProjectionService.class);
        act.stopService(intent);
        Log.i(TAG, "StopScreenCapture");
    }

    // 是否已获得屏幕捕获授权
    public static boolean HasScreenPermission() {
        return lastResultData != null;
    }

    private static VolumeKeyActivity getInstance() {
        return instance;
    }
}
