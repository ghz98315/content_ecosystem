$ErrorActionPreference = 'Stop'
$logDir = Join-Path $PSScriptRoot 'runtime-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
try { $guardianLock = [IO.File]::Open((Join-Path $logDir 'worker-guardian.lock'),'OpenOrCreate','ReadWrite','None') }
catch [IO.IOException] { exit 0 }
try {
  $runtime = Get-Content (Join-Path $PSScriptRoot 'output/worker-runtime.json') -Raw | ConvertFrom-Json
  $env:PYTHONIOENCODING = 'utf-8'
  Remove-Item Env:WORKER_TASK_ID,Env:WORKER_STAGE_KINDS,Env:PYTHONPATH -ErrorAction SilentlyContinue
  $arguments = @('-u',('"'+(Join-Path $PSScriptRoot 'bootstrap.py')+'"'),'--entry',('"'+(Join-Path $PSScriptRoot 'worker_guardian.py')+'"'))
  foreach($dependency in $runtime.dependencies){$arguments += @('--dependency-dir',('"'+$dependency+'"'))}
  while($true){
    $child=Start-Process -FilePath $runtime.python -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $PSScriptRoot) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'worker-guardian.out.log') -RedirectStandardError (Join-Path $logDir 'worker-guardian.err.log') -PassThru
    $child.WaitForExit();$child.Dispose()
    Start-Sleep -Seconds 15
  }
} finally {$guardianLock.Dispose()}
