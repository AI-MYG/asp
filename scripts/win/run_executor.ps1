# ASP Pipeline D local executor (Windows).
# Scans approved-to-execute issues, edits code via local claude in an isolated
# worktree, AI-reviews, pushes, opens PR. Runs only on this machine.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File run_executor.ps1 -ScanOnly
#   powershell -ExecutionPolicy Bypass -File run_executor.ps1

param(
    [switch]$ScanOnly,
    [int]$Batch = 3
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

# Fixed paths (hardcoded so Task Scheduler non-interactive runs work).
$Python   = 'C:\Users\publi\AppData\Local\Programs\Python\Python313\python.exe'
$RepoRoot = 'D:\work\asp\asp'
$Executor = Join-Path $RepoRoot 'tools\feishu_inbound\issue_executor.py'
$LogDir   = Join-Path $RepoRoot 'logs'

if (-not (Test-Path $Python))   { Write-Error "Python not found: $Python"; exit 1 }
if (-not (Test-Path $Executor)) { Write-Error "Executor not found: $Executor"; exit 1 }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# claude CLI needs git-bash on Windows; .env has CLAUDE_CODE_GIT_BASH_PATH but
# set a fallback here in case the scheduler env is incomplete.
if (-not $env:CLAUDE_CODE_GIT_BASH_PATH) {
    foreach ($p in @('D:\Git\bin\bash.exe', 'C:\Program Files\Git\bin\bash.exe')) {
        if (Test-Path $p) { $env:CLAUDE_CODE_GIT_BASH_PATH = $p; break }
    }
}

Set-Location $RepoRoot

$stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$logFile = Join-Path $LogDir "executor_$stamp.log"

$pyArgs = @($Executor)
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

Write-Output "[$stamp] Exit code: $code"
exit $code
