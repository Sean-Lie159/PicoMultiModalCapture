# AGENTS.md — Development Guide / 开发指南

> Built by the author in collaboration with AI (vibe coding). The structure is AI-friendly for easier handoff, maintenance, and extension.
>
> 本项目由作者与 AI 协作（vibe coding）完成，代码结构对 AI 助手友好，便于接手维护与扩展。
>
> **English / 中文** — Each section is presented in English followed by Chinese.

## Project Structure / 工程结构

```
Assets/
  Editor/BuildAPK.cs            # "PICO Capture > Build APK" menu build / 菜单构建
  Plugins/Android/              # Android plugins (Java + native lib + manifest + gradle) / Android 插件
    SurfaceEncoder.java         # Method A: MediaCodec Surface direct encoder (60fps) / 方案A：Surface 直通硬编码器
    VideoEncoder.java           # Legacy CPU rgbaToNv12 encoder (used by legacy path) / 旧版 CPU 编码器
    VolumeKeyActivity.java      # Intercept headset volume keys -> recording start/stop / 拦截音量键触发录制
    CameraRenderingPlugin.aar   # PICO for4U camera native lib (libpxrplatformloader family) / for4U 相机原生库
    AndroidManifest.xml         # Permissions + custom Activity / 权限 + 自定义 Activity
    launcherTemplate.gradle     # Gradle template (default debug signing) / Gradle 模板
  Resources/
  Scenes/Main.unity             # The only build scene (scripts created by Bootstrap, scene is nearly empty) / 唯一构建场景
  Scripts/
    Capture/CaptureBootstrap.cs # Entry point: dynamically create all components (EventSystem/Manager/UI) / 启动入口
    Capture/CaptureManager.cs   # Capture scheduling: unified-timestamp sampling head/body/hands + video control + async export / 采集调度
    Capture/PICOFor4UCapture.cs # for4U stereo RGB capture + Surface encode + camera calibration / for4U 双目采集
    Capture/BodyCapture.cs      # PICO Body Tracking (24 joints, Motion Trackers) / 身体追踪
    Capture/HandCapture.cs      # PICO Hand Tracking (26 joints per hand) / 手部追踪
    Capture/VolumeKeyTrigger.cs # Volume-key events -> capture manager / 音量键事件
    Capture/HeadPoseCapture.cs  # Head 6DoF / 头部 6DoF
    Capture/ScreenCaptureBridge.cs # Legacy MediaProjection path (no longer triggered) / 遗留 MediaProjection 路径
    Capture/VSTCameraProbe.cs   # Optional diagnostic: VST passthrough camera probe (off by default) / 可选诊断
    Core/DataExporter.cs        # data.json / data.csv / meta.json export / 数据导出
    Core/CameraMeta.cs          # Camera calibration model / 相机标定模型
    UI/RecorderUI.cs            # World-space UI + body-lost hint / 世界空间 UI + 身体丢失提示
  XR/Settings/OpenXR Package Settings.asset  # OpenXR feature config / OpenXR 特性配置
  link.xml                      # IL2CPP stripping guard (critical, do not delete) / IL2CPP 防剥离
Packages/manifest.json          # Dependency declarations (PICO OpenXR SDK fetched from official Git) / 依赖声明
ProjectSettings/                # Unity project config / Unity 工程配置
```

## Key Architecture / 关键架构

- **Startup**: `CaptureBootstrap` uses `[RuntimeInitializeOnLoadMethod]` to dynamically create EventSystem, CaptureManager, RecorderUI after scene load. **The scene itself has no attached scripts.** If `link.xml` is missing, IL2CPP strips all scripts and the APK opens with no functionality.
  **启动**：`CaptureBootstrap` 用 `[RuntimeInitializeOnLoadMethod]` 在场景加载后动态创建 EventSystem、CaptureManager、RecorderUI。**场景本身不挂脚本**。若 `link.xml` 缺失，IL2CPP 剥离所有脚本，APK 打开后无任何功能。
- **Capture scheduling**: `CaptureManager.Update()` reads head/body/hands each sample frame (default 30Hz) using a shared high-precision `Stopwatch`; `t` timestamps are strictly aligned. head/hand/body share the same OpenXR local-floor space (floor origin, Y up).
  **采集调度**：`CaptureManager.Update()` 每采样帧（默认 30Hz）依次读取头/身/手，共用高精度 `Stopwatch`，`t` 时间戳严格对齐。head/hand/body 共享同一 OpenXR local-floor 空间（地平面原点，Y 向上）。
- **Stereo video**: `PICOFor4UCapture` uses the PICO Enterprise for4U camera (`CameraRenderingPlugin.so`) to output side-by-side SBS (2560×720). `SurfaceEncoder.java` uses `MediaCodec.createInputSurface()` + `startPreview(surface,_3D,2560,720)` for Surface-direct hardware encode (60fps), bypassing CPU color conversion.
  **双目视频**：`PICOFor4UCapture` 用 for4U 相机输出左右并排 SBS（2560×720）。`SurfaceEncoder.java` 用 MediaCodec 输入 Surface + `startPreview` 实现 Surface 直通硬编码（60fps）。
- **Camera calibration**: `FetchCameraParams()` uses `PXR_Enterprise.GetCameraParametersNewfor4U` to export fx/fy/cx/cy + left/right extrinsics + baseline (6.4cm) into `meta.json`.
  **相机标定**：`PXR_Enterprise.GetCameraParametersNewfor4U` 导出内参/外参/基线（6.4cm），写 `meta.json`。
- **Async export**: data is exported on a background thread on stop, keeping the main thread responsive (no stutter for long recordings).
  **异步导出**：停止录制时数据在后台线程导出，主线程即时响应 UI。
- **UI**: world-space Canvas follows the camera; main UI hides during recording; a body-lost hint shows at the bottom (independent Canvas, does not affect the recorded video).
  **UI**：世界空间 Canvas 跟随相机；录制中隐藏主 UI；身体丢失时底部显示一行提示。

## Build / 构建

- Menu: open `Assets/Scenes/Main.unity`, `PICO Capture > Build APK`. — 菜单：打开 `Assets/Scenes/Main.unity`，`PICO Capture > Build APK`。
- Command line: `.\build_apk.ps1 -UnityPath "<Unity.exe path>"` (or `build_apk.sh`). — 命令行：`.\build_apk.ps1 -UnityPath "<Unity.exe 路径>"`。
- Output: `Build/PicoMultiModalCapture.apk`; install `adb install -r Build/PicoMultiModalCapture.apk`. — 产物：`Build/PicoMultiModalCapture.apk`；安装 `adb install -r`。
- Debug: `adb logcat -s Unity`. — 调试：`adb logcat -s Unity`。

## Key Pitfalls / 关键踩坑点

- **Must wear the headset** before launching; otherwise PICO `seethrough.setting` steals the foreground and suspends the VR app — shown as "no logs/no functionality". This is a wearing issue, not IL2CPP stripping.
  **必须佩戴头显**再启动应用，否则 PICO `seethrough.setting` 抢占前台、VR 应用被挂起，表现为"无任何日志/功能"——是佩戴问题，不是 IL2CPP 剥离。
- **for4U camera JNI calls must run on the Unity main thread** (background threads have no JVM classloader and crash).
  **for4U 相机 JNI 调用必须在 Unity 主线程**（后台线程无 JVM classloader 会崩溃）。
- **`link.xml` must not be deleted**: otherwise IL2CPP strips all dynamically-created scripts.
  **`link.xml` 不可删**：否则 IL2CPP 剥离所有动态创建的脚本。
- **Package name**: `com.DefaultCompany.PicoMultiModalCapture`, Activity is `VolumeKeyActivity` (Java package must match the manifest).
  **包名**：`com.DefaultCompany.PicoMultiModalCapture`，Activity 为 `VolumeKeyActivity`（Java package 需与 manifest 一致）。
- **for4U camera requires PICO 4 Ultra Enterprise + `getCameraInfo` enterprise auth**; consumer PICO 4 Ultra cannot access it.
  **for4U 相机需 PICO 4 Ultra Enterprise + `getCameraInfo` 企业授权**；普通消费版无法调用。
- **SDK does not export lens distortion coefficients** (`GetCameraIntrinsicsfor4U` returns only `[cx,cy,fx,fy]`); edge distortion needs offline chessboard calibration.
  **SDK 不导出镜头畸变系数**；边缘畸变需离线棋盘格标定。
- **for4U FOV is fixed** (~76°×61°, hardware); PICO's official "105° diagonal" is the display FOV, not the for4U capture FOV.
  **for4U 相机 FOV 固定**（约 76°×61°）；PICO 官方"105° 对角线"是显示 FOV，非 for4U 采集 FOV。
- **iToF depth data is not exposed**; depth/point clouds use stereo disparity (`Z = fx·baseline/disparity`).
  **iToF 深度数据不开放**；深度/点云用双目视差。

## Collaboration Notes / 协作开发建议

This project follows a vibe-coding workflow: requirement → AI-assisted implementation/debugging → on-device verification → documented here. New contributors may use an AI assistant to help understand the code and get started quickly with the architecture and pitfalls above. Keep this document in sync with the code.

本项目采用 vibe coding 工作流：需求 → AI 协助实现/排错 → 设备实测验证 → 记录到本文档。新贡献者可用 AI 助手辅助理解代码，按本文档的架构与踩坑点快速上手。保持本文档与代码同步更新。
