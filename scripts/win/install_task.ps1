# Register the ASP Pipeline D executor as a Windows Scheduled Task.
#
# Behavior (per requirement):
#   - Does NOT run at boot / startup (no boot trigger).
#   - While you are logged in and the machine is on, runs every N minutes.
#   - Shutting down stops it; next logon it resumes on schedule.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File install_task.ps1
#   powershell -ExecutionPolicy Bypass -File install_task.ps1 -Minutes 10
#   powershell -ExecutionPolicy Bypass -File install_task.ps1 -Uninstall

param(
    [int]$Minutes = 15,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$TaskName = 'ASP-PipelineD-Executor'
$Wrapper  = 'D:\work\asp\asp\scripts\win\run_executor.ps1'

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "Removed scheduled task: $TaskName"
    } else {
        Write-Output "Task not found (nothing to remove): $TaskName"
    }
    exit 0
}

if (-not (Test-Path $Wrapper)) { Write-Error "Wrapper not found: $Wrapper"; exit 1 }

# Action: run the wrapper hidden (no popup window every N minutes).
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Wrapper`""

# Trigger: repeat every N minutes starting shortly after registration.
# No AtStartup / AtLogOn trigger, so nothing runs at boot.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes)

# Run as current user, only when logged on (so env / token are present).
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Output "Installed scheduled task: $TaskName"
Write-Output "  Runs every $Minutes minute(s) while you are logged in."
Write-Output "  Does NOT run at boot. Manual run anytime: scripts\win\run_executor_once.bat"
