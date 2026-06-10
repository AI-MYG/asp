# 把 ASP Pipeline C（分析器）注册成 Windows 计划任务。
#
# 行为（按需求）：
#   - 不开机自启（无 boot 触发器）。
#   - 你登录且开机期间，每 N 分钟自动跑一次「分析新 issue」。
#   - 关机即停；下次登录按计划恢复。
#   - 只做分析（Pipeline C）：生成分析评论 + 打 analyzed 标签。
#     审批（approved-to-execute 标签）和执行（run_executor）保持手动。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File install_scanner_task.ps1
#   powershell -ExecutionPolicy Bypass -File install_scanner_task.ps1 -Minutes 15
#   powershell -ExecutionPolicy Bypass -File install_scanner_task.ps1 -Uninstall

param(
    [int]$Minutes = 15,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$TaskName = 'ASP-PipelineC-Scanner'
$Wrapper  = 'D:\work\asp\asp\scripts\win\run_scanner.ps1'

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

# 动作：隐藏窗口运行包装器（避免每 N 分钟弹一个黑框）。
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Wrapper`""

# 触发器：注册后 1 分钟开始，之后每 N 分钟重复。
# 无 AtStartup / AtLogOn 触发器，所以不会开机自启。
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes)

# 以当前用户身份、仅在登录时运行（保证 env / token 可用）。
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

# 分析比执行轻，1 小时超时足够；同一时刻只跑一个实例（IgnoreNew）。
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Output "Installed scheduled task: $TaskName"
Write-Output "  Runs every $Minutes minute(s) while you are logged in."
Write-Output "  Does NOT run at boot. Only analyzes (Pipeline C) — approval & execution stay manual."
Write-Output "  Logs: D:\work\asp\asp\logs\scanner_*.log"
Write-Output "  Uninstall: powershell -ExecutionPolicy Bypass -File install_scanner_task.ps1 -Uninstall"
