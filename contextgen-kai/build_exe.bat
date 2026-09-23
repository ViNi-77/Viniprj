@echo off
setlocal
cd /d "%~dp0"
call start_windows.bat --setup-only
if errorlevel 1 goto failed
set "PATH=%~dp0.venv\Scripts;%PATH%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_windows.ps1"
if errorlevel 1 goto failed
echo.
echo Build completed: dist\ContextgenKai\ContextgenKai.exe
pause
exit /b 0
:failed
echo Build failed. See the message above.
pause
exit /b 1
