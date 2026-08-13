package com.DefaultCompany.PicoMultiModalCapture;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.util.Log;
import android.view.Surface;

import java.io.File;
import java.nio.ByteBuffer;

/**
 * Android 14+ 要求 MediaProjection 必须在类型为 FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
 * 的前台服务中创建和使用。本服务承载 MediaProjection 屏幕捕获录制。
 *
 * 启动方式（从 VolumeKeyActivity 授权后）：
 *   startService(new Intent(this, MediaProjectionService.class)
 *       .putExtra("resultCode", resultCode)
 *       .putExtra("resultData", data))
 */
public class MediaProjectionService extends Service {
    private static final String TAG = "MediaProjectionSvc";
    private static final String CHANNEL_ID = "media_projection";

    private MediaProjectionManager mpManager;
    private MediaProjection mediaProjection;
    private VirtualDisplay virtualDisplay;
    private MediaCodec encoder;
    private MediaMuxer muxer;
    private HandlerThread handlerThread;
    private Handler handler;
    private int trackIndex = -1;
    private boolean muxerStarted;
    private MediaCodec.BufferInfo bufferInfo = new MediaCodec.BufferInfo();
    private volatile boolean recording;

    @Override
    public void onCreate() {
        super.onCreate();
        mpManager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        createChannel();
        startForegroundCompat();
    }

    private void startForegroundCompat() {
        Notification.Builder builder;
        if (android.os.Build.VERSION.SDK_INT >= 26) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }
        builder.setContentTitle("PicoMultiModalCapture")
                .setContentText("屏幕录制中")
                .setSmallIcon(android.R.drawable.ic_media_play);
        Notification notification = builder.build();
        if (android.os.Build.VERSION.SDK_INT >= 29) {
            startForeground(1, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
        } else {
            startForeground(1, notification);
        }
    }

    private void createChannel() {
        if (android.os.Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, "Screen Capture", NotificationManager.IMPORTANCE_LOW);
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) nm.createNotificationChannel(channel);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null) {
            int resultCode = intent.getIntExtra("resultCode", 0);
            Intent resultData = intent.getParcelableExtra("resultData");
            String filePath = intent.getStringExtra("filePath");
            if (resultData != null && filePath != null) {
                startRecording(resultCode, resultData, filePath);
            }
        }
        return START_STICKY;
    }

    private void startRecording(int resultCode, Intent resultData, String filePath) {
        if (recording) return;
        try {
            if (handlerThread == null) {
                handlerThread = new HandlerThread("ScreenCapSvc");
                handlerThread.start();
                handler = new Handler(handlerThread.getLooper());
            }

            int width = 1280, height = 720;
            int density = getResources().getDisplayMetrics().densityDpi;

            MediaFormat format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, width, height);
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT,
                    MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
            format.setInteger(MediaFormat.KEY_BIT_RATE, 10_000_000);
            format.setInteger(MediaFormat.KEY_FRAME_RATE, 30);
            format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);

            encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
            encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            Surface encoderSurface = encoder.createInputSurface();
            encoder.start();

            File out = new File(filePath);
            if (out.exists()) out.delete();
            muxer = new MediaMuxer(filePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            muxerStarted = false;
            trackIndex = -1;

            mediaProjection = mpManager.getMediaProjection(resultCode, resultData);

            // Android 14+ 要求：createVirtualDisplay 之前必须先注册 callback，
            // 否则抛 IllegalStateException "Must register a callback before starting capture"
            mediaProjection.registerCallback(new MediaProjection.Callback() {
                @Override
                public void onStop() {
                    Log.w(TAG, "MediaProjection stopped by system");
                    stopRecording();
                }
            }, handler);

            virtualDisplay = mediaProjection.createVirtualDisplay(
                    "ScreenCapSvc", width, height, density,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    encoderSurface, null, handler);

            recording = true;
            startDrainLoop();
            Log.i(TAG, "startRecording OK: " + filePath);
            UnityPlayerHelper.sendToUnity("ScreenCaptureMgr", "OnRecordingStarted", filePath);
        } catch (Exception e) {
            Log.e(TAG, "startRecording failed: " + e.getMessage(), e);
            UnityPlayerHelper.sendToUnity("ScreenCaptureMgr", "OnRecordingError", e.getMessage());
        }
    }

    private void startDrainLoop() {
        final HandlerThread drainThread = new HandlerThread("ScreenCapDrain");
        drainThread.start();
        Handler drainHandler = new Handler(drainThread.getLooper());
        drainHandler.post(new Runnable() {
            @Override public void run() {
                if (!recording) { drainThread.quitSafely(); return; }
                try {
                    int idx;
                    while ((idx = encoder.dequeueOutputBuffer(bufferInfo, 0)) >= 0) {
                        if (idx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                            if (trackIndex >= 0) { try { muxer.stop(); } catch (Exception ignore) {} }
                            trackIndex = muxer.addTrack(encoder.getOutputFormat());
                            muxer.start();
                            muxerStarted = true;
                        } else if (idx >= 0) {
                            ByteBuffer outBuf = encoder.getOutputBuffer(idx);
                            if (outBuf != null) {
                                if ((bufferInfo.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) {
                                    bufferInfo.size = 0;
                                }
                                if (bufferInfo.size > 0 && muxerStarted) {
                                    outBuf.position(bufferInfo.offset);
                                    outBuf.limit(bufferInfo.offset + bufferInfo.size);
                                    muxer.writeSampleData(trackIndex, outBuf, bufferInfo);
                                }
                            }
                            encoder.releaseOutputBuffer(idx, false);
                        }
                    }
                } catch (Exception e) {
                    Log.e(TAG, "drain error: " + e.getMessage());
                }
                drainHandler.post(this);
            }
        });
    }

    public void stopRecording() {
        recording = false;
        try {
            if (virtualDisplay != null) { virtualDisplay.release(); virtualDisplay = null; }
            if (encoder != null) {
                try { encoder.signalEndOfInputStream(); } catch (Exception ignore) {}
                try { encoder.stop(); } catch (Exception ignore) {}
                encoder.release();
                encoder = null;
            }
            if (muxer != null) {
                try { if (muxerStarted) muxer.stop(); } catch (Exception ignore) {}
                muxer.release();
                muxer = null;
                muxerStarted = false;
            }
            if (mediaProjection != null) {
                try { mediaProjection.stop(); } catch (Exception ignore) {}
                mediaProjection = null;
            }
            if (handlerThread != null) {
                handlerThread.quitSafely();
                handlerThread = null;
                handler = null;
            }
            Log.i(TAG, "stopRecording OK");
            UnityPlayerHelper.sendToUnity("ScreenCaptureMgr", "OnRecordingStopped", "done");
        } catch (Exception e) {
            Log.e(TAG, "stopRecording failed: " + e.getMessage());
        }
    }

    @Override
    public void onDestroy() {
        stopRecording();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
