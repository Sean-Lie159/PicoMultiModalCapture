# _process_sample.ps1 — 对单个样例文件夹运行完整处理管线（脚本支持 --input-dir）
# 用法: powershell -ExecutionPolicy Bypass -File scripts\_process_sample.ps1 -SampleDir "<绝对路径>" [-SkipDepth]
param(
    [Parameter(Mandatory=$true)][string]$SampleDir,
    [switch]$SkipDepth
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root

Write-Host "== [run] $SampleDir =="
& $Py scripts\01_parse_data.py --input-dir $SampleDir
if ($LASTEXITCODE -ne 0) { throw "01 failed" }
& $Py scripts\02_build_lerobot.py --input-dir $SampleDir
if ($LASTEXITCODE -ne 0) { throw "02 failed" }
if ($SkipDepth) {
    Write-Host "== [skip] 03 depth_pointcloud =="
} else {
    & $Py scripts\03_depth_pointcloud.py --input-dir $SampleDir --workers 8
    if ($LASTEXITCODE -ne 0) { throw "03 failed" }
}
& $Py scripts\04_skeleton_viz.py --input-dir $SampleDir --view front
if ($LASTEXITCODE -ne 0) { throw "04 failed" }
& $Py scripts\06_visualize.py --input-dir $SampleDir
if ($LASTEXITCODE -ne 0) { throw "06 failed" }
Write-Host "SAMPLE DONE: $SampleDir"
