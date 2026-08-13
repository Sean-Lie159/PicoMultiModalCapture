# PICO MultiModal Capture — PICO 4 Ultra 同步采集（双目 SBS · 60fps）

> **English / 中文** — Each section is presented in English followed by Chinese.

Capture four modalities in sync on **PICO 4 Ultra**, exported with **unified timestamps** for offline **multi-modal analysis / stereo vision / depth reconstruction / point clouds**.

在 **PICO 4 Ultra** 上同步采集四类数据，以**统一时间戳**导出到设备本地，供离线做**多模态分析 / 双目立体 / 深度重建 / 点云**。

- **Head 6DoF** pose (position + quaternion) — 头部 6DoF 位姿（位置 + 四元数）
- **Stereo first-person RGB video** (PICO Enterprise for4U dual RGB camera, side-by-side 2560×720, Surface-direct hardware encode at **60fps**) — 双目第一人称 RGB 视频（PICO Enterprise for4U 双 RGB 相机，左右并排 2560×720，Surface 直通硬编码 **60fps**）
- **Full-body 24 joints** (PICO Motion Trackers + Body Tracking) — 全身 24 关键点骨骼（PICO Motion Trackers + Body Tracking）
- **Hands 26 joints each** (PICO Hand Tracking) — 双手各 26 关键点姿态（PICO Hand Tracking）

> The app runs in MR/Passthrough mode. The recorded video is the **real-world view of the for4U dual RGB cameras** (not Unity main-camera rendering), stored as a side-by-side (SBS) single-stream MP4. Combined with `meta.json` camera intrinsics/extrinsics/baseline, you can do **stereo disparity → depth → point clouds** offline (`Z = fx·baseline/disparity`).
>
> 应用运行于 MR/Passthrough 模式。所录视频为 **for4U 双 RGB 相机的真实世界画面**（非 Unity 主相机渲染），左右并排（SBS）单流 MP4，配合 `meta.json` 的相机内参/外参/基线，可离线做 **双目视差 → 深度 → 点云**（`Z = fx·baseline/disparity`）。

---

## 1. Prerequisites / 环境要求

- **Unity 2022.3 LTS** (verified on 2022.3.62f3c1), with modules: `Android Build Support`, `OpenJDK`, `Android SDK & NDK Tools`. — **Unity 2022.3 LTS**（已验证 2022.3.62f3c1），安装模块：`Android Build Support`、`OpenJDK`、`Android SDK & NDK Tools`。
- **Android API 34** target; `Scripting Backend = IL2CPP`; `Target Architectures = ARM64`. — **Android API 34** 编译目标；`Scripting Backend = IL2CPP`；`Target Architectures = ARM64`。
- A **PICO 4 Ultra Enterprise** (for4U camera requires enterprise system + `getCameraInfo` auth) + 5 **PICO Motion Trackers** (paired & calibrated). — 一台 **PICO 4 Ultra Enterprise**（for4U 相机需企业系统 + `getCameraInfo` 授权）+ 5 个 **PICO Motion Trackers**（已配对校准）。

---

## 2. SDK Dependencies / 用到的 SDK

All dependencies are declared in `Packages/manifest.json` and **auto-fetched by Unity Package Manager** when you open the project (no manual download needed).

本项目基于以下 SDK，均在 `Packages/manifest.json` 中声明，**打开工程时由 Unity Package Manager 自动拉取**（无需手动下载）：

| Package / 包名 | Version / 版本 | Purpose / 用途 | Source & Download / 来源与下载 |
|------|------|------|-------------|
| `com.unity.xr.openxr.picoxr` | 1.4.x | PICO device display/input/tracking/Enterprise camera API — PICO 设备显示/输入/追踪/Enterprise 相机 API | [PICO-Unity-OpenXR-SDK](https://github.com/Pico-Developer/PICO-Unity-OpenXR-SDK)（官方 GitHub，UPM 直接引用） |
| `com.unity.xr.openxr` | 1.10.0 | OpenXR runtime — OpenXR 运行时 | [Unity OpenXR](https://docs.unity3d.com/Packages/com.unity.xr.openxr@1.10/manual/index.html) |
| `com.unity.xr.management` | 4.6.0 | XR management — XR 管理 | Unity 官方包 |
| `com.unity.xr.hands` | 1.4.0 | Hand tracking — 手部追踪 | Unity 官方包 |
| `com.unity.ugui` | 1.0.0 | UI | Unity 官方包 |

> **About SDK download / 关于 SDK 下载**: `com.unity.xr.openxr.picoxr` is pulled from the official repo via UPM Git reference. If GitHub is not directly reachable, download the PICO Unity OpenXR SDK from the [PICO Developer Platform](https://developer.picoxr.com/) and replace the Git URL in the manifest with a local path. PICO device system requires **5.13.0+**.
>
> 说明：`com.unity.xr.openxr.picoxr` 通过 manifest 的 UPM Git 引用从官方仓库拉取。若你的网络无法直接访问 GitHub，可在 [PICO 开发者平台](https://developer.picoxr.com/) 下载 PICO Unity OpenXR SDK 后，替换 manifest 中的 Git URL 为本地路径。PICO 设备系统需 **5.13.0 及以上**。

---

## 3. Project Setup / 工程初始化

1. Open this directory (project root) with **Unity Hub**. — 用 **Unity Hub** 打开本目录（作为工程根目录）。
2. Unity resolves dependencies automatically on first open (XR Management, OpenXR, PICO OpenXR SDK) and generates `.meta` files. First resolution fetches the SDK online, which may be slow. — Unity 首次打开会自动解析依赖（XR Management、OpenXR、PICO OpenXR SDK），并为脚本生成 `.meta`。首次解析会联网拉取 SDK，较慢属正常。
3. If SDK fetch fails, configure network or a local path per Section 2. — 若 SDK 拉取失败，按第 2 节提示配置网络或本地路径。

> This project does **not** embed the PICO SDK (to keep the repo lean and avoid license bloat); the SDK is fetched on demand via the official UPM source.
>
> 本项目**不内嵌** PICO SDK（避免体积与版权冗余），SDK 通过官方 UPM 源按需拉取。

---

## 4. Key Configuration / 关键配置

- **XR Plugin Management**: `Project Settings > XR Plugin Management > Android` enable **OpenXR** and **PICO OpenXR**. Enabled features: **Hand Tracking, Body Tracking, Passthrough** (see `Assets/XR/Settings/OpenXR Package Settings.asset`). — `Project Settings > XR Plugin Management > Android` 勾选 **OpenXR** 与 **PICO OpenXR**。已启用特性：**Hand Tracking、Body Tracking、Passthrough**。
- **Passthrough**: `XRCameraTracker.Start()` sets the main camera `Clear Flags = Solid Color`, background `Alpha=0`, and enables `PassthroughFeature.EnableVideoSeeThrough` (guarded by `#if ENABLE_PICO_XR_SDK`). The collector sees the real world; UI hides during recording. — `XRCameraTracker.Start()` 自动设主相机 `Clear Flags = Solid Color`、背景 `Alpha=0`，并启用 `PassthroughFeature.EnableVideoSeeThrough`（`#if ENABLE_PICO_XR_SDK` 保护）。采集员看到真实世界，录制中 UI 自动隐藏。
- **IL2CPP Stripping guard (critical)**: `Assets/link.xml` configures `<assembly fullname="Assembly-CSharp" preserve="all"/>`. **Do not delete** — otherwise IL2CPP strips all dynamically-created scripts and the APK opens with no functionality. — `Assets/link.xml` 已配置 `<assembly fullname="Assembly-CSharp" preserve="all"/>`。**不可删除**——否则 IL2CPP 剥离所有动态创建的逻辑，APK 打开后无任何功能。
- **Player Settings**: package name `com.DefaultCompany.PicoMultiModalCapture` (changeable); camera permission required; PICO 4 Ultra Enterprise system (for4U + `getCameraInfo` auth for camera-calibration export). — 包名 `com.DefaultCompany.PicoMultiModalCapture`（可改）；需相机权限；PICO 4 Ultra Enterprise 系统（for4U + `getCameraInfo` 授权用于导出相机标定参数）。

---

## 5. Build APK / 构建 APK

### Method A: Editor menu — 编辑器菜单
Open `Assets/Scenes/Main.unity` (**must be Main.unity**, not the auto-generated CaptureScene), click `PICO Capture > Build APK`; output at `Build/PicoMultiModalCapture.apk`.
打开 `Assets/Scenes/Main.unity`（**必须是 Main.unity**，不是自动生成的 CaptureScene），点菜单 `PICO Capture > Build APK`，产物在 `Build/PicoMultiModalCapture.apk`。

### Method B: Command line — 命令行
```powershell
.\build_apk.ps1 -UnityPath "C:\Program Files\Unity\Hub\Editor\2022.3.62f3c1\Editor\Unity.exe"
```
Install: `adb install -r Build/PicoMultiModalCapture.apk` — 安装：`adb install -r Build/PicoMultiModalCapture.apk`

### Method C: Prebuilt APK (no Unity needed) — 直接安装预编译 APK（无需 Unity）
Download the prebuilt `PicoMultiModalCapture_*.apk` from **GitHub Releases**, then:
在本仓库的 **GitHub Releases** 页面下载预编译的 `PicoMultiModalCapture_*.apk`，然后：

```bash
adb install -r PicoMultiModalCapture_1.0.0.apk
```

> **Note**: the prebuilt APK uses Android default debug signing (not a release keystore); the device must allow "install from unknown sources". For official distribution, configure your own keystore and rebuild.
>
> **注意**：预编译 APK 使用 Android 默认 debug 签名（非发布签名），设备需允许"安装未知来源应用"。若需正式分发请配置自己的 keystore 后重新构建。

---

## 6. Usage / 使用流程

1. Wear the headset and ensure the 5 Motion Trackers are connected & calibrated. — 佩戴头显，确保 5 个 Motion Trackers 已连接并校准。
2. **Use the headset physical volume keys**: **"+" (VolumeUp) = Start**, **"−" (VolumeDown) = Stop**. No controller needed. — **用头显物理音量键控制录制**：**"+"（VolumeUp）= 开始录制**，**"−"（VolumeDown）= 停止录制**。无需手柄。
3. UI hides during recording (clean passthrough view); on stop, data is written to `Android/data/<package>/files/PicoMultiModalCapture/YYYYMMDD_HHmmss/`: — 录制中 UI 自动隐藏（干净透视画面）；停止后数据写入 `Android/data/<包名>/files/PicoMultiModalCapture/YYYYMMDD_HHmmss/`：
   - `video.mp4`: stereo SBS 2560×720 H.264 (60fps)
   - `data.json`: all-modality pose data (unified timestamps)
   - `data.csv`: wide table (head 7 + body 24×7 + hands 26×7×2)
   - `meta.json`: session + camera intrinsics/extrinsics/baseline + joint names (always exported)

> **Must wear the headset** before launch; otherwise PICO `seethrough.setting` steals the foreground and suspends the VR app — shown as "no logs/no functionality". This is a wearing issue, not IL2CPP stripping.
>
> **必须佩戴头显**再启动，否则 PICO `seethrough.setting` 抢占前台、VR 应用被挂起，表现为"无任何日志/功能"——这是佩戴问题，不是 IL2CPP 剥离。

---

## 7. Output Data Format / 导出数据格式

### meta.json (camera calibration — required for offline stereo/depth/pointcloud / 相机标定，离线立体/深度/点云必需)
```json
{
  "session": { "device": "PICO 4 Ultra Enterprise", "videoFps": 60, "videoWidth": 2560, "videoHeight": 720, "videoStereoLayout": "side-by-side", ... },
  "camera": {
    "available": true,
    "resolution": [1280, 720],
    "intrinsics": { "fx": 814.02, "fy": 610.55, "cx": 639.50, "cy": 359.50 },
    "baseline": 0.064,
    "left": { "position": [...], "rotation": [...] },
    "right": { "position": [...], "rotation": [...] }
  }
}
```
- `videoFps` is the **actual encoded frame rate** (~60 after Surface-direct). — `videoFps` 为**实际编码帧率**（Surface 直通后 ~60）。
- Intrinsics correspond to a single eye at 1280×720; baseline ≈ 6.4cm; extrinsics in the OpenXR local-floor frame. — 内参对应单眼 1280×720；基线约 6.4cm；外参为 OpenXR 局部地平面坐标系。
- Depth: `Z = fx·baseline/disparity`; point-cloud reprojection: `X=(u-cx)·Z/fx, Y=(v-cy)·Z/fy` (left-camera frame). — 深度：`Z = fx·baseline/disparity`；点云反投影：`X=(u-cx)·Z/fx, Y=(v-cy)·Z/fy`（左相机系）。
- **Distortion**: the for4U SDK **does not export lens distortion coefficients** (`GetCameraIntrinsicsfor4U` returns only `[cx,cy,fx,fy]`). For edge distortion, self-calibrate with a chessboard (`cv2.calibrateCamera`) then `undistort` + `stereoRectify`. — **畸变**：PICO for4U SDK **不导出镜头畸变系数**。边缘畸变需离线棋盘格自标定后 `undistort` + `stereoRectify`。

### data.json (unified timestamp `t` in seconds + `wallClock` UTC)
```json
{
  "meta": { "frameCount": ..., "durationSec": ..., "videoFps": 60, "bodyJointNames": [...24], "handJointNames": [...26] },
  "frames": [
    {
      "t": 0.0, "wallClock": "2026-08-07T...Z",
      "head":  { "position":[x,y,z], "rotation":[x,y,z,w], "confidence":1.0 },
      "body":  { "tracking": true, "confidence": 0.9, "joints":[ {"id":0,"name":"Pelvis","position":[..],"rotation":[..],"confidence":..}, ... ] },
      "hands": { "left": { "tracked": true, "scale":1.0, "joints":[ {"id":0,"name":"Wrist",...}, ... ] }, "right": { ... } }
    }
  ]
}
```
**Sync**: `CaptureManager.Update()` reads head/body/hands each sample frame (default 30Hz) using a shared high-precision `Stopwatch`; timestamps are naturally aligned. **Coordinate frame**: head/hand/body share the same OpenXR local-floor space (floor origin, Y up), directly aligned.

**同步**：`CaptureManager.Update()` 每采样帧（默认 30Hz）依次读头/身/手，共用高精度 `Stopwatch`，时间戳天然对齐。**坐标系**：head/hand/body 共享同一 OpenXR local-floor space（地平面原点，Y 向上），直接对齐。

---

## 8. Architecture Highlights / 架构要点

- **Stereo video (Surface-direct encode)**: for4U `PXRCaptureRenderMode._3D` outputs side-by-side 2560×720 (1280×720 per eye). `SurfaceEncoder.java` uses `MediaCodec.createInputSurface()` + `CameraRenderingPlugin.so` `startPreview(surface,_3D,2560,720)` so the camera renders straight into the encoder input Surface, bypassing CPU color conversion — 22fps → **60fps**. — **双目视频（Surface 直通硬编码）**：for4U `_3D` 模式输出左右并排 2560×720。`SurfaceEncoder.java` 用 MediaCodec 输入 Surface + `startPreview`，绕开 CPU 颜色转换，帧率 22fps → **60fps**。
- **Camera calibration**: `PICOFor4UCapture.FetchCameraParams()` uses `PXR_Enterprise.GetCameraParametersNewfor4U` to export intrinsics/extrinsics/baseline into meta.json. — **相机标定**：`PXR_Enterprise.GetCameraParametersNewfor4U` 导出内参/外参/基线，写 meta.json。
- **UI/Interaction**: scripts are created dynamically by `CaptureBootstrap` via `[RuntimeInitializeOnLoadMethod]` (no scene attachment); `link.xml` must be kept. — **UI/交互**：脚本由 `CaptureBootstrap` 用 `[RuntimeInitializeOnLoadMethod]` 动态创建，必须保留 `link.xml`。
- **Body tracking**: PICO OpenXR `BodyTrackingFeature`; with 5 MotionTrackers, 24 joints at confidence=1.0. — **身体追踪**：PICO OpenXR `BodyTrackingFeature`，5 个 MotionTracker 佩戴后可输出 24 关节 confidence=1.0。
- **Async export**: data is exported on a background thread on stop, keeping the main thread responsive (no stutter for long recordings). — **异步导出**：停止录制时后台线程导出，主线程即时响应。
- **Body-lost hint**: during recording, if body confidence is 0, a one-line hint shows at the bottom of view (does not affect the recorded video). — **身体丢失提示**：录制中检测到身体置信度为 0 时，视野底部显示一行提示（不影响录制画面）。

---

## 9. Known Limitations / 已知限制

- **No lens distortion coefficients**: SDK does not export them; self-calibrate with a chessboard. — **无镜头畸变系数**：SDK 不导出，需棋盘格自标定。
- **for4U FOV is fixed**: ~76°×61° (hardware optical, cannot be widened by SDK). The official "105° diagonal" is the **display FOV**, not the for4U capture FOV. — **for4U 相机 FOV 固定**：约 76°×61°（硬件决定）。官方"105° 对角线"是**显示 FOV**，非 for4U 采集 FOV。
- **iToF depth not exposed**: PICO 4 Ultra has an iToF depth camera, but the SDK provides no depth-data export; depth/point clouds use stereo disparity. — **iToF 深度不开放**：SDK 不提供深度数据导出；深度/点云需用双目视差。
- **for4U requires enterprise system**: consumer PICO 4 Ultra may not access the for4U camera. — **for4U 需企业系统**：普通消费版可能无法调用 for4U 相机。
- **60fps files are large**: `KEY_BIT_RATE = w·h·4` is adaptive; lower it for smaller files. — **60fps 文件较大**：`KEY_BIT_RATE` 自适应，如需更小体积可下调。

---

## 10. License / 许可证

MIT License (see [LICENSE](LICENSE)). Third-party dependencies (PICO SDK, etc.) belong to their respective owners; follow their license terms.
本项目采用 **MIT License**（见 [LICENSE](LICENSE)）。第三方依赖（PICO SDK 等）版权归其各自所有者，请遵守其许可条款。
