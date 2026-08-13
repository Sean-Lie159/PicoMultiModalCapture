# 一键构建 PICO 4 Ultra APK（需已安装 Unity 且工程已导入 PICO Unity OpenXR SDK）。
# 用法：在 unity/PicoMultiModalCapture 目录下运行  .\build_apk.ps1
param(
    [string]$UnityPath = "C:\Program Files\Unity\Hub\Editor\2022.3.62f3c1\Editor\Unity.exe",
    [string]$ProjectPath = (Get-Location).Path
)

if (-not (Test-Path $UnityPath)) {
    Write-Error "未找到 Unity 可执行文件: $UnityPath 。请通过 -UnityPath 参数指定。"
    exit 1
}

Write-Host "开始构建 APK ..."
& "$UnityPath" -batchmode -quit -projectPath "$ProjectPath" `
    -executeMethod PicoMultiModalCapture.BuildAPK.Build `
    -buildTarget Android -logFile build.log

if ($LASTEXITCODE -eq 0) {
    Write-Host "构建完成，产物位于 Build/PicoMultiModalCapture.apk"
} else {
    Write-Error "构建失败，请查看 build.log"
}
