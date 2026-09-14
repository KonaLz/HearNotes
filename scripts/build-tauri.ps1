$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$nodeRoot = "$env:USERPROFILE\.cache\hearnotes-node\node-v22.14.0-win-x64"
$cargoRoot = "$env:USERPROFILE\.cache\hearnotes-cargo\bin"
$vsDevCmd = "C:\BuildTools\Common7\Tools\VsDevCmd.bat"

if (!(Test-Path "$nodeRoot\node.exe")) {
    throw "找不到 Node.js：$nodeRoot"
}

if (!(Test-Path "$cargoRoot\cargo.exe")) {
    throw "找不到 Cargo：$cargoRoot"
}

if (!(Test-Path $vsDevCmd)) {
    throw "找不到 Visual Studio 编译环境：$vsDevCmd"
}

$pathPrefix = "$cargoRoot;$nodeRoot;$nodeRoot\node_modules\npm\bin"

$command = "`"$vsDevCmd`" -arch=x64 -host_arch=x64 && set `"PATH=$pathPrefix;%PATH%`" && cd /d `"$root`" && npm run tauri:build:direct"

cmd.exe /d /s /c $command

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}