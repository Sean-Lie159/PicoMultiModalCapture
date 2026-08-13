# PICO MultiModal Capture — PICO 4 Ultra 多模态同步录制（双目 SBS · 60fps）

在 **PICO 4 Ultra** 上同步采集四类数据，以**统一时间戳**导出到设备本地，供离线做**多模态分析 / 双目立体 / 深度重建 / 点云**。

- 头部 6DoF 位姿（位置 + 四元数）
- **双目第一人称 RGB 视频**（PICO Enterprise for4U 双 RGB 相机，side-by-side 2560×720，Surface 直通硬编码 **60fps**）
- 全身 24 关键点骨骼（PICO Motion Trackers + Body Tracking）
- 双手各 26 关键点姿态（PICO Hand Tracking）

> 应用运行于 MR/Passthrough 模式，采集员佩戴头显看到真实世界透视画面执行数采。所录视频为 **for4U 双 RGB 相机的真实世界画面**（非 Unity 主相机渲染），左右并排（SBS）单流 MP4，配合 `meta.json` 的相机内参/外参/基线，可离线做 **双目视差 → 深度 → 点云**（`Z = fx·baseline/disparity`）。

---

## 1. 环境要求

- **Unity 2022.3 LTS**（已验证 2022.3.62f3c1），安装模块：`Android Build Support`、`OpenJDK`、`Android SDK & NDK Tools`。
- **Android API 34** 编译目标；`Scripting Backend = IL2CPP`；`Target Architectures = ARM64`。
- 一台 **PICO 4 Ultra Enterprise**（for4U 相机需企业系统 + `getCameraInfo` 授权）+ 5 个 **PICO Motion Trackers**（已配对校准）。

---

## 2. 用到的 SDK（依赖说明）

本项目基于以下 SDK，均在 `Packages/manifest.json` 中声明，**打开工程时由 Unity Package Manager 自动拉取**（无需手动下载）：

| 包名 | 版本 | 用途 | 来源 / 下载 |
|------|------|------|-------------|
| `com.unity.xr.openxr.picoxr` | 1.4.x | PICO 设备显示/输入/追踪/Enterprise 相机 API | [PICO-Unity-OpenXR-SDK](https://github.com/Pico-Developer/PICO-Unity-OpenXR-SDK)（官方 GitHub，UPM 直接引用） |
| `com.unity.xr.openxr` | 1.10.0 | OpenXR 运行时 | [Unity OpenXR](https://docs.unity3d.com/Packages/com.unity.xr.openxr@1.10/manual/index.html) |
| `com.unity.xr.management` | 4.6.0 | XR 管理 | Unity 官方包 |
| `com.unity.xr.hands` | 1.4.0 | 手部追踪 | Unity 官方包 |
| `com.unity.ugui` | 1.0.0 | UI | Unity 官方包 |

> **关于 SDK 下载**：`com.unity.xr.openxr.picoxr` 通过 manifest 的 UPM Git 引用从官方仓库拉取。若你的网络无法直接访问 GitHub，可在 [PICO 开发者平台](https://developer.picoxr.com/) 下载 PICO Unity OpenXR SDK 后，替换 manifest 中的 Git URL 为本地路径。PICO 设备系统需 **5.13.0 及以上**。

---

## 3. 工程初始化

1. 用 **Unity Hub** 打开本目录（作为工程根目录）。
2. Unity 首次打开会自动解析依赖（XR Management、OpenXR、PICO OpenXR SDK），并为脚本生成 `.meta`。首次解析会联网拉取 SDK，较慢属正常。
3. 若 SDK 拉取失败，按第 2 节提示配置网络或本地路径。

> 本项目**不内嵌** PICO SDK（避免体积与版权冗余），SDK 通过官方 UPM 源按需拉取。

---

## 4. 关键配置（务必确认）

- **XR Plugin Management**：`Project Settings > XR Plugin Management > Android` 勾选 **OpenXR** 与 **PICO OpenXR**。已启用特性：**Hand Tracking、Body Tracking、Passthrough**（见 `Assets/XR/Settings/OpenXR Package Settings.asset`）。
- **Passthrough（透视）**：`XRCameraTracker.Start()` 自动设主相机 `Clear Flags = Solid Color`、背景 `Alpha=0`，并启用 `PassthroughFeature.EnableVideoSeeThrough`（`#if ENABLE_PICO_XR_SDK` 保护）。采集员看到真实世界，录制中 UI 自动隐藏。
- **IL2CPP Stripping 防护（关键）**：`Assets/link.xml` 已配置 `<assembly fullname="Assembly-CSharp" preserve="all"/>`。**不可删除**——否则 `[RuntimeInitializeOnLoadMethod]` 动态创建的所有逻辑会被剥离，APK 打开后无任何功能。
- **Player Settings**：包名 `com.DefaultCompany.PicoMultiModalCapture`（可改）；需相机权限；PICO 4 Ultra Enterprise 系统（for4U + `getCameraInfo` 授权用于导出相机标定参数）。

---

## 5. 构建 APK

### 方式 A：编辑器菜单
打开 `Assets/Scenes/Main.unity`（**必须是 Main.unity**，不是自动生成的 CaptureScene），点菜单 `PICO Capture > Build APK`，产物在 `Build/PicoMultiModalCapture.apk`。

### 方式 B：命令行
```powershell
.\build_apk.ps1 -UnityPath "C:\Program Files\Unity\Hub\Editor\2022.3.62f3c1\Editor\Unity.exe"
```

安装：`adb install -r Build/PicoMultiModalCapture.apk`

### 方式 C：直接安装预编译 APK（无需 Unity）

在本仓库的 **GitHub Releases** 页面下载预编译的 `PicoMultiModalCapture_*.apk`，然后：

```bash
adb install -r PicoMultiModalCapture_1.0.0.apk
```

> **注意**：预编译 APK 使用 Android 默认 debug 签名（非发布签名），设备需允许"安装未知来源应用"。若需正式分发请按第 5 节配置自己的 keystore 后重新构建。

---

## 6. 使用流程

1. 佩戴头显，确保 5 个 Motion Trackers 已连接并校准。
2. **用头显物理音量键控制录制**：**"+"（VolumeUp）= 开始录制**，**"−"（VolumeDown）= 停止录制**。无需手柄。
3. 录制中 UI 自动隐藏（干净透视画面）；停止后数据写入 `Android/data/<包名>/files/PicoMultiModalCapture/YYYYMMDD_HHmmss/`：
   - `video.mp4`：双目 SBS 2560×720 H.264（60fps）
   - `data.json`：全模态姿态数据（统一时间戳）
   - `data.csv`：宽表（头 7 列 + 身体 24×7 + 双手 26×7×2）
   - `meta.json`：会话 + 相机内参/外参/基线 + 骨骼关节名（始终导出）

> **必须佩戴头显**再启动，否则 PICO `seethrough.setting` 抢占前台、VR 应用被挂起，表现为"无任何日志/功能"——这是佩戴问题，不是 IL2CPP 剥离。

---

## 7. 导出数据格式

### meta.json（相机标定，离线立体/深度/点云必需）
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
- `videoFps` 为**实际编码帧率**（Surface 直通后 ~60）。
- 内参对应单眼 1280×720；基线约 6.4cm；外参为 OpenXR 局部地平面坐标系。
- 深度：`Z = fx·baseline/disparity`；点云反投影：`X=(u-cx)·Z/fx, Y=(v-cy)·Z/fy`（左相机系）。
- **畸变**：PICO for4U SDK **不导出镜头畸变系数**（`GetCameraIntrinsicsfor4U` 仅返回 `[cx,cy,fx,fy]`）。边缘畸变需离线棋盘格自标定（`cv2.calibrateCamera`）后 `undistort` + `stereoRectify`。

### data.json（统一时间戳 `t` 秒 + `wallClock` UTC）
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
**同步**：`CaptureManager.Update()` 每采样帧（默认 30Hz）依次读头/身/手，共用 `Stopwatch` 高精度时钟，时间戳天然对齐。**坐标系**：head/hand/body 共享同一 OpenXR local-floor space（地平面原点，Y 向上），直接对齐。

---

## 8. 架构要点

- **双目视频（Surface 直通硬编码）**：for4U `PXRCaptureRenderMode._3D` 输出左右并排 2560×720（每眼 1280×720）。`SurfaceEncoder.java` 用 `MediaCodec.createInputSurface()` + `CameraRenderingPlugin.so` 的 `startPreview(surface,_3D,2560,720)`，让相机画面直接渲染到编码器输入 Surface，绕开 CPU 颜色转换，帧率 22fps → **60fps**。
- **相机标定**：`PICOFor4UCapture.FetchCameraParams()` 用 `PXR_Enterprise.GetCameraParametersNewfor4U` 导出内参/外参/基线，写 meta.json。
- **UI/交互**：脚本由 `CaptureBootstrap` 用 `[RuntimeInitializeOnLoadMethod]` 动态创建（不挂场景），必须保留 `link.xml`。
- **身体追踪**：PICO OpenXR `BodyTrackingFeature`，5 个 MotionTracker 佩戴后可输出 24 关节 confidence=1.0。
- **异步导出**：停止录制时后台线程导出数据，主线程即时响应 UI（长时间录制不卡顿）。
- **身体丢失提示**：录制中检测到身体置信度为 0 时，视野底部显示一行提示（不影响录制画面）。

---

## 9. 已知限制

- **无镜头畸变系数**：SDK 不导出，需棋盘格自标定。
- **for4U 相机 FOV 固定**：约 76°×61°（硬件光学决定，SDK 无法扩大）。官方"105° 对角线"是**显示 FOV**，非 for4U 采集相机 FOV。
- **iToF 深度不开放**：PICO 4 Ultra 硬件有 iToF 深度相机，但 SDK 不提供深度数据导出接口；深度/点云需用双目视差。
- **for4U 需企业系统**：普通消费版 PICO 4 Ultra 可能无法调用 for4U 相机。
- **60fps 文件较大**：`KEY_BIT_RATE = w·h·4` 自适应，如需更小体积可下调。

---

## 10. 许可证

本项目采用 **MIT License**（见 [LICENSE](LICENSE)）。第三方依赖（PICO SDK 等）版权归其各自所有者，请遵守其许可条款。
