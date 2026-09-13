$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path $python)) { throw 'Bundled Python runtime not found.' }
$out = Join-Path $root 'src-tauri\binaries'
New-Item -ItemType Directory -Path $out -Force | Out-Null
& $python -m pip install pyinstaller
& $python -m PyInstaller --noconfirm --clean --onefile --name meeting-scribe-engine (Join-Path $root 'InterviewScribe\launch.py')
$target = Join-Path $out 'meeting-scribe-engine-x86_64-pc-windows-msvc.exe'
Copy-Item (Join-Path $root 'dist\meeting-scribe-engine.exe') $target -Force
