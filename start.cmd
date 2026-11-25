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

rem WeChatAppEx.exe is the miniapp runtime the debugger hooks into.
rem Without it the proxy dies with a raw stack trace, which looks broken.
set "APPEX="
"%SystemRoot%\System32\tasklist.exe" /fi "imagename eq WeChatAppEx.exe" 2>nul | find /i "WeChatAppEx.exe" >nul && set "APPEX=1"

if not defined APPEX (
  echo.
  echo [FAIL] WeChat mini-program runtime is not running.
  echo.
  echo   The debugger attaches to WeChatAppEx.exe, which only exists
  echo   after WeChat has opened a mini program at least once.
  echo.
  echo   Do this once:
  echo     1. open WeChat and log in
  echo     2. open the game from WeChat, then CLOSE that window
  echo     3. run this start.cmd again
  echo     4. when you see "[proxy] hook ready", reopen the game
  echo.
  echo   Order matters: the hook only catches pages loaded after it is ready.
  echo.
  pause
  exit /b 1
)

call "dbg\sheep-solver\oneclick.cmd" %*
