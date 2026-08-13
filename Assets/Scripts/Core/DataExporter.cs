using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

namespace PicoMultiModalCapture
{
    // 将内存中的帧序列导出为设备本地文件：
    //   data.json  —— 全模态（头/身体/双手/视频路径）带统一时间戳的完整数据
    //   data.csv   —— 宽表（头7列 + 身体24*7 + 双手26*7*2），便于 Python/pandas 读取
    public static class DataExporter
    {
        public static void Export(string folder, List<FrameSample> frames, CaptureManager cfg)
        {
            if (cfg.writeJson) WriteJson(folder, frames, cfg);
            if (cfg.writeCsv) WriteCsv(folder, frames, cfg);
            WriteMetaJson(folder, frames, cfg); // meta.json 始终写（相机标定/设备参数，独立于逐帧数据）
        }

        // 独立的元数据文件 meta.json：记录设备/会话信息 + 双目相机标定参数（内参/外参/基线）。
        // 这些是静态/低频参数，与 data.json 的逐帧序列分离，便于离线立体匹配/深度/点云直接加载。
        static void WriteMetaJson(string folder, List<FrameSample> frames, CaptureManager cfg)
        {
            var sb = new StringBuilder();
            sb.Append("{\n");
            sb.Append("  \"session\": {\n");
            sb.AppendFormat("    \"device\": \"PICO 4 Ultra Enterprise\",\n");
            // 用 cfg.unityVersionCache（主线程缓存的版本号），避免后台导出线程调用 Application.unityVersion。
            sb.AppendFormat("    \"unityVersion\": \"{0}\",\n", cfg.unityVersionCache);
            sb.AppendFormat("    \"frameCount\": {0},\n", frames.Count);
            sb.AppendFormat("    \"durationSec\": {0:F3},\n", frames.Count > 0 ? frames[frames.Count - 1].t : 0);
            // videoFps 用实际编码帧率（Surface 直通后 ~60fps），配置值 cfg.videoFps 仅为初始设定。
            int realFps = cfg.cameraMeta.actualVideoFps > 0 ? cfg.cameraMeta.actualVideoFps : cfg.videoFps;
            sb.AppendFormat("    \"videoFps\": {0},\n", realFps);
            sb.AppendFormat("    \"videoWidth\": {0},\n", cfg.videoWidth);
            sb.AppendFormat("    \"videoHeight\": {0},\n", cfg.videoHeight);
            sb.AppendFormat("    \"videoFile\": \"{0}\",\n", "video.mp4");
            sb.Append("    \"videoStereoLayout\": \"side-by-side\",\n");
            sb.AppendFormat("    \"videoStereoDesc\": \"{0}\",\n", "左半=左眼 RGB，右半=右眼 RGB，每眼宽为 videoWidth/2");
            sb.Append("    \"dataFile\": \"data.json\"\n");
            sb.Append("  },\n");
            sb.Append("  \"camera\": {\n");
            sb.AppendFormat("    \"available\": {0},\n", cfg.cameraMeta.available ? "true" : "false");
            sb.AppendFormat("    \"resolution\": [{0}, {1}],\n", cfg.videoWidth / 2, cfg.videoHeight); // 单眼分辨率
            sb.Append("    \"intrinsics\": {");
            sb.AppendFormat("\"fx\": {0:F6}, \"fy\": {1:F6}, \"cx\": {2:F6}, \"cy\": {3:F6}",
                F6(cfg.cameraMeta.fx), F6(cfg.cameraMeta.fy), F6(cfg.cameraMeta.cx), F6(cfg.cameraMeta.cy));
            sb.Append("},\n");
            sb.AppendFormat("    \"baseline\": {0:F6},\n", cfg.cameraMeta.baseline);
            sb.Append("    \"left\": { \"position\": [");
            sb.AppendFormat("{0:F6},{1:F6},{2:F6}", cfg.cameraMeta.lpx, cfg.cameraMeta.lpy, cfg.cameraMeta.lpz);
            sb.Append("], \"rotation\": [");
            sb.AppendFormat("{0:F6},{1:F6},{2:F6},{3:F6}", cfg.cameraMeta.lqx, cfg.cameraMeta.lqy, cfg.cameraMeta.lqz, cfg.cameraMeta.lqw);
            sb.Append("] },\n");
            sb.Append("    \"right\": { \"position\": [");
            sb.AppendFormat("{0:F6},{1:F6},{2:F6}", cfg.cameraMeta.rpx, cfg.cameraMeta.rpy, cfg.cameraMeta.rpz);
            sb.Append("], \"rotation\": [");
            sb.AppendFormat("{0:F6},{1:F6},{2:F6},{3:F6}", cfg.cameraMeta.rqx, cfg.cameraMeta.rqy, cfg.cameraMeta.rqz, cfg.cameraMeta.rqw);
            sb.Append("] }\n");
            sb.Append("  },\n");
            sb.Append("  \"skeleton\": {\n");
            sb.AppendFormat("    \"coordinateFrame\": \"{0}\",\n", "Unity world (local floor space, Y-up, floor origin; head/hand/body all in same space)");
            sb.AppendFormat("    \"bodyJointNames\": {0},\n", Arr(CaptureConst.BodyJointNames));
            sb.AppendFormat("    \"handJointNames\": {0}\n", Arr(CaptureConst.HandJointNames));
            sb.Append("  }\n");
            sb.Append("}\n");
            File.WriteAllText(Path.Combine(folder, "meta.json"), sb.ToString());
        }

        // 把 double 格式化为 6 位小数；NaN/Infinity 替换为 0（避免破坏 JSON 合法性）。
        static string F6(double v)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) return "0.000000";
            return v.ToString("F6", System.Globalization.CultureInfo.InvariantCulture);
        }

        static void WriteJson(string folder, List<FrameSample> frames, CaptureManager cfg)
        {
            var sb = new StringBuilder();
            sb.Append("{\n");
            sb.Append("  \"meta\": {\n");
            sb.Append("    \"device\": \"PICO 4 Ultra\",\n");
            // 用 cfg.unityVersionCache（主线程缓存的版本号），避免后台导出线程调用 Application.unityVersion。
            sb.AppendFormat("    \"unityVersion\": \"{0}\",\n", cfg.unityVersionCache);
            sb.AppendFormat("    \"frameCount\": {0},\n", frames.Count);
            sb.AppendFormat("    \"durationSec\": {0:F3},\n", frames.Count > 0 ? frames[frames.Count - 1].t : 0);
            sb.AppendFormat("    \"videoFps\": {0},\n", cfg.videoFps);
            sb.AppendFormat("    \"videoWidth\": {0},\n", cfg.videoWidth);
            sb.AppendFormat("    \"videoHeight\": {0},\n", cfg.videoHeight);
            sb.Append("    \"videoFile\": \"video.mp4\",\n");
            sb.Append("    \"coordinateFrame\": \"Unity world (head = main camera transform)\",\n");
            sb.AppendFormat("    \"bodyJointNames\": {0},\n", Arr(CaptureConst.BodyJointNames));
            sb.AppendFormat("    \"handJointNames\": {0},\n", Arr(CaptureConst.HandJointNames));
            sb.Append("    \"modalities\": [\"head6dof\", \"body24\", \"hands26x2\", \"video\"],\n");
            sb.Append("    \"synchronization\": \"所有模态在 CaptureManager 同一帧循环内以统一高精度时钟采样，时间戳严格对齐\"\n");
            sb.Append("  },\n");
            sb.Append("  \"frames\": [\n");
            for (int i = 0; i < frames.Count; i++)
            {
                sb.Append(FrameToJson(frames[i]));// 缩进由 FrameToJson 内部处理
                sb.Append(i < frames.Count - 1 ? ",\n" : "\n");
            }
            sb.Append("  ]\n");
            sb.Append("}\n");
            File.WriteAllText(Path.Combine(folder, "data.json"), sb.ToString());
        }

        static string FrameToJson(FrameSample f)
        {
            var sb = new StringBuilder();
            sb.Append("    {\n");
            sb.AppendFormat("      \"t\": {0:F4},\n", f.t);
            sb.AppendFormat("      \"wallClock\": \"{0}\",\n", f.wallClock);
            sb.Append("      \"head\": { \"position\": [");
            sb.AppendFormat("{0:F4},{1:F4},{2:F4}", f.head.px, f.head.py, f.head.pz);
            sb.Append("], \"rotation\": [");
            sb.AppendFormat("{0:F4},{1:F4},{2:F4},{3:F4}", f.head.qx, f.head.qy, f.head.qz, f.head.qw);
            sb.AppendFormat("], \"confidence\": {0:F2} }},\n", f.head.confidence);
            sb.AppendFormat("      \"body\": {{ \"tracking\": {0}, \"confidence\": {1:F2}, \"joints\": [\n",
                f.hasBody ? "true" : "false", f.bodyConfidence);
            if (f.bodyJoints != null)
            {
                for (int i = 0; i < f.bodyJoints.Count; i++)
                {
                    var j = f.bodyJoints[i];
                    string name = CaptureConst.BodyJointNames[Mathf.Clamp(j.id, 0, CaptureConst.BodyJointCount - 1)];
                    sb.AppendFormat("        {{\"id\":{0},\"name\":\"{1}\",\"position\":[{2:F4},{3:F4},{4:F4}],\"rotation\":[{5:F4},{6:F4},{7:F4},{8:F4}],\"confidence\":{9:F2}}}",
                        j.id, name, j.px, j.py, j.pz, j.qx, j.qy, j.qz, j.qw, j.confidence);
                    sb.Append(i < f.bodyJoints.Count - 1 ? ",\n" : "\n");
                }
            }
            sb.Append("      ] },\n");
            sb.Append("      \"hands\": {\n");
            sb.Append("        \"left\": "); sb.Append(HandToJson(f.leftHand)); sb.Append(",\n");
            sb.Append("        \"right\": "); sb.Append(HandToJson(f.rightHand)); sb.Append("\n");
            sb.Append("      }\n");
            sb.Append("    }");
            return sb.ToString();
        }

        static string HandToJson(HandSample h)
        {
            var sb = new StringBuilder();
            sb.Append("{ \"tracked\": "); sb.Append(h.tracked ? "true" : "false");
            sb.AppendFormat(", \"scale\": {0:F3}, \"joints\": [", h.scale);
            if (h.joints != null)
            {
                for (int i = 0; i < h.joints.Count; i++)
                {
                    var j = h.joints[i];
                    string name = CaptureConst.HandJointNames[Mathf.Clamp(j.id, 0, CaptureConst.HandJointCount - 1)];
                    sb.AppendFormat("{{\"id\":{0},\"name\":\"{1}\",\"position\":[{2:F4},{3:F4},{4:F4}],\"rotation\":[{5:F4},{6:F4},{7:F4},{8:F4}],\"radius\":{9:F4}}}",
                        j.id, name, j.px, j.py, j.pz, j.qx, j.qy, j.qz, j.qw, j.radius);
                    if (i < h.joints.Count - 1) sb.Append(",");
                }
            }
            sb.Append("] }");
            return sb.ToString();
        }

        static string Arr(string[] a)
        {
            var sb = new StringBuilder("[");
            for (int i = 0; i < a.Length; i++) { sb.AppendFormat("\"{0}\"", a[i]); if (i < a.Length - 1) sb.Append(","); }
            sb.Append("]");
            return sb.ToString();
        }

        static void WriteCsv(string folder, List<FrameSample> frames, CaptureManager cfg)
        {
            var sb = new StringBuilder();
            var header = new List<string> { "t" };
            header.AddRange(new[] { "head_px", "head_py", "head_pz", "head_qx", "head_qy", "head_qz", "head_qw" });
            for (int i = 0; i < CaptureConst.BodyJointCount; i++)
            {
                string n = CaptureConst.BodyJointNames[i];
                header.Add($"b{i}_{n}_px"); header.Add($"b{i}_{n}_py"); header.Add($"b{i}_{n}_pz");
                header.Add($"b{i}_{n}_qx"); header.Add($"b{i}_{n}_qy"); header.Add($"b{i}_{n}_qz"); header.Add($"b{i}_{n}_qw");
            }
            for (int i = 0; i < CaptureConst.HandJointCount; i++)
            {
                string n = CaptureConst.HandJointNames[i];
                header.Add($"L{i}_{n}_px"); header.Add($"L{i}_{n}_py"); header.Add($"L{i}_{n}_pz");
                header.Add($"L{i}_{n}_qx"); header.Add($"L{i}_{n}_qy"); header.Add($"L{i}_{n}_qz"); header.Add($"L{i}_{n}_qw");
                header.Add($"R{i}_{n}_px"); header.Add($"R{i}_{n}_py"); header.Add($"R{i}_{n}_pz");
                header.Add($"R{i}_{n}_qx"); header.Add($"R{i}_{n}_qy"); header.Add($"R{i}_{n}_qz"); header.Add($"R{i}_{n}_qw");
            }
            sb.Append(string.Join(",", header)).Append("\n");

            foreach (var f in frames)
            {
                var row = new List<string> { f.t.ToString("F4") };
                row.AddRange(new[] { f.head.px.ToString("F4"), f.head.py.ToString("F4"), f.head.pz.ToString("F4"),
                    f.head.qx.ToString("F4"), f.head.qy.ToString("F4"), f.head.qz.ToString("F4"), f.head.qw.ToString("F4") });
                for (int i = 0; i < CaptureConst.BodyJointCount; i++)
                {
                    var j = (f.bodyJoints != null && i < f.bodyJoints.Count) ? f.bodyJoints[i] : default;
                    row.AddRange(new[] { j.px.ToString("F4"), j.py.ToString("F4"), j.pz.ToString("F4"),
                        j.qx.ToString("F4"), j.qy.ToString("F4"), j.qz.ToString("F4"), j.qw.ToString("F4") });
                }
                for (int i = 0; i < CaptureConst.HandJointCount; i++)
                {
                    var lj = (f.leftHand.joints != null && i < f.leftHand.joints.Count) ? f.leftHand.joints[i] : default;
                    var rj = (f.rightHand.joints != null && i < f.rightHand.joints.Count) ? f.rightHand.joints[i] : default;
                    row.AddRange(new[] { lj.px.ToString("F4"), lj.py.ToString("F4"), lj.pz.ToString("F4"),
                        lj.qx.ToString("F4"), lj.qy.ToString("F4"), lj.qz.ToString("F4"), lj.qw.ToString("F4") });
                    row.AddRange(new[] { rj.px.ToString("F4"), rj.py.ToString("F4"), rj.pz.ToString("F4"),
                        rj.qx.ToString("F4"), rj.qy.ToString("F4"), rj.qz.ToString("F4"), rj.qw.ToString("F4") });
                }
                sb.Append(string.Join(",", row)).Append("\n");
            }
            File.WriteAllText(Path.Combine(folder, "data.csv"), sb.ToString());
        }
    }
}
