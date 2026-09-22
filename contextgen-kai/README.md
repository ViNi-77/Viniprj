# contextgen 改

**資料を整理・確認してCopilotへ渡す、ローカル専用アプリ。**

独立した開発版 **0.1.0**。旧contextgen v3・pptx-web-bridgeはそのまま利用できます。Windows配布物の自動試験と、利用予定PCでの最終受入は分けて記録します。

## できること

- 複数フォルダの差分更新と、ファイルの単発取り込み。
- Office・PDF・画像・テキスト・CSV・ZIPの出典付き抽出。混在PDFとOffice画像の日本語/英語OCR。
- 検索・絞り込み・原本確認、収録除外、抽出本文の訂正。原本変更時は訂正の競合を表示。
- 用途別資料セットを保存し、M365 TXT、Markdown、JSONL、出典、診断、差替一覧、指示文を生成。
- 毎日・曜日・間隔による定期更新。アプリ起動中とWindowsバックグラウンド実行の切替。
- 原本を変更しない世代保存、保留、停止・再開、設定と修正のバックアップ。

## Windowsで使う

GitHub Actionsの **contextgen-kai Windows** → 成功した実行 → `contextgen-kai-windows` 成果物をダウンロードし、ZIPをローカルへ展開。`ContextgenKai/ContextgenKai.exe` をダブルクリックしてください。Pythonの導入は不要で、OCR・画面資源も同梱します。

ブラウザを閉じてもアプリ本体は動作します。完全に終了するときは画面の「アプリ終了」を選びます。「アプリ終了後も実行」モードの予約は終了後もWindows側に残ります。

## 開発環境（macOS / Windows、Python3.12）

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m contextgen_kai
```

Windowsの開発起動は `start_windows.bat`。macOSは `./start.sh`。開発時のOCRにはTesseract5とjpn/eng言語データを用意します。`CONTEXTGEN_TESSERACT` に実行ファイルを指定可能です。未導入時はOCR未処理を明示し、本文抽出は続けます。配布EXEにはOCRを同梱します。

`--state-dir <フォルダ>` で検証用保存先、`--port 8766` で起動ポート、`--no-browser` で自動ブラウザ起動を変更できます。OS予約は `--run-schedule <ID>` で同じ処理を実行します。

## 保存場所とバックアップ

Windows: `%LOCALAPPDATA%\ContextgenKai`。macOS: `~/Library/Application Support/ContextgenKai`。DBをBox/OneDrive等の同期フォルダへ移さないでください。入力資料フォルダは同期済みの場所を指定できます。オンラインのみのファイルは、先に端末へ取得してください。

JSONバックアップには登録先、用途別セット、資料参照、利用者による本文修正、予約設定を含みます。**原本・抽出キャッシュ・出力世代は含みません**。原本は別途保管してください。復元は空の保存先へ行い、登録先のパスを確認・変更して読み取りを実行します。復元した予約は停止状態です。

出力世代は自動削除しません。保存容量は利用者が管理します。エラー、修正競合、前回からの収録量の大幅減少時は確認待ちとなり、既存世代が有効なまま残ります。

## 試験

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/ui_smoke.py
.venv/bin/python scripts/benchmark_10000.py
```

Windows CIは同梱EXEを起動し、OCR・読み取り・出力・OS予約まで試験します。利用予定Windows PCでの最終確認手順は [Windows受入チェック](docs/04_検証記録とWindows受入.md) を参照してください。

## 設計文書

- [要件定義書・仕様書](docs/01_要件定義書.md)
- [アプリケーション概要・バージョン履歴](docs/02_アプリ概要とバージョン履歴.md)
- [アプリケーション基本設計基準書](docs/03_基本設計基準書.md)

## 制約と権利

旧doc/xls/ppt形式は新形式への変換が必要です。図や写真の意味は解釈せず、文字をOCRします。資料のAI分析とCopilotへの投入は利用者が行います。自動アップロードや外部AI接続はありません。直接アップロード用パッケージは各セット20ファイル以内で、全量を一つのエージェントに無制限投入するものではありません。

新規部分は独立実装で、旧contextgenのソース・既存の権利表示を変更していません。新しい権利帰属・ライセンスの宣言はしていません。同梱依存のライセンス・出典は配布物の `THIRD_PARTY_LICENSES/` に含めます。
