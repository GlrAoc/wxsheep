@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"

if exist "runtime\node\node.exe" set "PATH=%CD%\runtime\node;%PATH%"

if not exist "dbg\sheep-solver\oneclick.cmd" (
  echo [FAIL] not installed yet.
  echo        double-click install.cmd first.
  echo.
  pause
  exit /b 1
)

call "dbg\sheep-solver\oneclick.cmd" %*
