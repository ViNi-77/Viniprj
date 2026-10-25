@echo off
cd /d "%~dp0"
if not exist dist\index.html (
  echo dist\ がありません。Node.js を入れて  npm install ^&^& npm run build  を実行してください。
  pause
  exit /b 1
)
python scripts\serve.py
if errorlevel 1 (
  py -3 scripts\serve.py
)
