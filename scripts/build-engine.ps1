$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$python = if (Test-Path $bundledPython) { $bundledPython } else { 'python' }
$pythonDir = Split-Path -Parent (& $python -c "import sys; print(sys.executable)")
$pythonStableDll = Join-Path $pythonDir 'python3.dll'
$out = Join-Path $root 'src-tauri\binaries'
New-Item -ItemType Directory -Path $out -Force | Out-Null
Set-Location $root
& $python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
}
& $python -m PyInstaller --noconfirm --clean --onefile --name hearnotes-engine `
    --add-binary "$pythonStableDll;." `
    --exclude-module faster_whisper --exclude-module ctranslate2 --exclude-module av `
    --exclude-module sherpa_onnx `
    (Join-Path $root 'HearNotes\launch.py')
if ($LASTEXITCODE -ne 0) { throw 'Engine build failed; refusing to bundle an older engine.' }
$target = Join-Path $out 'hearnotes-engine-x86_64-pc-windows-msvc.exe'
Copy-Item (Join-Path $root 'dist\hearnotes-engine.exe') $target -Force
