package com.picocapture;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.util.Log;
import android.view.Surface;

import java.io.File;
import java.nio.ByteBuffer;

/**
 * Surface 直通硬件编码器（方案 A，已验证 60fps）。
 * 关键：PICO for4U 的 startPreview(androidSurface,...) 把双目 SBS 画面直接渲染到
 * MediaCodec 的输入 Surface，完全绕开 CPU 的 rgbaToNv12 逐像素转换，帧率由 CPU 编码的
 * ~22fps 提升到相机原始 ~60fps。
 *
 * 用法（配合 PICOFor4UCapture 的 Surface 直通分支）：
 *   getInputSurface() -> 返回输入 Surface（把 JNI 句柄转成 IntPtr 传给 Unity startPreview）
 *   encodeAndDrain()  -> 周期性排空编码输出写 MP4（相机异步渲染到 Surface，无需主动喂帧）
 *   finish()          -> 停止并封装
 */
public class SurfaceEncoder {
    private static final String TAG = "SurfaceEncoder";
    private MediaCodec encoder;
    private MediaMuxer muxer;
    private Surface inputSurface;
    private int trackIndex = -1;
    private boolean muxerStarted = false;
    private int width, height, fps;
    private long frameCount = 0;
    private long lastTs = 0;
    private long firstTs = -1;

    public SurfaceEncoder(String filePath, int w, int h, int fps) {
        this.width = w; this.height = h; this.fps = fps;
        File f = new File(filePath);
        if (f.exists()) f.delete();
        try {
            muxer = new MediaMuxer(filePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
        } catch (Exception e) {
            Log.e(TAG, "MediaMuxer 创建失败", e);
            return;
        }
        MediaFormat format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h);
        // Surface 输入：编码器直接从 Surface 消费纹理，无需 CPU 转 YUV。
        format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        format.setInteger(MediaFormat.KEY_BIT_RATE, w * h * 4);
        format.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
        try {
            encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
            encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            inputSurface = encoder.createInputSurface();
            encoder.start();
            Log.i(TAG, "Surface encoder created " + w + "x" + h + " fps=" + fps + " surface=" + inputSurface);
        } catch (Exception e) {
            Log.e(TAG, "Surface encoder 配置失败", e);
        }
    }

    /** 返回输入 Surface（供 Unity P/Invoke startPreview 直接渲染到该 Surface）。 */
    public Surface getInputSurface() {
        return inputSurface;
    }

    /** 周期性排空编码输出到 muxer。返回当前已编码帧数。 */
    public long encodeAndDrain() {
        if (encoder == null || muxer == null) return frameCount;
        try {
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            int outIdx;
            while ((outIdx = encoder.dequeueOutputBuffer(info, 10000)) >= 0) {
                ByteBuffer outBuf = encoder.getOutputBuffer(outIdx);
                if ((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) {
                    encoder.releaseOutputBuffer(outIdx, false);
                    continue;
                }
                if (!muxerStarted) {
                    MediaFormat mf = encoder.getOutputFormat();
                    trackIndex = muxer.addTrack(mf);
                    muxer.start();
                    muxerStarted = true;
                }
                if (outBuf != null) {
                    outBuf.position(info.offset);
                    outBuf.limit(info.offset + info.size);
                    muxer.writeSampleData(trackIndex, outBuf, info);
                }
                encoder.releaseOutputBuffer(outIdx, false);
                if (frameCount == 0) {
                    firstTs = info.presentationTimeUs;
                }
                lastTs = info.presentationTimeUs;
                frameCount++;
                if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) break;
            }
        } catch (Exception e) {
            Log.e(TAG, "encodeAndDrain 异常", e);
        }
        return frameCount;
    }

    /** 输出统计：帧数、首个/末个 PTS、推算平均帧间隔 ms。 */
    public String stats() {
        if (frameCount < 2) return "frames=" + frameCount;
        double spanMs = (lastTs - firstTs) / 1000.0;
        double avgMs = spanMs / (frameCount - 1);
        return "frames=" + frameCount + " spanMs=" + (long) spanMs + " avgFrameMs=" + String.format("%.2f", avgMs)
                + " fps=" + String.format("%.1f", 1000.0 / avgMs);
    }

    public void finish() {
        if (encoder == null) return;
        try {
            encoder.signalEndOfInputStream();
            // 排空至 EOS
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            boolean eos = false;
            while (!eos) {
                int outIdx = encoder.dequeueOutputBuffer(info, 10000);
                if (outIdx >= 0) {
                    ByteBuffer outBuf = encoder.getOutputBuffer(outIdx);
                    if ((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0) {
                        if (!muxerStarted) {
                            MediaFormat mf = encoder.getOutputFormat();
                            trackIndex = muxer.addTrack(mf);
                            muxer.start();
                            muxerStarted = true;
                        }
                        if (outBuf != null) {
                            outBuf.position(info.offset);
                            outBuf.limit(info.offset + info.size);
                            muxer.writeSampleData(trackIndex, outBuf, info);
                        }
                        frameCount++;
                    }
                    if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) eos = true;
                    encoder.releaseOutputBuffer(outIdx, false);
                }
            }
            encoder.stop();
            encoder.release();
            encoder = null;
            inputSurface = null;
            if (muxer != null) {
                if (muxerStarted) muxer.stop();
                muxer.release();
                muxer = null;
            }
            Log.i(TAG, "finish done: " + stats());
        } catch (Exception e) {
            Log.e(TAG, "finish 异常", e);
        }
    }
}
