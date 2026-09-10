# Windows ビルド手順（PyInstaller）

Windows exe は Windows 上でしかビルドできないため、
ビルドは Windows 機で実施します。

## 前提

- Windows 10/11
- Python 3.12（python.org 版を推奨。「Add python.exe to PATH」にチェック）

## 手順

```bat
rem 1. リポジトリ（work1_improvement フォルダ）を C:\Tools\contextgen 等へ配置

cd C:\Tools\contextgen

rem 2. 仮想環境と依存
python -m venv .venv
.venv\Scripts\pip install -e ".[dev,ocr-windows]"
.venv\Scripts\pip install pyinstaller pywin32

rem OCR を使わない最小構成なら: .venv\Scripts\pip install -e ".[dev]"

rem 3. 動作確認（exe 化前に必ず）
.venv\Scripts\python -m pytest tests
.venv\Scripts\python -m contextgen.gui

rem 4a. ビルド（onedir: フォルダ配布・起動が速い）
.venv\Scripts\pyinstaller contextgen.spec
rem → 配布物: dist\CopilotM365ContextGenerator\ フォルダ一式

rem 4b. ビルド（onefile: 単一exe・原本と同じ配布形態）
.venv\Scripts\pyinstaller contextgen_onefile.spec
rem → 配布物: dist\CopilotM365ContextGenerator.exe の1ファイルだけ
```

## onefile と onedir の使い分け

| | onefile（contextgen_onefile.spec） | onedir（contextgen.spec） |
|---|---|---|
| 配布物 | **exe 1ファイル**（原本と同じ形態） | フォルダ一式（ZIP配布） |
| 起動速度 | 遅い（毎回一時フォルダに自己展開、数秒〜十数秒） | 速い |
| AV誤検知 | やや出やすい | 出にくい |
| 差し替え | 1ファイル上書きで完了 | フォルダごと差し替え |

社内の共有フォルダに置いてダブルクリックで使う運用なら onefile、
各自のPCにインストールして毎日使うなら onedir を推奨。

## 1つの exe で GUI と CLI の両方が動く

launcher_gui.py は引数の有無でモードを切り替えます:

```bat
rem ダブルクリック（引数なし）→ GUI が開く
CopilotM365ContextGenerator.exe

rem 引数あり → CLI として動作（タスクスケジューラ登録はこの形で）
CopilotM365ContextGenerator.exe --source "C:\BoxDrive\..." --output "C:\..." --sort mtime_desc
```

exe は windowed ビルドのため CLI モードでも画面出力はありません。
実行結果は 管理フォルダの box_copy_gui_log.txt と Teams 通知
（--teams-webhook）で確認してください。終了コード（0=正常）は
タスクスケジューラの「前回の実行結果」に反映されます。

## 注意事項

- **onedir 構成**にしています（従来の onefile 単一exeより起動が速く、
  ウイルス対策ソフトの誤検知も減ります）。配布はフォルダごと ZIP で。
- `pywin32` は .doc → docx 自動変換（Word がある端末のみ動作）に使います。
  入れなくても動作し、.doc は「要変換」としてレポートされます。
- **v2.1 OCR**: `[ocr-windows]` extras（pypdfium2 + winsdk）で Windows 10/11
  内蔵の OCR エンジンを使います（Tesseract 等の追加インストール不要）。
  Windows 実機で `--ocr auto` の動作確認をしてください
  （winsdk 経路は実機確認が必要）。
- 原本 exe は PIL/avif 等の未使用ライブラリ同梱で 27MB ありました。
  spec の excludes で除外済みですが、ビルド後に dist フォルダのサイズを
  確認してください（目安: 30〜40MB のフォルダ、zip で 15MB 前後）。
- 社内配布するなら**コード署名**を検討してください（原本は未署名で
  SmartScreen 警告が出る状態でした）。署名証明書がない場合は、
  配布 ZIP の SHA256 を README に記載する運用でも代替になります。

## CLI だけを使う場合

exe 化せず、Python 環境 + タスクスケジューラでの運用も可能です
（docs/OPERATIONS.md 参照）。この方が更新配布が楽です。
