param(
  [string]$RuntimeConfig = (Join-Path $PSScriptRoot 'output\worker-runtime.json'),
  [string]$TaskId = '',
  [string]$StageKinds = ''
)

$ErrorActionPreference = 'Stop'
$runtime = Get-Content -LiteralPath $RuntimeConfig -Raw | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $runtime.python -PathType Leaf)) { throw 'Configured Python runtime is missing' }
$logDir = Join-Path $PSScriptRoot 'runtime-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$lockName = if ($TaskId) { 'worker-' + $TaskId + '.lock' } else { 'worker-service.lock' }
try {
  $lock = [System.IO.File]::Open((Join-Path $logDir $lockName), 'OpenOrCreate', 'ReadWrite', 'None')
} catch [System.IO.IOException] {
  Write-Output 'Worker is already running for this scope'
  exit 0
}
try {
  $env:WORKER_TASK_ID = $TaskId
  $env:WORKER_STAGE_KINDS = $StageKinds
  $env:PYTHONIOENCODING = 'utf-8'
  $env:PYTHONUNBUFFERED = '1'
  # bootstrap preloads the working NumPy before adding isolated packages.
  Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  $arguments = @('-u', ('"' + (Join-Path $PSScriptRoot 'bootstrap.py') + '"'))
  foreach ($dependency in $runtime.dependencies) {
    $arguments += @('--dependency-dir', ('"' + $dependency + '"'))
  }
  $scope = if ($TaskId) { $TaskId } else { 'service' }
  $process = Start-Process -FilePath $runtime.python -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $PSScriptRoot) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir ('worker-' + $scope + '.out.log')) -RedirectStandardError (Join-Path $logDir ('worker-' + $scope + '.err.log')) -PassThru
  @{pid=$process.Id; scope=$scope; started_at=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDir ('worker-' + $scope + '.pid.json'))
  $process.WaitForExit()
  exit $process.ExitCode
} finally {
  $lock.Dispose()
}
