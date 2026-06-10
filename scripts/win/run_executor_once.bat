@echo off
REM ASP Pipeline D - 手动「真执行」：扫描已批准的 issue，自动改代码 + AI 审查 + 提 PR。
REM 用法：双击本文件，或命令行 run_executor_once.bat
REM 前提：对应 issue 已打 approved-to-execute 标签（trivial 难度可免标签）。
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_executor.ps1"
echo.
echo ============================================
echo  执行结束。详见 logs\executor_*.log
echo ============================================
pause
