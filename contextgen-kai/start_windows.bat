@echo off
cd /d "%~dp0"
if exist "ContextgenKai.exe" (
    start "" "ContextgenKai.exe" %*
    exit /b 0
)
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" -m contextgen_kai %*
exit /b %ERRORLEVEL%
:missing
echo Please extract the complete Windows ZIP and start ContextgenKai.exe.
echo Source developers: create a Python 3.12 venv and run pip install -e .
pause
exit /b 1
