# Install MIDIVOLT Windows RC (requires an existing Python 3.11).
# No downloads without -AllowNetwork. Install only into a NEW environment.
[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $env:LOCALAPPDATA "MIDIVOLT\venv-0.1.0rc1"),
    [switch]$AllowNetwork,
    [string]$Wheelhouse
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([bool]$AllowNetwork -eq [bool]$Wheelhouse) {
    throw "Choose exactly one dependency source: -AllowNetwork OR -Wheelhouse <folder>."
}
$wheels = @(Get-ChildItem -LiteralPath $PSScriptRoot -File -Filter "midivolt-*.whl")
if ($wheels.Count -ne 1) {
    throw "The extracted RC package must contain exactly one MIDIVOLT wheel."
}
$destinationFull = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $destinationFull) {
    throw "The destination already exists. Refusing to overwrite: $destinationFull"
}
if ($Wheelhouse) {
    $sourceDir = [IO.Path]::GetFullPath($Wheelhouse)
    if (-not (Test-Path -LiteralPath $sourceDir -PathType Container)) {
        throw "Offline wheelhouse directory does not exist: $sourceDir"
    }
}
$pythonLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
if (-not $pythonLauncher) {
    throw "Install trusted Python 3.11 (with py.exe launcher) before installing MIDIVOLT."
}
& $pythonLauncher.Source -3.11 -c "import sys; assert sys.version_info[:2] == (3,11)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11 was not found by the Windows Python Launcher."
}
$parent = Split-Path -Parent $destinationFull
New-Item -ItemType Directory -Path $parent -Force | Out-Null

# Create first, then install from the single wheel; no administrative privileges.
& $pythonLauncher.Source -3.11 -m venv $destinationFull
if ($LASTEXITCODE -ne 0) { throw "Failed to create the virtual environment." }
$python = Join-Path $destinationFull "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Venv Python executable missing." }
$pipArgs = @("-m", "pip", "install", "--no-input", "--disable-pip-version-check")
if ($Wheelhouse) {
    $pipArgs += @("--no-index", "--find-links", $sourceDir)
} else {
    Write-Host "Network consent: pip will download MIDIVOLT's dependencies from configured package indexes."
}
$pipArgs += @($wheels[0].FullName)
& $python @pipArgs
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed. Inspect the partial new environment: $destinationFull"
}

# Run offline smoke immediately; no pretrained model or Cubase is invoked.
$smokeScript = Join-Path $PSScriptRoot "Smoke-MIDIVOLT.ps1"
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $smokeScript -PythonExe $python
if ($LASTEXITCODE -ne 0) {
    throw "MIDIVOLT smoke failed. Do not use this RC until investigated."
}
Write-Host "MIDIVOLT 0.1.0rc1 ready: $destinationFull"
Write-Host "Launch with: $destinationFull\Scripts\midivolt.exe --help"
Write-Host "This is a CLI developer RC, not a GUI/VST3 or packaged model."
