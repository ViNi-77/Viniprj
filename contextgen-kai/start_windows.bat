@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if exist "ContextgenKai.exe" (
    start "" "ContextgenKai.exe" %*
    exit /b 0
)
call "%~dp0scripts\python_windows.bat" "%~dp0scripts\bootstrap_windows.py" %*
set "result=%ERRORLEVEL%"
if not "%result%"=="0" if not defined CONTEXTGEN_NO_PAUSE pause
exit /b %result%
