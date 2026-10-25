# Portable offline CLI smoke: run on installed Windows venv.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$PythonExe)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "An installed virtual environment Python executable is required."
}
$scripts = Split-Path -Parent ([IO.Path]::GetFullPath($PythonExe))
function Invoke-CLI([string]$Name, [string[]]$Arguments) {
    $exe = Join-Path $scripts "$Name.exe"
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "Missing console script: $exe"
    }
    & $exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name exited with code $LASTEXITCODE"
    }
}
$folder = Join-Path ([IO.Path]::GetTempPath()) ("MIDIVOLT-RC-SMOKE-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $folder | Out-Null
try {
    $source = Join-Path $folder "source.mid"
    $candidate = Join-Path $folder "candidate.mid"
    $manifest = Join-Path $folder "proposal.json"
    $approved = Join-Path $folder "approved.mid"
    $cubase = Join-Path $folder "cubase-type1.mid"

    Invoke-CLI "midivolt" @("create", "--chords", "Fmaj7 Dm7 Gm7 C7",
                            "--bpm", "70", "--out", $source)
    Invoke-CLI "midivolt" @("analyze", "--input", $source)
    Invoke-CLI "midivolt-hub" @("catalog")
    Invoke-CLI "midivolt-review" @("propose", "--input", $source,
                                   "--chords", "C7", "--candidate-out", $candidate,
                                   "--manifest", $manifest, "--lock", "0")
    Invoke-CLI "midivolt-review" @("preview", "--manifest", $manifest)
    Invoke-CLI "midivolt-review" @("apply", "--manifest", $manifest,
                                   "--out", $approved, "--approve")
    Invoke-CLI "midivolt-cubase" @("check", "--input", $approved)
    Invoke-CLI "midivolt-cubase" @("prepare", "--input", $approved,
                                   "--out", $cubase, "--ppq", "480")
    Invoke-CLI "midivolt-cubase" @("compare", "--reference", $approved,
                                   "--returned", $cubase, "--strict")
    # Verify every K1-K11 shipped entry point is installed and imports.
    # --help never downloads weights, contacts Hugging Face or starts Cubase.
    foreach ($extra in @("midivolt-model", "midivolt-env", "midivolt-accept",
                          "midivolt-tsov", "midivolt-bridge",
                          "midivolt-compose", "midivolt-compose-accept",
                          "midivolt-compose-audit", "midivolt-compose-doctor",
                          "midivolt-beta-gate",
                          "midivolt-plan", "midivolt-transcribe", "midivolt-evaluate")) {
        Invoke-CLI $extra @("--help")
    }
    if (-not (Test-Path -LiteralPath $cubase -PathType Leaf)) {
        throw "Cubase Type 1 sample MIDI is missing."
    }
    Write-Host "WINDOWS_RC_SMOKE=PASS"
} finally {
    Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue
}
