# ASP Pipeline C + D 自动化（Windows）。
# 一轮里依次做两件事：
#   ① 分析（Pipeline C）：扫 assignee=你 的 open issue，生成分析报告评论 + 打 analyzed 标签。
#   ② 执行（Pipeline D）：对已打 approved-to-execute 标签的 issue，自动改代码 + AI 审查 + 开 PR。
#      已执行过(executed)/已有PR/失败(execution-failed/review-failed) 的会自动跳过，不重复改。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File run_scanner.ps1            # 分析 + 执行（定时任务用这个）
#   powershell -ExecutionPolicy Bypass -File run_scanner.ps1 -ScanOnly  # 只列出待分析的 issue，不分析不执行
#   powershell -ExecutionPolicy Bypass -File run_scanner.ps1 -NoExecute # 只分析，不执行（旧行为）
#   powershell -ExecutionPolicy Bypass -File run_scanner.ps1 -Batch 10

param(
    [switch]$ScanOnly,
    [switch]$NoExecute,
    [int]$Batch = 5,
    [int]$ExecuteBatch = 3
)

$ErrorActionPreference = 'Stop'

# 强制 UTF-8：让 Python 以 UTF-8 输出中文日志，PowerShell 也以 UTF-8 解码，
# 否则 Windows 默认 cp936 编码会让日志里的中文变成乱码。
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# 固定路径（硬编码，保证任务计划程序非交互运行时也能找到）。
$Python   = 'C:\Users\publi\AppData\Local\Programs\Python\Python313\python.exe'
$RepoRoot = 'D:\work\asp\asp'
$Scanner  = Join-Path $RepoRoot 'tools\feishu_inbound\issue_scanner.py'
$Executor = Join-Path $RepoRoot 'tools\feishu_inbound\issue_executor.py'
$LogDir   = Join-Path $RepoRoot 'logs'

if (-not (Test-Path $Python))  { Write-Error "Python not found: $Python"; exit 1 }
if (-not (Test-Path $Scanner)) { Write-Error "Scanner not found: $Scanner"; exit 1 }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# claude CLI 在 Windows 上需要 git-bash；.env 里有 CLAUDE_CODE_GIT_BASH_PATH，
# 这里再兜底一次，防止调度器环境不完整。
if (-not $env:CLAUDE_CODE_GIT_BASH_PATH) {
    foreach ($p in @('D:\Git\bin\bash.exe', 'C:\Program Files\Git\bin\bash.exe')) {
        if (Test-Path $p) { $env:CLAUDE_CODE_GIT_BASH_PATH = $p; break }
    }
}

Set-Location $RepoRoot

$stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$logFile = Join-Path $LogDir "scanner_$stamp.log"

$pyArgs = @($Scanner)
if ($ScanOnly) {
    $pyArgs += '--scan-only'
} else {
    $pyArgs += @('--batch', "$Batch", '--parallel')
}

Write-Output "[$stamp] Running: $Python $($pyArgs -join ' ')"
Write-Output "[$stamp] Log: $logFile"

# 逐行输出：实时打印到控制台，同时以 UTF-8 写入日志文件（Tee-Object 在
# Windows PowerShell 5.1 下会写成 UTF-16，这里改用 Add-Content -Encoding UTF8）。
if (Test-Path $logFile) { Remove-Item $logFile -Force }
& $Python @pyArgs 2>&1 | ForEach-Object {
    Write-Host $_
    Add-Content -Path $logFile -Value $_ -Encoding UTF8
}
$code = $LASTEXITCODE

# 废弃无用日志：本轮没有任何「待分析」的需求时，删掉这份日志，避免定时任务
# 每 15 分钟堆一堆空跑日志。判据：scanner 每个仓库都会打印
# "... N need analysis"，只要有任意一行 N>0，就说明本轮有实际分析，保留日志。
# 解析失败（脚本报错等）一律保留，方便排查。
if (-not $ScanOnly -and (Test-Path $logFile)) {
    $hadWork = $false
    try {
        foreach ($line in (Get-Content -Path $logFile -Encoding UTF8)) {
            $m = [regex]::Match($line, '(\d+)\s+need analysis')
            if ($m.Success -and [int]$m.Groups[1].Value -gt 0) { $hadWork = $true; break }
        }
        if ($code -eq 0 -and -not $hadWork) {
            Remove-Item $logFile -Force
            Write-Output "[$stamp] 本轮无待分析需求，已删除空日志：$logFile"
        }
    } catch {
        Write-Output "[$stamp] 日志保留性判断失败，保留日志：$_"
    }
}

# ===========================================================================
# ② 执行阶段（Pipeline D）：对已打 approved-to-execute 标签的 issue 自动改代码 + 开 PR。
#    -ScanOnly 或 -NoExecute 时跳过。已执行/已有PR/失败 的 issue 由 executor 自身门禁跳过。
# ===========================================================================
if (-not $ScanOnly -and -not $NoExecute) {
    $execLog = Join-Path $LogDir "executor_$stamp.log"
    $execArgs = @($Executor, '--batch', "$ExecuteBatch", '--parallel')
    Write-Output "[$stamp] 执行阶段 Running: $Python $($execArgs -join ' ')"
    Write-Output "[$stamp] 执行日志: $execLog"

    if (Test-Path $execLog) { Remove-Item $execLog -Force }
    & $Python @execArgs 2>&1 | ForEach-Object {
        Write-Host $_
        Add-Content -Path $execLog -Value $_ -Encoding UTF8
    }
    $execCode = $LASTEXITCODE

    # 废弃无用执行日志：本轮没有任何「可执行」的 issue 时删掉空日志。
    # 判据：executor 会打印 "... N 个可执行"，只要有任意一行 N>0 就保留。
    if (Test-Path $execLog) {
        $hadExec = $false
        try {
            foreach ($line in (Get-Content -Path $execLog -Encoding UTF8)) {
                $m = [regex]::Match($line, '(\d+)\s*个可执行')
                if ($m.Success -and [int]$m.Groups[1].Value -gt 0) { $hadExec = $true; break }
            }
            if ($execCode -eq 0 -and -not $hadExec) {
                Remove-Item $execLog -Force
                Write-Output "[$stamp] 本轮无可执行 issue，已删除空执行日志：$execLog"
            }
        } catch {
            Write-Output "[$stamp] 执行日志保留性判断失败，保留日志：$_"
        }
    }
    # 执行阶段非 0 退出码不覆盖分析阶段的结果，只记录；整体以分析阶段退出码为准。
    if ($execCode -ne 0) { Write-Output "[$stamp] 执行阶段 Exit code: $execCode" }
}

Write-Output "[$stamp] Exit code: $code"
exit $code
