@echo off
chcp 936 >nul
cd /d "%~dp0"

rem Absolute path first: a broken PATH is a common cause of "powershell not found".
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo [FAIL] installer exited with an error. Scroll up for the reason.
  pause
)
