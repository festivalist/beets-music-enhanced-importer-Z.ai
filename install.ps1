# musik installer: Python check, venv, dependencies, fpcalc, setup wizard.
# Run via install.bat (or: powershell -ExecutionPolicy Bypass -File install.ps1)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

$FpcalcUrl = "https://github.com/acoustid/chromaprint/releases/download/v1.5.1/chromaprint-fpcalc-1.5.1-windows-x86_64.zip"
$MinPython = [version]"3.10"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }

function Test-PythonVersion($exe, $args) {
    try {
        $out = & $exe @args -c "import sys; print('OK', '%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $line = ($out | Select-Object -Last 1)
        if ($line -notmatch "OK (\d+\.\d+)") { return $null }
        return [version]$Matches[1]
    } catch { return $null }
}

# --- 1. Find or install Python --------------------------------------------
Write-Step "Looking for Python >= $MinPython"

$python = $null
$candidates = @(
    @{ exe = "py";      args = @("-3") },
    @{ exe = "python";  args = @() },
    @{ exe = "python3"; args = @() }
)
foreach ($cand in $candidates) {
    $cmd = Get-Command $cand.exe -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    # Skip the Microsoft Store alias stub.
    if ($cmd.Source -like "*WindowsApps*") { continue }
    $ver = Test-PythonVersion $cmd.Source $cand.args
    if ($ver -and $ver -ge $MinPython) {
        $python = @{ exe = $cmd.Source; args = $cand.args; version = $ver }
        break
    }
}

if (-not $python) {
    Write-Host "    no suitable Python found - trying winget install (Python 3.12)"
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        & winget install -e --id Python.Python.3.12 --scope user `
            --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { throw "winget Python install failed - install Python 3.10+ manually from https://www.python.org/downloads/" }
        # Refresh PATH for this session.
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
        foreach ($cand in $candidates) {
            $cmd = Get-Command $cand.exe -ErrorAction SilentlyContinue
            if (-not $cmd -or $cmd.Source -like "*WindowsApps*") { continue }
            $ver = Test-PythonVersion $cmd.Source $cand.args
            if ($ver -and $ver -ge $MinPython) {
                $python = @{ exe = $cmd.Source; args = $cand.args; version = $ver }
                break
            }
        }
    }
    if (-not $python) {
        throw "Python $MinPython or newer is required. Install it from https://www.python.org/downloads/ (check 'Add to PATH') and re-run install.bat."
    }
}
Write-Ok "using Python $($python.version) ($($python.exe))"

# --- 2. Virtual environment + dependencies ---------------------------------
Write-Step "Creating virtual environment (.venv)"
& $python.exe @($python.args) -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
$PyExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"

Write-Step "Installing dependencies (beets and friends)"
& $PyExe -m pip install --upgrade pip --quiet
& $PyExe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
Write-Ok "dependencies installed"

# --- 2b. Deno (yt-dlp needs it for some YouTube videos; without it those
#         fail with sporadic "YT-DLP download error") ------------------------
Write-Step "Downloading Deno runtime (for spotDL/SomeDL YouTube downloads)"
& $PyExe -m spotdl --download-deno
if ($LASTEXITCODE -ne 0) {
    Write-Host "    WARNING: Deno download failed - some YouTube tracks may fail." -ForegroundColor Yellow
} else {
    Write-Ok "Deno installed (into %USERPROFILE%\.spotdl)"
}

# --- 3. fpcalc (acoustic fingerprinter for the chroma plugin) ---------------
$FpcalcExe = Join-Path $ProjectDir "bin\fpcalc.exe"
if (Test-Path $FpcalcExe) {
    Write-Step "fpcalc already present"
} else {
    Write-Step "Downloading fpcalc (chromaprint 1.5.1)"
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir "bin") | Out-Null
    $zip = Join-Path $env:TEMP "chromaprint-fpcalc.zip"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $FpcalcUrl -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath (Join-Path $env:TEMP "chromaprint-fpcalc") -Force
        $exe = Get-ChildItem (Join-Path $env:TEMP "chromaprint-fpcalc") -Recurse -Filter "fpcalc.exe" | Select-Object -First 1
        Copy-Item $exe.FullName $FpcalcExe
        Remove-Item $zip -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $env:TEMP "chromaprint-fpcalc") -Recurse -Force -ErrorAction SilentlyContinue
        Write-Ok "fpcalc installed to bin\fpcalc.exe"
    } catch {
        Write-Host "    WARNING: fpcalc download failed ($($_.Exception.Message))" -ForegroundColor Yellow
        Write-Host "    Acoustic fingerprinting (chroma) is disabled; everything else works." -ForegroundColor Yellow
    }
}

# --- 3b. flac (decode tests for `musik doctor` bitrot checks) ----------------
$FlacUrl = "https://github.com/xiph/flac/releases/download/1.5.0/flac-1.5.0-win.zip"
$FlacExe = Join-Path $ProjectDir "bin\flac.exe"
if (Test-Path $FlacExe) {
    Write-Step "flac already present"
} else {
    Write-Step "Downloading flac (1.5.0, for `musik doctor` bitrot checks)"
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir "bin") | Out-Null
    $zip = Join-Path $env:TEMP "flac-win.zip"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $FlacUrl -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath (Join-Path $env:TEMP "flac-win") -Force
        # flac.exe links dynamically — the DLL must sit next to it
        foreach ($name in @("flac.exe", "libFLAC.dll", "libFLAC++.dll")) {
            $f = Get-ChildItem (Join-Path $env:TEMP "flac-win") -Recurse -Filter $name |
                Where-Object { $_.Directory.Name -eq "Win64" } | Select-Object -First 1
            if ($f) { Copy-Item $f.FullName (Join-Path $ProjectDir "bin\$name") }
        }
        Remove-Item $zip -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $env:TEMP "flac-win") -Recurse -Force -ErrorAction SilentlyContinue
        Write-Ok "flac installed to bin\flac.exe"
    } catch {
        Write-Host "    WARNING: flac download failed ($($_.Exception.Message))" -ForegroundColor Yellow
        Write-Host "    `musik doctor` will skip FLAC bitrot checks; everything else works." -ForegroundColor Yellow
    }
}

# --- 3c. ffmpeg (replaygain loudness tags via the ffmpeg backend) ------------
$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$FfmpegExe = Join-Path $ProjectDir "bin\ffmpeg.exe"
if (Test-Path $FfmpegExe) {
    Write-Step "ffmpeg already present"
} else {
    Write-Step "Downloading ffmpeg (essentials build, for ReplayGain tags)"
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir "bin") | Out-Null
    $zip = Join-Path $env:TEMP "ffmpeg-essentials.zip"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $FfmpegUrl -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath (Join-Path $env:TEMP "ffmpeg-essentials") -Force
        $exe = Get-ChildItem (Join-Path $env:TEMP "ffmpeg-essentials") -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
        Copy-Item $exe.FullName $FfmpegExe
        Remove-Item $zip -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $env:TEMP "ffmpeg-essentials") -Recurse -Force -ErrorAction SilentlyContinue
        Write-Ok "ffmpeg installed to bin\ffmpeg.exe"
    } catch {
        Write-Host "    WARNING: ffmpeg download failed ($($_.Exception.Message))" -ForegroundColor Yellow
        Write-Host "    ReplayGain is disabled; remove 'replaygain' from config plugins to silence the warning." -ForegroundColor Yellow
    }
}

# --- 4. Setup wizard (writes config.yaml for this machine) -------------------
if (Test-Path (Join-Path $ProjectDir "config.yaml")) {
    Write-Step "config.yaml already exists - keeping it (re-run 'musik setup' to regenerate)"
} else {
    Write-Step "Setup wizard: choose your music library root and (optionally) a Discogs token"
    & $PyExe musik.py setup
    if ($LASTEXITCODE -ne 0) {
        throw "setup wizard failed (exit code $LASTEXITCODE) - run '.venv\Scripts\python.exe musik.py setup' manually to see the error."
    }
}

# --- 5. Done ------------------------------------------------------------------
Write-Step "Ready. Usage (from this folder):"
Write-Host @"

  musik.bat scan --root "C:\path\to\incoming music"
  musik.bat import --dry-run --unit "C:\path\to\incoming music"
  musik.bat import --unit "C:\path\to\incoming music"
  musik.bat asis --unit "C:\path\to\incoming music"      (optional, see README)
  musik.bat report --verify

Reports land in reports\, finished albums in your library root.
Read README.md for the full workflow, review.csv handling and tuning.
"@ -ForegroundColor White
