package com.picocapture;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.util.Log;

import java.io.File;
import java.nio.ByteBuffer;

/**
 * 安卓原生视频编码器：接收 RGBA 帧，转换为 NV12（YUV420 半平面）后由 MediaCodec
 * 编码为 H.264，再用 MediaMuxer 封装为 MP4。纯 Android 系统 API，无需引入 FFmpeg。
 */
public class VideoEncoder {
    private static final String TAG = "PicoCaptureVideoEncoder";
    private MediaCodec encoder;
    private MediaMuxer muxer;
    private int trackIndex = -1;
    private boolean muxerStarted = false;
    private int width, height, fps;
    private int frameIndex = 0;
    private ByteBuffer yuv;

    public VideoEncoder(String filePath, int w, int h, int fps) {
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
        format.setInteger(MediaFormat.KEY_BIT_RATE, w * h * 4);
        format.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
        format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible);
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);

        try {
            encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
            encoder.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            encoder.start();
        } catch (Exception e) {
            Log.e(TAG, "MediaCodec 配置失败", e);
        }
        yuv = ByteBuffer.allocateDirect((int) (w * h * 1.5));
    }

    public void encodeFrame(byte[] rgba, long pts) {
        if (encoder == null || muxer == null) return;
        int ySize = width * height;
        if (yuv.capacity() < ySize * 3 / 2) yuv = ByteBuffer.allocateDirect(ySize * 3 / 2);
        rgbaToNv12(rgba, yuv, width, height);

        try {
            int inIdx = encoder.dequeueInputBuffer(10000);
            if (inIdx >= 0) {
                ByteBuffer inputBuf = encoder.getInputBuffer(inIdx);
                if (inputBuf != null) {
                    inputBuf.clear();
                    yuv.rewind();
                    inputBuf.put(yuv);
                    encoder.queueInputBuffer(inIdx, 0, ySize * 3 / 2, pts, 0);
                    frameIndex++;
                }
            }
            drain(false);
        } catch (Exception e) {
            Log.e(TAG, "encodeFrame 异常", e);
        }
    }

    private void drain(boolean end) {
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
                if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) break;
            }
        } catch (Exception e) {
            Log.e(TAG, "drain 异常", e);
        }
    }

    public void finish() {
        if (encoder == null) return;
        try {
            // 发送 EOS 标记
            int inIdx = encoder.dequeueInputBuffer(10000);
            if (inIdx >= 0) {
                encoder.queueInputBuffer(inIdx, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
            }
            drain(true);
            encoder.stop();
            encoder.release();
            encoder = null;
            if (muxer != null) {
                if (muxerStarted) { muxer.stop(); }
                muxer.release();
                muxer = null;
            }
        } catch (Exception e) {
            Log.e(TAG, "finish 异常", e);
        }
    }

    // 将 RGBA 字节数组转换为 NV12（Y 平面 + 交错的 U/V 半平面）。
    private static void rgbaToNv12(byte[] rgba, ByteBuffer out, int w, int h) {
        int ySize = w * h;
        int yi = 0;
        for (int i = 0; i < rgba.length; i += 4) {
            int r = rgba[i] & 0xff;
            int g = rgba[i + 1] & 0xff;
            int b = rgba[i + 2] & 0xff;
            int y = (int) (0.299 * r + 0.587 * g + 0.114 * b);
            out.put(yi++, (byte) y);
        }
        int uvOffset = ySize;
        int uvi = 0;
        for (int y = 0; y < h; y += 2) {
            for (int x = 0; x < w; x += 2) {
                int idx = (y * w + x) * 4;
                int r = rgba[idx] & 0xff;
                int g = rgba[idx + 1] & 0xff;
                int b = rgba[idx + 2] & 0xff;
                int u = (int) ((-0.169 * r - 0.331 * g + 0.5 * b) + 128);
                int v = (int) ((0.5 * r - 0.419 * g - 0.081 * b) + 128);
                out.put(uvOffset + uvi, (byte) u);
                out.put(uvOffset + uvi + 1, (byte) v);
                uvi += 2;
            }
        }
        out.rewind();
    }
}
