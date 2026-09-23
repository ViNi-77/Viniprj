@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if exist "ContextgenKai.exe" (
    echo このフォルダは配布EXE版です。新しいWindows配布ZIPを別のフォルダに展開してください。
    echo Gitで更新する場合は Viniprj\contextgen-kai にある「更新.bat」を使用してください。
    if not defined CONTEXTGEN_NO_PAUSE pause
    exit /b 1
)
call "%~dp0scripts\python_windows.bat" "%~dp0scripts\bootstrap_windows.py" --update-only
set "result=%ERRORLEVEL%"
if not defined CONTEXTGEN_NO_PAUSE pause
exit /b %result%
