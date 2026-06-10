@echo off
REM ASP Pipeline C - manually run issue analysis once (no timer, for debugging/catch-up).
REM Usage: double-click this file, or run run_scanner_once.bat from a terminal.
REM Effect: scan open issues assigned to you, generate analysis comment + add 'analyzed' label.
REM         Does NOT edit code or open PR (that is run_executor_once.bat).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_scanner.ps1"
echo.
echo ============================================
echo  See logs\scanner_*.log for analysis output
echo ============================================
pause
