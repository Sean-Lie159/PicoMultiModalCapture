# AGENTS.md — 开发指南

> 本项目由作者与 AI 协作（vibe coding）完成，代码结构对 AI 助手友好，便于接手维护与扩展。
> 本文档面向开发者 / AI 助手，提供工程结构、关键架构、构建流程与踩坑点。

## 工程结构

```
Assets/
  Editor/BuildAPK.cs            # "PICO Capture > Build APK" 菜单构建
  Plugins/Android/              # Android 插件（Java + 原生库 + manifest + gradle）
    SurfaceEncoder.java         # 方案A：MediaCodec Surface 直通硬编码器（60fps）
    VideoEncoder.java           # 旧版 CPU rgbaToNv12 编码器（遗留路径用）
    VolumeKeyActivity.java      # 拦截头显物理音量键 → 触发录制启停
    CameraRenderingPlugin.aar   # PICO for4U 相机原生库（libpxrplatformloader 体系）
    AndroidManifest.xml         # 权限 + 自定义 Activity
    launcherTemplate.gradle     # Gradle 模板（默认 debug 签名）
  Resources/
  Scenes/Main.unity             # 唯一构建场景（脚本靠 Bootstrap 动态创建，场景几乎无挂载）
  Scripts/
    Capture/CaptureBootstrap.cs # 启动入口：动态创建所有组件（EventSystem/Manager/UI）
    Capture/CaptureManager.cs   # 采集调度：统一时间戳采样 头/身/手 + 视频启停 + 异步导出
    Capture/PICOFor4UCapture.cs # for4U 双目 RGB 相机采集 + Surface 直通编码 + 相机标定
    Capture/BodyCapture.cs      # PICO Body Tracking（24 关节，Motion Trackers）
    Capture/HandCapture.cs      # PICO Hand Tracking（双手各 26 关节）
    Capture/VolumeKeyTrigger.cs # 音量键事件 → 采集管理器
    Capture/HeadPoseCapture.cs  # 头部 6DoF
    Capture/ScreenCaptureBridge.cs # 遗留 MediaProjection 路径（不再触发）
    Capture/VSTCameraProbe.cs   # 可选诊断：VST 透视相机探针（默认关闭）
    Core/DataExporter.cs        # data.json / data.csv / meta.json 导出
    Core/CameraMeta.cs          # 相机标定参数模型
    UI/RecorderUI.cs            # 世界空间 UI + 身体丢失提示
  XR/Settings/OpenXR Package Settings.asset  # OpenXR 特性配置
  link.xml                      # IL2CPP 防剥离（关键，不可删）
Packages/manifest.json          # 依赖声明（PICO OpenXR SDK 从官方 Git 拉取）
ProjectSettings/                # Unity 工程配置
```

## 关键架构

- **启动**：`CaptureBootstrap` 用 `[RuntimeInitializeOnLoadMethod]` 在场景加载后动态创建 EventSystem、CaptureManager、RecorderUI。**场景本身不挂脚本**。若 `link.xml` 缺失，IL2CPP 会剥离所有脚本，APK 打开后无任何功能。
- **采集调度**：`CaptureManager.Update()` 每采样帧（默认 30Hz）依次读取 头/身/手，共用高精度 `Stopwatch`，`t` 时间戳严格对齐。head/hand/body 共享同一 OpenXR local-floor 空间（地平面原点，Y 向上）。
- **双目视频**：`PICOFor4UCapture` 用 PICO Enterprise for4U 相机（`CameraRenderingPlugin.so`）输出左右并排 SBS（2560×720）。`SurfaceEncoder.java` 用 `MediaCodec.createInputSurface()` + `startPreview(surface,_3D,2560,720)` 实现 Surface 直通硬编码（60fps），绕开 CPU 颜色转换。
- **相机标定**：`FetchCameraParams()` 用 `PXR_Enterprise.GetCameraParametersNewfor4U` 导出 fx/fy/cx/cy + 左右外参 + 基线（6.4cm），写 `meta.json`。
- **异步导出**：停止录制时数据在后台线程导出，主线程即时响应 UI（长时间录制不卡顿）。
- **UI**：世界空间 Canvas 跟随相机；录制中隐藏主 UI；身体丢失时底部显示一行提示（独立 Canvas，不影响录制的视频画面）。

## 构建

- 菜单：打开 `Assets/Scenes/Main.unity`，`PICO Capture > Build APK`。
- 命令行：`.\build_apk.ps1 -UnityPath "<Unity.exe 路径>"`（或 `build_apk.sh`）。
- 产物：`Build/PicoMultiModalCapture.apk`；安装 `adb install -r Build/PicoMultiModalCapture.apk`。
- 调试：`adb logcat -s Unity`。

## 关键踩坑点

- **必须佩戴头显**再启动应用，否则 PICO `seethrough.setting` 抢占前台、VR 应用被挂起，表现为"无任何日志/功能"——是佩戴问题，不是 IL2CPP 剥离。
- **for4U 相机 JNI 调用必须在 Unity 主线程**（后台线程无 JVM classloader 会崩溃）。
- **`link.xml` 不可删**：否则 IL2CPP 剥离所有动态创建的脚本。
- **包名**：`com.DefaultCompany.PicoMultiModalCapture`，Activity 为 `VolumeKeyActivity`（Java package 需与 manifest 一致）。
- **for4U 相机需 PICO 4 Ultra Enterprise + `getCameraInfo` 企业授权**；普通消费版无法调用。
- **SDK 不导出镜头畸变系数**（`GetCameraIntrinsicsfor4U` 仅返回 `[cx,cy,fx,fy]`），边缘畸变需离线棋盘格标定。
- **for4U 相机 FOV 固定**（约 76°×61°，硬件决定）；PICO 官方"105° 对角线"是显示 FOV，非 for4U 采集 FOV。
- **iToF 深度相机数据不开放导出**；深度/点云用双目视差（`Z = fx·baseline/disparity`）。

## 协作开发建议

本项目采用 vibe coding 工作流：需求 → AI 协助实现/排错 → 设备实测验证 → 记录到本文档。新贡献者可用 AI 助手辅助理解代码，按本文档的架构与踩坑点快速上手。保持本文档与代码同步更新。
