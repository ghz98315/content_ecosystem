param(
    [int]$RestartDelaySeconds = 5
)

$ErrorActionPreference = "Continue"
$workerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location -LiteralPath $workerRoot
while ($true) {
    & python main.py
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        break
    }
    Write-Warning "Worker exited with code $exitCode; restarting in $RestartDelaySeconds seconds."
    Start-Sleep -Seconds $RestartDelaySeconds
}
