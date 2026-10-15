param(
  [Parameter(Mandatory = $true)][string]$TaskId,
  [string]$StageKinds = "",
  [switch]$AutoPowerOn,
  [switch]$AutoPowerOff
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runtimeConfig = Join-Path $PSScriptRoot 'output\worker-runtime.json'
if ((Test-Path -LiteralPath $runtimeConfig) -and -not $AutoPowerOn -and -not $AutoPowerOff) {
  & (Join-Path $PSScriptRoot 'run_worker_service.ps1') -RuntimeConfig $runtimeConfig -TaskId $TaskId -StageKinds $StageKinds
  exit $LASTEXITCODE
}
$logDir = Join-Path $PSScriptRoot "runtime-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$out = Join-Path $logDir ("worker-{0}.out.log" -f $TaskId)
$err = Join-Path $logDir ("worker-{0}.err.log" -f $TaskId)

if ($AutoPowerOn) {
  python (Join-Path $PSScriptRoot "gpushare_power.py") on
}

$env:WORKER_TASK_ID = $TaskId
$env:WORKER_STAGE_KINDS = $StageKinds
Push-Location $root
try {
  & python -u (Join-Path $PSScriptRoot "main.py") *> $out
  $exitCode = $LASTEXITCODE
}
finally {
  Pop-Location
}

if ($AutoPowerOff) {
  try {
    python (Join-Path $PSScriptRoot "gpushare_power.py") off *>> $out
  } catch {
    Add-Content -Path $err -Value ("AUTO_POWER_OFF_FAILED: " + $_.Exception.Message)
  }
}
exit $exitCode
