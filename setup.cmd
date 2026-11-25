@echo off
setlocal
chcp 936 >nul
cd /d "%~dp0"

echo ============================================================
echo  wxsheep - first time setup
echo ============================================================
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [FAIL] git not found
  echo        install Git for Windows: https://git-scm.com/download/win
  goto :end
)

if not exist "dbg" mkdir "dbg"

call :fetch sheep-solver https://github.com/GlrAoc/sheep-solver.git
call :fetch WMPFDebugger https://github.com/evi0s/WMPFDebugger.git

if exist "docs\patches\0001-wmpfdebugger-logger-file-log.patch" if exist "dbg\WMPFDebugger\src\logger.ts" call :patch

echo.
echo --- environment ---
where node >nul 2>nul && (for /f "delims=" %%v in ('node -v') do echo [ok]   node %%v) || echo [WARN] node not found - need 22+
where yarn >nul 2>nul && (for /f "delims=" %%v in ('yarn -v') do echo [ok]   yarn %%v) || echo [WARN] yarn not found - need 1.22.x

echo.
echo --- next ---
echo  1^) install proxy deps, once only:
echo       cd dbg\WMPFDebugger
echo       yarn install
echo     If frida falls back to compiling from source, stop and read
echo     docs\ENVIRONMENT.md section 3.3 ^(prebuilt napi-v8 binding^).
echo.
echo  2^) run:  dbg\sheep-solver\oneclick.cmd
echo     IMPORTANT: run it BEFORE opening the miniapp window.
echo     Wait for "hook ready", then open the game and enter a level.
echo.
goto :end

:fetch
if exist "dbg\%~1\.git" (
  echo [skip] dbg\%~1 already exists
  exit /b 0
)
echo [clone] %~1
git clone --depth 1 %~2 "dbg\%~1"
if errorlevel 1 (
  echo [FAIL] clone failed - check network or clone it manually:
  echo        git clone %~2 dbg\%~1
) else (
  echo [ok]   dbg\%~1
)
exit /b 0

:patch
pushd "dbg\WMPFDebugger"
git apply --reverse --check "..\..\docs\patches\0001-wmpfdebugger-logger-file-log.patch" >nul 2>nul
if errorlevel 1 (
  git apply "..\..\docs\patches\0001-wmpfdebugger-logger-file-log.patch" >nul 2>nul
  if errorlevel 1 (echo [WARN] log patch failed - apply it by hand, see docs\ENVIRONMENT.md) else (echo [ok]   proxy log patch applied)
) else (
  echo [ok]   proxy log patch already applied
)
popd
exit /b 0

:end
echo.
echo Press any key to exit . . .
pause >nul
