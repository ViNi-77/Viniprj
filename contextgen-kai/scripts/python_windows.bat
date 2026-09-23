@echo off
rem Use only Python 3.12 x64; do not install or change a system interpreter.
if exist "%~dp0..\.venv\Scripts\python.exe" (
    "%~dp0..\.venv\Scripts\python.exe" -c "import sys; exit(0 if sys.version_info[:2] == (3,12) and sys.maxsize > 2**32 else 1)" >nul 2>&1
    if not errorlevel 1 goto venv
)
py -3.12 -c "import sys; exit(0 if sys.maxsize > 2**32 else 1)" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys; exit(0 if sys.version_info[:2] == (3,12) and sys.maxsize > 2**32 else 1)" >nul 2>&1
if not errorlevel 1 goto python
echo Git版には Python 3.12 ^(64bit^) が必要です。導入後にもう一度「起動.bat」を開いてください。
echo Pythonを導入しない場合はWindows配布ZIPの ContextgenKai.exe を開いてください。
exit /b 1
:venv
"%~dp0..\.venv\Scripts\python.exe" %*
exit /b %ERRORLEVEL%
:launcher
py -3.12 %*
exit /b %ERRORLEVEL%
:python
python %*
exit /b %ERRORLEVEL%
