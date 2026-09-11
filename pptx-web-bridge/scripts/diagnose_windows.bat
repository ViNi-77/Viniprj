@echo off
chcp 65001 >nul
echo ============================================
echo  PPTX-Web-Bridge 診断スクリプト
echo ============================================
echo.

echo [1] 動いているプロセスを終了します
taskkill /f /im python.exe 2>nul
taskkill /f /im pptx-web-bridge.exe 2>nul
echo   -> 完了
echo.

echo [2] 作業フォルダを確認
if not exist "Viniprj" (
  echo   Viniprj フォルダが無いので新規クローンします
  git clone https://github.com/ViNi-77/Viniprj.git
) else (
  echo   既存フォルダを最新化します
  cd Viniprj
  git fetch origin
  git checkout main
  git reset --hard origin/main
  cd ..
)
echo.

cd Viniprj\pptx-web-bridge
echo [3] 現在のコミット（95a3630 であるべき）
git log --oneline -1
echo.

echo [4] サーバーを起動します（このウィンドウは閉じないでください）
start "PWB Server" cmd /k start_windows.bat --no-browser

echo   起動を待っています...
timeout /t 8 /nobreak >nul

echo.
echo [5] API から版を確認
curl -s http://127.0.0.1:8765/api/version
echo.
echo.

echo [6] 画面に Copilot ボタンがあるか確認
curl -s http://127.0.0.1:8765/ | findstr "btn-copilot" >nul
if %errorlevel%==0 (
  echo   -> ボタンはサーバー側にあります（○）
) else (
  echo   -> ボタンが見つかりません（×・要報告）
)
echo.

echo ============================================
echo  ブラウザで http://127.0.0.1:8765/ を開き、
echo  左側パネルを一番下までスクロールしてください。
echo  「4. Copilot 連携」の中に緑色の
echo  「Copilot に頼む」ボタンがあります。
echo ============================================
pause
