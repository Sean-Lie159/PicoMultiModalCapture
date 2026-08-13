#!/usr/bin/env bash
# 一键构建 PICO 4 Ultra APK（macOS/Linux，需已安装 Unity 且工程已导入 PICO Unity OpenXR SDK）。
# 用法：在 unity/PicoMultiModalCapture 目录下运行  bash build_apk.sh
set -e

UNITY_PATH="${UNITY_PATH:-/Applications/Unity/Hub/Editor/2022.3.21f1/Unity.app/Contents/MacOS/Unity}"
PROJECT_PATH="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$UNITY_PATH" ]; then
  echo "未找到 Unity 可执行文件: $UNITY_PATH 。请通过环境变量 UNITY_PATH 指定。"
  exit 1
fi

echo "开始构建 APK ..."
"$UNITY_PATH" -batchmode -quit -projectPath "$PROJECT_PATH" \
  -executeMethod PicoMultiModalCapture.BuildAPK.Build \
  -buildTarget Android -logFile build.log

echo "构建完成，产物位于 Build/PicoMultiModalCapture.apk"
