@echo off
REM ASP Pipeline D - 手动「干跑」：只列出已批准待执行的 issue，不改任何代码。
REM 用法：双击本文件，或命令行 run_executor_scan.bat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_executor.ps1" -ScanOnly
echo.
echo ============================================
echo  干跑结束。以上是「已批准待执行」的 issue 列表。
echo  要真正执行，请运行 run_executor_once.bat
echo ============================================
pause
