@echo off
chcp 65001 >nul
rem ============================================================
rem  PPTX <-> Web図解 変換アプリ  Windows 起動スクリプト
rem  使い方: このファイルをダブルクリック（または start_windows.bat --no-browser）
rem  初回は仮想環境の作成と依存パッケージの導入で数分かかります。
rem  PowerShell の実行ポリシーに依存しないよう、venv の python.exe を直接呼びます。
rem ============================================================
setlocal
cd /d "%~dp0"
set "VENV=.venv"
set "PY="

rem --- Python を探す（py ランチャー → python → python3 の順）
where py >nul 2>nul && (py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=py -3")
if not defined PY (where python >nul 2>nul && (python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=python"))
if not defined PY (where python3 >nul 2>nul && (python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=python3"))
if not defined PY (
  echo Python 3.10 以上が見つかりません。https://www.python.org/downloads/ から導入し、
  echo インストール時に "Add python.exe to PATH" にチェックを入れてください。
  pause
  exit /b 1
)

rem --- 仮想環境
if not exist "%VENV%\Scripts\python.exe" (
  echo 仮想環境を作成します: %VENV%
  %PY% -m venv "%VENV%" || (echo 仮想環境の作成に失敗しました & pause & exit /b 1)
)
set "VPY=%VENV%\Scripts\python.exe"

rem --- 依存導入（requirements.txt が更新されたときも再実行）
set "NEED_INSTALL=0"
if not exist "%VENV%\.deps_installed" set "NEED_INSTALL=1"
if exist "%VENV%\.deps_installed" (
  "%VPY%" -c "import os,sys; sys.exit(0 if os.path.getmtime('requirements.txt') > os.path.getmtime(r'%VENV%\.deps_installed') else 1)" && set "NEED_INSTALL=1"
)
if "%NEED_INSTALL%"=="1" (
  echo 依存パッケージを導入します（初回のみ数分かかります）
  "%VPY%" -m pip install --upgrade pip >nul
  "%VPY%" -m pip install -r requirements.txt || (echo 依存パッケージの導入に失敗しました。ネットワーク（プロキシ）設定を確認してください。 & pause & exit /b 1)
  type nul > "%VENV%\.deps_installed"
  if not "%SKIP_PLAYWRIGHT_INSTALL%"=="1" (
    echo 見た目優先モード用のブラウザを導入します（失敗しても編集性優先モードで動作します）
    "%VPY%" -m playwright install chromium || echo Playwright のブラウザ導入に失敗しました。見た目優先モードは編集性優先へ代替されます。
  )
)

if "%~1"=="--setup-only" (echo セットアップ完了 & exit /b 0)

rem --- サンプル PPTX
if not exist "samples\sample_deck.pptx" "%VPY%" samples\make_sample_pptx.py >nul && echo サンプル PPTX を生成しました: samples\sample_deck.pptx

rem --- 起動（ブラウザが自動で開きます。止めるときは Ctrl+C）
set "PYTHONUTF8=1"
"%VPY%" backend\run_server.py %*
if errorlevel 1 (
  echo.
  echo 起動に失敗しました。logs\app.log を確認してください。
  pause
)
endlocal
