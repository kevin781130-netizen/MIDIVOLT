# MIDIVOLT Windows RC 單一驗收入口：核對封包 SHA256 -> 安裝到新 venv -> smoke -> 全部 CLI --help -> 輸出 JSON 結果。
# 不啟動 Cubase、不下載模型權重、不以管理員權限執行。需先安裝 Python 3.11 x64 與 py.exe。
[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $env:LOCALAPPDATA "MIDIVOLT\venv-0.1.0rc1-accept"),
    [switch]$AllowNetwork,
    [string]$Wheelhouse,
    [string]$ResultPath = (Join-Path $PSScriptRoot "MIDIVOLT-windows-acceptance-result.json")
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$clis = @("midivolt", "midivolt-prompt", "midivolt-ai", "midivolt-bridge", "midivolt-tsov",
          "midivolt-review", "midivolt-model", "midivolt-hub", "midivolt-env", "midivolt-accept",
          "midivolt-cubase", "midivolt-transcribe", "midivolt-evaluate")
$result = [ordered]@{
    status = "FAIL"; started_utc = (Get-Date).ToUniversalTime().ToString("o"); destination = $null
    windows = [Environment]::OSVersion.VersionString; powershell = $PSVersionTable.PSVersion.ToString()
    package_hashes = @(); steps = @(); cli_help = @(); python = $null; pip_freeze = @(); error = $null
}
function Add-Step([string]$Name, [bool]$Ok, [string]$Detail = "") {
    $script:result.steps += [ordered]@{ name = $Name; ok = $Ok; detail = $Detail }
    if (-not $Ok) { throw "Step failed: $Name $Detail" }
}
try {
    if ([bool]$AllowNetwork -eq [bool]$Wheelhouse) {
        throw "Choose exactly one dependency source: -AllowNetwork OR -Wheelhouse <folder>."
    }
    $destinationFull = [IO.Path]::GetFullPath($Destination)
    $result.destination = $destinationFull

    # 1) 封包完整性：SHA256SUMS.txt 內每一列都必須與實際檔案相符。
    $sums = Join-Path $PSScriptRoot "SHA256SUMS.txt"
    Add-Step "sha256sums_present" (Test-Path -LiteralPath $sums -PathType Leaf) $sums
    foreach ($line in (Get-Content -LiteralPath $sums -Encoding ASCII)) {
        if (-not $line.Trim()) { continue }
        $parts = $line -split "\s+", 2
        $name = $parts[1].TrimStart("*")
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot $name)).Hash.ToLowerInvariant()
        $match = ($actual -eq $parts[0].ToLowerInvariant())
        $result.package_hashes += [ordered]@{ file = $name; sha256 = $actual; match = $match }
        Add-Step "hash:$name" $match
    }

    # 2) 以正式安裝器安裝（內含 Smoke-MIDIVOLT.ps1：生成/檢查/review/Cubase prepare 與嚴格比對）。
    $installArgs = @("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                     (Join-Path $PSScriptRoot "Install-MIDIVOLT.ps1"), "-Destination", $destinationFull)
    if ($AllowNetwork) { $installArgs += "-AllowNetwork" } else { $installArgs += @("-Wheelhouse", $Wheelhouse) }
    & powershell.exe @installArgs
    Add-Step "install_and_smoke" ($LASTEXITCODE -eq 0) "exit=$LASTEXITCODE"

    # 3) 已安裝環境：Python 版本、依賴清單、全部已註冊 CLI --help。
    $python = Join-Path $destinationFull "Scripts\python.exe"
    $result.python = (& $python -c "import sys; print(sys.version)") -join " "
    $result.pip_freeze = @(& $python -m pip freeze)
    foreach ($cli in $clis) {
        $exe = Join-Path $destinationFull "Scripts\$cli.exe"
        $ok = $false
        if (Test-Path -LiteralPath $exe -PathType Leaf) {
            & $exe --help *> $null
            $ok = ($LASTEXITCODE -eq 0)
        }
        $result.cli_help += [ordered]@{ cli = $cli; ok = $ok }
        Add-Step "help:$cli" $ok
    }
    $result.status = "PASS"
} catch {
    $result.error = $_.Exception.Message
} finally {
    $result.finished_utc = (Get-Date).ToUniversalTime().ToString("o")
    ($result | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    Write-Host "WINDOWS_RC_ACCEPTANCE=$($result.status)  result: $ResultPath"
}
if ($result.status -ne "PASS") { exit 1 }
