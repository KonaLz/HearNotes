$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$python = if (Test-Path $bundledPython) { $bundledPython } else { 'python' }
$out = Join-Path $root 'src-tauri\binaries'
New-Item -ItemType Directory -Path $out -Force | Out-Null
& $python -m pip install pyinstaller
& $python -m PyInstaller --noconfirm --clean --onefile --name meeting-scribe-engine (Join-Path $root 'MeetingScribe\launch.py')
$target = Join-Path $out 'meeting-scribe-engine-x86_64-pc-windows-msvc.exe'
Copy-Item (Join-Path $root 'dist\meeting-scribe-engine.exe') $target -Force
