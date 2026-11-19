# Build HyperGet for Windows on your own PC, the same way the GitHub Actions build does.
#
# Needs: Windows 10/11, Python 3.12 (python.org, tick "Add to PATH"), Inno Setup 6
# (jrsoftware.org/isdl.php). Run from the repo folder in PowerShell:
#
#   powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1
#
# Output in dist\:  HyperGet-Setup-<version>.exe, HyperGet-portable-<version>.zip and
# the extension zips. Attach those to a GitHub release (tag v<version>).

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$version = (python -c "import hypeget; print(hypeget.__version__)").Trim()
Write-Host "== Building HyperGet $version" -ForegroundColor Cyan

Write-Host "== Installing build tools"
python -m pip install --upgrade pip
python -m pip install . yt-dlp pyinstaller pytest

Write-Host "== Running tests"
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
if (-not (Test-Path hypeget\store_ids.json)) {
  # Store IDs for the browser helper; empty until the stores assign them.
  '{"chrome": "", "edge": ""}' | Set-Content -Encoding ascii hypeget\store_ids.json
}

Write-Host "== HyperGet.exe"
pyinstaller --noconfirm --clean --windowed --name HyperGet --icon packaging/hypeget.ico `
  --add-data "hypeget/ui;hypeget/ui" --add-data "hypeget/store_ids.json;hypeget" `
  --collect-submodules yt_dlp --collect-submodules pystray --collect-all webview packaging/launcher.py

Write-Host "== HyperGet-NativeHost.exe (browser helper)"
pyinstaller --noconfirm --onefile --console --name HyperGet-NativeHost --icon packaging/hypeget.ico `
  --distpath build\host packaging/native_host_launcher.py
Copy-Item build\host\HyperGet-NativeHost.exe dist\HyperGet\

Write-Host "== FFmpeg"
$zip = Join-Path $env:TEMP "hyperget-ffmpeg.zip"
Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -OutFile $zip
$ff = Join-Path $env:TEMP "hyperget-ffmpeg"
Remove-Item -Recurse -Force $ff -ErrorAction SilentlyContinue
Expand-Archive $zip $ff
Copy-Item (Get-ChildItem $ff -Recurse -Filter ffmpeg.exe | Select-Object -First 1).FullName dist\HyperGet\ffmpeg.exe

Write-Host "== Browser extension"
python tools/build_extension.py
Expand-Archive (Get-ChildItem dist\extension\*-full.zip | Select-Object -First 1).FullName dist\HyperGet\extension
Copy-Item README.md dist\HyperGet\README.md

Write-Host "== Checking the build"
$env:HYPEGET_HOME = Join-Path $env:TEMP "hyperget-check"
Remove-Item -Recurse -Force $env:HYPEGET_HOME -ErrorAction SilentlyContinue
$p = Start-Process dist\HyperGet\HyperGet.exe -ArgumentList "--headless", "--port", "52999" -PassThru
$ok = $false
for ($i = 0; $i -lt 30 -and -not $ok; $i++) {
  Start-Sleep 1
  try {
    $r = Invoke-RestMethod http://127.0.0.1:52999/api/state -Headers @{ "X-HyperGet" = "1" }
    if ($r.features.ffmpeg -and $r.features.sites) { $ok = $true }
  } catch {}
}
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Remove-Item Env:\HYPEGET_HOME
if (-not $ok) { throw "HyperGet.exe did not start correctly (UI, FFmpeg or yt-dlp missing)" }

Write-Host "== Portable zip"
Compress-Archive -Path dist\HyperGet -DestinationPath "dist\HyperGet-portable-$version.zip"

Write-Host "== Installer"
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found. Install it from jrsoftware.org/isdl.php" }
& $iscc "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }

Write-Host ""
Write-Host "Done. Attach these to the GitHub release v$($version):" -ForegroundColor Green
Get-ChildItem dist\HyperGet-Setup-*.exe, dist\HyperGet-portable-*.zip, dist\extension\*.zip | ForEach-Object { "  $($_.FullName)" }
