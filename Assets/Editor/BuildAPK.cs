#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace PicoMultiModalCapture
{
    // 一键构建 APK：使用 Main.unity 场景，构建前尽力配置 XR。
    public static class BuildAPK
    {
        const string ScenePath = "Assets/Scenes/Main.unity";

        [MenuItem("PICO Capture/Build APK")]
        public static void Build()
        {
            if (!File.Exists(ScenePath))
            {
                Debug.LogError("[BuildAPK] 构建场景不存在: " + ScenePath + "，请先在 Unity 中保存 Main 场景。");
                return;
            }
            XRSetup.Ensure();

            string path = "Build/PicoMultiModalCapture.apk";
            BuildPlayerOptions opt = new BuildPlayerOptions();
            opt.scenes = new[] { ScenePath };
            opt.locationPathName = path;
            opt.target = BuildTarget.Android;
            opt.options = BuildOptions.None;
            var report = BuildPipeline.BuildPlayer(opt);
            Debug.Log("Build 结果: " + report.summary.result + "  产物: " + path);
        }
    }
}
#endif
