@echo off
setlocal
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-genealogy.ps1"
if "%ERRORLEVEL%"=="2" (
  echo.
  echo FastAPI started inside WSL, but Windows localhost forwarding failed.
  echo Run "wsl --shutdown", then start this script again.
)
echo.
echo Startup script exited. Press any key to close this window.
pause >nul
