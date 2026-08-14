# AGENTS.md — Development Guide / 开发指南

> Built by the author in collaboration with AI (vibe coding). The structure is AI-friendly for easier handoff, maintenance, and extension. The companion offline processing pipeline has its own guide in [`tools/AGENTS.md`](tools/AGENTS.md).
>
> 本项目由作者与 AI 协作（vibe coding）完成，代码结构对 AI 助手友好，便于接手维护与扩展。配套的离线处理管线有独立指南，见 [`tools/AGENTS.md`](tools/AGENTS.md)。
>
> **English first, then 中文.** — 英文在前，中文在后。

---

## English

### Project Structure

```
Assets/
  Editor/BuildAPK.cs            # "PICO Capture > Build APK" menu build
  Plugins/Android/              # Android plugins (Java + native lib + manifest + gradle)
    SurfaceEncoder.java         # Method A: MediaCodec Surface direct encoder (60fps)
    VideoEncoder.java           # Legacy CPU rgbaToNv12 encoder (legacy path)
    VolumeKeyActivity.java      # Intercept headset volume keys -> recording start/stop
    CameraRenderingPlugin.aar   # PICO for4U camera native lib (libpxrplatformloader family)
    AndroidManifest.xml         # Permissions + custom Activity
    launcherTemplate.gradle     # Gradle template (default debug signing)
  Resources/
  Scenes/Main.unity             # The only build scene (scripts created by Bootstrap, scene is nearly empty)
  Scripts/
    Capture/CaptureBootstrap.cs # Entry point: dynamically create all components (EventSystem/Manager/UI)
    Capture/CaptureManager.cs   # Capture scheduling: unified-timestamp sampling head/body/hands + video control + async export
    Capture/PICOFor4UCapture.cs # for4U stereo RGB capture + Surface encode + camera calibration
    Capture/BodyCapture.cs      # PICO Body Tracking (24 joints, Motion Trackers)
    Capture/HandCapture.cs      # PICO Hand Tracking (26 joints per hand)
    Capture/VolumeKeyTrigger.cs # Volume-key events -> capture manager
    Capture/HeadPoseCapture.cs  # Head 6DoF
    Capture/ScreenCaptureBridge.cs # Legacy MediaProjection path (no longer triggered)
    Capture/VSTCameraProbe.cs   # Optional diagnostic: VST passthrough camera probe (off by default)
    Core/DataExporter.cs        # data.json / data.csv / meta.json export
    Core/CameraMeta.cs          # Camera calibration model
    UI/RecorderUI.cs            # World-space UI + body-lost hint
  XR/Settings/OpenXR Package Settings.asset  # OpenXR feature config
  link.xml                      # IL2CPP stripping guard (critical, do not delete)
Packages/manifest.json          # Dependency declarations (PICO OpenXR SDK fetched from official Git)
ProjectSettings/                # Unity project config
tools/                          # Offline processing pipeline (Python) — see tools/AGENTS.md
```

### Key Architecture

- **Startup**: `CaptureBootstrap` uses `[RuntimeInitializeOnLoadMethod]` to dynamically create EventSystem, CaptureManager, RecorderUI after scene load. **The scene itself has no attached scripts.** If `link.xml` is missing, IL2CPP strips all scripts and the APK opens with no functionality.
- **Capture scheduling**: `CaptureManager.Update()` reads head/body/hands each sample frame (default 30Hz) using a shared high-precision `Stopwatch`; `t` timestamps are strictly aligned. head/hand/body share the same OpenXR local-floor space (floor origin, Y up).
- **Stereo video**: `PICOFor4UCapture` uses the PICO Enterprise for4U camera (`CameraRenderingPlugin.so`) to output side-by-side SBS (2560×720). `SurfaceEncoder.java` uses `MediaCodec.createInputSurface()` + `startPreview(surface,_3D,2560,720)` for Surface-direct hardware encode (60fps), bypassing CPU color conversion.
- **Camera calibration**: `FetchCameraParams()` uses `PXR_Enterprise.GetCameraParametersNewfor4U` to export fx/fy/cx/cy + left/right extrinsics + baseline (6.4cm) into `meta.json`.
- **Async export**: data is exported on a background thread on stop, keeping the main thread responsive.
- **UI**: world-space Canvas follows the camera; main UI hides during recording; a body-lost hint shows at the bottom (independent Canvas, does not affect the recorded video).

### Build

- Menu: open `Assets/Scenes/Main.unity`, `PICO Capture > Build APK`.
- Command line: `.\build_apk.ps1 -UnityPath "<Unity.exe path>"` (or `build_apk.sh`).
- Output: `Build/PicoMultiModalCapture.apk`; install `adb install -r Build/PicoMultiModalCapture.apk`.
- Debug: `adb logcat -s Unity`.

### Key Pitfalls

- **Must wear the headset** before launching; otherwise PICO `seethrough.setting` steals the foreground and suspends the VR app — shown as "no logs/no functionality". This is a wearing issue, not IL2CPP stripping.
- **for4U camera JNI calls must run on the Unity main thread** (background threads have no JVM classloader and crash).
- **`link.xml` must not be deleted**: otherwise IL2CPP strips all dynamically-created scripts.
- **Package name**: `com.DefaultCompany.PicoMultiModalCapture`, Activity is `VolumeKeyActivity` (Java package must match the manifest).
- **for4U camera requires PICO 4 Ultra Enterprise + `getCameraInfo` enterprise auth**; consumer PICO 4 Ultra cannot access it.
- **SDK does not export lens distortion coefficients** (`GetCameraIntrinsicsfor4U` returns only `[cx,cy,fx,fy]`); edge distortion needs offline chessboard calibration.
- **for4U FOV is fixed** (~76°×61°, hardware); PICO's official "105° diagonal" is the display FOV, not the for4U capture FOV.
- **iToF depth data is not exposed**; depth/point clouds use stereo disparity (`Z = fx·baseline/disparity`).

### Collaboration Notes

This project follows a vibe-coding workflow: requirement → AI-assisted implementation/debugging → on-device verification → documented here. New contributors may use an AI assistant to help understand the code and get started quickly with the architecture and pitfalls above. Keep this document in sync with the code.

---

## 中文

### 工程结构

```
Assets/
  Editor/BuildAPK.cs            # "PICO Capture > Build APK" 菜单构建
  Plugins/Android/              # Android 插件（Java + 原生库 + manifest + gradle）
    SurfaceEncoder.java         # 方案A：MediaCodec Surface 直通硬编码器（60fps）
    VideoEncoder.java           # 旧版 CPU rgbaToNv12 编码器（遗留路径）
    VolumeKeyActivity.java      # 拦截头显音量键触发录制
    CameraRenderingPlugin.aar   # for4U 相机原生库（libpxrplatformloader 系列）
    AndroidManifest.xml         # 权限 + 自定义 Activity
    launcherTemplate.gradle     # Gradle 模板（默认 debug 签名）
  Resources/
  Scenes/Main.unity             # 唯一构建场景（脚本由 Bootstrap 创建，场景几乎为空）
  Scripts/
    Capture/CaptureBootstrap.cs # 启动入口：动态创建 EventSystem/Manager/UI
    Capture/CaptureManager.cs   # 采集调度：统一时间戳采样头/身/手 + 视频控制 + 异步导出
    Capture/PICOFor4UCapture.cs # for4U 双目采集 + Surface 编码 + 相机标定
    Capture/BodyCapture.cs      # PICO Body Tracking（24 关节，Motion Trackers）
    Capture/HandCapture.cs      # PICO Hand Tracking（每手 26 关节）
    Capture/VolumeKeyTrigger.cs # 音量键事件 → 采集管理器
    Capture/HeadPoseCapture.cs  # 头部 6DoF
    Capture/ScreenCaptureBridge.cs # 遗留 MediaProjection 路径（不再触发）
    Capture/VSTCameraProbe.cs   # 可选诊断：VST 透视相机探测（默认关闭）
    Core/DataExporter.cs        # data.json / data.csv / meta.json 导出
    Core/CameraMeta.cs          # 相机标定模型
    UI/RecorderUI.cs            # 世界空间 UI + 身体丢失提示
  XR/Settings/OpenXR Package Settings.asset  # OpenXR 特性配置
  link.xml                      # IL2CPP 防剥离（关键，不可删）
Packages/manifest.json          # 依赖声明（PICO OpenXR SDK 从官方 Git 拉取）
ProjectSettings/                # Unity 工程配置
tools/                          # 离线处理管线（Python）——见 tools/AGENTS.md
```

### 关键架构

- **启动**：`CaptureBootstrap` 用 `[RuntimeInitializeOnLoadMethod]` 在场景加载后动态创建 EventSystem、CaptureManager、RecorderUI。**场景本身不挂脚本**。若 `link.xml` 缺失，IL2CPP 剥离所有脚本，APK 打开后无任何功能。
- **采集调度**：`CaptureManager.Update()` 每采样帧（默认 30Hz）依次读取头/身/手，共用高精度 `Stopwatch`，`t` 时间戳严格对齐。head/hand/body 共享同一 OpenXR local-floor 空间（地平面原点，Y 向上）。
- **双目视频**：`PICOFor4UCapture` 用 for4U 相机输出左右并排 SBS（2560×720）。`SurfaceEncoder.java` 用 MediaCodec 输入 Surface + `startPreview` 实现 Surface 直通硬编码（60fps）。
- **相机标定**：`FetchCameraParams()` 用 `PXR_Enterprise.GetCameraParametersNewfor4U` 导出内参/外参/基线（6.4cm），写 meta.json。
- **异步导出**：停止录制时后台线程导出，主线程即时响应 UI。
- **UI**：世界空间 Canvas 跟随相机；录制中隐藏主 UI；身体丢失时底部显示一行提示（不影响录制画面）。

### 构建

- 菜单：打开 `Assets/Scenes/Main.unity`，`PICO Capture > Build APK`。
- 命令行：`.\build_apk.ps1 -UnityPath "<Unity.exe 路径>"`（或 `build_apk.sh`）。
- 产物：`Build/PicoMultiModalCapture.apk`；安装 `adb install -r`。
- 调试：`adb logcat -s Unity`。

### 关键踩坑点

- **必须佩戴头显**再启动应用，否则 PICO `seethrough.setting` 抢占前台、VR 应用被挂起，表现为"无任何日志/功能"——是佩戴问题，不是 IL2CPP 剥离。
- **for4U 相机 JNI 调用必须在 Unity 主线程**（后台线程无 JVM classloader 会崩溃）。
- **`link.xml` 不可删**：否则 IL2CPP 剥离所有动态创建的脚本。
- **包名**：`com.DefaultCompany.PicoMultiModalCapture`，Activity 为 `VolumeKeyActivity`（Java package 需与 manifest 一致）。
- **for4U 相机需 PICO 4 Ultra Enterprise + `getCameraInfo` 企业授权**；普通消费版无法调用。
- **SDK 不导出镜头畸变系数**（`GetCameraIntrinsicsfor4U` 仅返回 `[cx,cy,fx,fy]`）；边缘畸变需离线棋盘格标定。
- **for4U 相机 FOV 固定**（约 76°×61°）；PICO 官方"105° 对角线"是显示 FOV，非 for4U 采集 FOV。
- **iToF 深度数据不开放**；深度/点云用双目视差（`Z = fx·baseline/disparity`）。

### 协作开发建议

本项目采用 vibe coding 工作流：需求 → AI 协助实现/排错 → 设备实测验证 → 记录到本文档。新贡献者可用 AI 助手辅助理解代码，按本文档的架构与踩坑点快速上手。保持本文档与代码同步更新。
