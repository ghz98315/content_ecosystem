$ErrorActionPreference='Stop'
$launcher=Join-Path $PSScriptRoot 'run_worker_guardian.ps1'
$shellPath=(Get-Command powershell.exe).Source
$arguments='-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$launcher+'"'
$action=New-ScheduledTaskAction -Execute $shellPath -Argument $arguments -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$triggers=@((New-ScheduledTaskTrigger -AtLogOn),(New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)))
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
try {
  Register-ScheduledTask -TaskName 'ContentEcosystemWorkerGuardian' -Action $action -Trigger $triggers -Settings $settings -Description 'Restores the local content Worker; publishes liveness without handling task contents' -Force | Out-Null
  Start-ScheduledTask -TaskName 'ContentEcosystemWorkerGuardian'
  Write-Output 'GUARDIAN_SCHEDULED'
} catch {
  $startup=[Environment]::GetFolderPath('Startup')
  $shortcut=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startup 'Content Ecosystem Worker Guardian.lnk'))
  $shortcut.TargetPath=$shellPath;$shortcut.Arguments=$arguments;$shortcut.WorkingDirectory=(Split-Path -Parent $PSScriptRoot);$shortcut.WindowStyle=7;$shortcut.Save()
  Start-Process -FilePath $shellPath -ArgumentList $arguments -WindowStyle Hidden
  Write-Output 'GUARDIAN_STARTUP_SHORTCUT'
}
