@echo off
rem ============================================================
rem contextgen 夜間自動実行バッチ（タスクスケジューラ登録用）
rem 環境に合わせて PYTHON / SOURCE / OUTPUT を書き換えてください
rem ============================================================

set PYTHON=C:\Tools\contextgen\.venv\Scripts\python.exe
set SOURCE=C:\BoxDrive\Box\第2ユニット生技部_全員\002_室運営\2026年\NZB00_アルミ開発室
set OUTPUT=C:\BoxDrive\Box\第2ユニット生技部_全員\002_室運営\2026年\NZB00_アルミ開発室\2G\401_内製ソフト\ChatGPT用コンテキストファイル生成\生成コンテキスト

"%PYTHON%" -m contextgen --source "%SOURCE%" --output "%OUTPUT%" --sort mtime_desc

exit /b %ERRORLEVEL%
