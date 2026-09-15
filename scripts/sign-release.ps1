param([string]$KeyPath = '')
$ErrorActionPreference = 'Stop'

# Resolve paths relative to the project, so the script works from any directory.
$root = Split-Path -Parent $PSScriptRoot
$utf8 = New-Object System.Text.UTF8Encoding($false)
$config = [IO.File]::ReadAllText((Join-Path $root 'src-tauri/tauri.conf.json')) | ConvertFrom-Json
$package = [IO.File]::ReadAllText((Join-Path $root 'package.json')) | ConvertFrom-Json
$version = $config.version
if ($version -ne $package.version) { throw 'Package and Tauri versions differ.' }
$fileName = "HearNotes_${version}_x64-setup.exe"
$installer = Join-Path $root "src-tauri/target/release/bundle/nsis/$fileName"
$notesPath = Join-Path $root "release/v$version.md"
if (!$KeyPath) { $KeyPath = Join-Path $root '.signing/hearnotes-updater.key' }
foreach ($path in @($installer, $notesPath, $KeyPath)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
}
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) { $node = $node.Source }
else { $node = Join-Path $env:USERPROFILE '.cache/hearnotes-node/node-v22.14.0-win-x64/node.exe' }
$cli = Join-Path $root 'node_modules/@tauri-apps/cli/tauri.js'
if (!(Test-Path $node) -or !(Test-Path $cli)) { throw 'Node.js or local Tauri CLI is missing. Install project dependencies first.' }

# Sign using the existing key. An encrypted key uses the Tauri password prompt
# or TAURI_SIGNING_PRIVATE_KEY_PASSWORD; never write the password into this file.
$signArgs = @('signer', 'sign', '-f', $KeyPath)
if (!$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD) {
    # Windows PowerShell needs quoted empty text to pass an empty native argument.
    $signArgs += @('--password', '""')
}
& $node $cli @signArgs $installer
if ($LASTEXITCODE -ne 0) { throw 'Signing failed; latest.json was not changed.' }
$signature = [IO.File]::ReadAllText("$installer.sig").Trim()

# Reject an accidental different signing key before publishing its metadata.
function Get-KeyId([string]$encoded) {
    $lines = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded)) -split '\r?\n'
    $bytes = [Convert]::FromBase64String($lines[1])
    return [BitConverter]::ToString($bytes[2..9])
}
if ((Get-KeyId $signature) -ne (Get-KeyId $config.plugins.updater.pubkey)) {
    throw 'Signing key ID does not match the application public key; latest.json was not changed.'
}

# Build the update feed from this version's bilingual release notes.
$manifest = [ordered]@{
    version = $version
    notes = [IO.File]::ReadAllText($notesPath).Trim()
    pub_date = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    platforms = @{
        'windows-x86_64' = @{
            signature = $signature
            url = "https://github.com/KonaLz/HearNotes/releases/download/v$version/$fileName"
        }
    }
}
$target = Join-Path $root 'release/latest.json'
$temporary = "$target.tmp"
try {
    [IO.File]::WriteAllText($temporary, ($manifest | ConvertTo-Json -Depth 6), $utf8)
    Move-Item -LiteralPath $temporary -Destination $target -Force
} finally {
    if (Test-Path $temporary) { Remove-Item -LiteralPath $temporary }
}
Write-Host "Ready: $installer.sig"
Write-Host "Ready: $target"
Write-Host 'Upload the EXE, its SIG, and latest.json to the same GitHub release.'
