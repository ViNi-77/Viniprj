# contextgen 改

**資料を整理・確認してCopilotへ渡す、ローカル専用アプリ。開発版 0.2.0。**

OCR本体（Windows x64版Tesseract 5.5.1）と日本語・英語データも、このフォルダに入っています。**Gitで取得・更新すればOCRも一緒に取得・更新できます。別途コピーする必要はありません。** 旧contextgen v3とpptx-web-bridgeは変更していません。

| はじめに読むもの | 内容 |
|---|---|
| [画像付き操作マニュアル](contextgen改_操作マニュアル.html) | フォルダ内のHTMLをダブルクリック。実画面画像で起動から終了まで説明。アプリ左下からも開けます |
| [仕様書兼要件定義書](仕様書兼要件定義書.md) | 目的・機能・画面・データ・API・異常時・受入条件 |
| [アプリ概要とバージョン履歴](アプリ概要とバージョン履歴.md) | できること・対応形式・版ごとの変更・制約 |
| [アプリ基本設計基準書](アプリ基本設計基準書.md) | 非破壊処理・画面・保存・Windows配布・試験・文書更新ルール |
| [検証記録とWindows受入](docs/04_検証記録とWindows受入.md) | 自動試験の実績と、利用予定PCで確認する項目 |

## WindowsでGitから取得する

Git版の初回利用には **Git for WindowsとPython 3.12（64bit、`py -3.12`が使える状態）** が必要です。依存ライブラリの初回準備時・更新時のみインターネットを使います。OCRを別途インストールする必要はなく、準備後の資料処理はPC内で完結します。

現在の開発ブランチは `codex/contextgen-kai` です。mainへのマージ前なので、このブランチを指定してください。

### すでに C:\Viniprj にクローン済みの場合

アプリを画面の「アプリを終了する」で終了してから、コマンドプロンプトで実行します。フォルダを作り直す必要はありません。

```bat
cd /d C:\Viniprj
git fetch origin
git switch codex/contextgen-kai
git pull --ff-only
cd contextgen-kai
start_windows.bat
```

`git switch` / `git pull` がローカル変更との衝突を示した場合はそこで停止してください。`reset --hard` やフォルダ削除は不要です。初めてブランチを使う場合は、`git switch` が同名のoriginブランチを追跡するローカルブランチを作ります。

### 初めてクローンする場合

`C:\Viniprj` がまだ存在しない場合だけ実行します。

```bat
git clone --branch codex/contextgen-kai https://github.com/ViNi-77/Viniprj.git C:\Viniprj
cd /d C:\Viniprj\contextgen-kai
start_windows.bat
```

初回起動は仮想環境 `.venv` と依存ライブラリを自動準備してブラウザを開きます。次回からは **`起動.bat` のダブルクリック**で使えます。`start_windows.bat` も同じ入口です。

### 次回以降の更新

アプリを終了後、**`更新.bat` をダブルクリック**します。現在選んでいるブランチを `git pull --ff-only` で更新し、OCR・文書・マニュアルも同じ更新に含めます。追跡対象のローカル変更、別のリポジトリ、分岐した履歴は上書きせず停止します。

更新後は `起動.bat` を実行してください。依存の定義が変わった場合だけ再準備し、設定・本文修正・出力世代は利用者専用領域に保持します。画面左下の版表示が **0.2.0** になったことを確認します。

## Pythonを入れずに使う場合

[Windows CI](https://github.com/ViNi-77/Viniprj/actions/workflows/contextgen-kai.yml)の成功した実行から `contextgen-kai-windows` 成果物をダウンロードし、内部の配布ZIPまで展開して `ContextgenKai.exe` をダブルクリックします。EXE版にはPython実行環境・OCR・画面・文書・画像付きマニュアルを含めます。

Git版とEXE版は起動方法が違います。EXE版を更新するときは新しい配布ZIPを別フォルダに展開して起動してください。Gitを持たない配布フォルダでは `更新.bat` によるpullは行いません。

## ファイル構成

写真と同じように、利用者が探す文書・マニュアル・起動ファイルをアプリ直下にまとめています。実装のフォルダ名は本アプリの構造に合わせています。

```text
contextgen-kai/
├─ README.md
├─ 仕様書兼要件定義書.md
├─ アプリ概要とバージョン履歴.md
├─ アプリ基本設計基準書.md
├─ contextgen改_操作マニュアル.html
├─ 起動.bat / start_windows.bat
├─ 更新.bat
├─ build_exe.bat
├─ requirements.txt / requirements.lock / pyproject.toml
├─ launch.py                       # EXE起動用
├─ contextgen_kai/                 # アプリ本体・画面
├─ ocr/                           # Gitに同梱するWindows用OCR・言語・ライセンス
├─ images/                        # 操作マニュアルの実画面
├─ docs/                          # 検証記録・証跡
├─ scripts/ / tests/ / packaging/  # 起動補助・試験・配布定義
└─ .venv/ / build/ / dist/         # 初回起動・ビルドで生成（Git管理外）
```

## できること

- 複数フォルダの差分更新と、ファイル選択・ドラッグ＆ドロップによる単発取り込み。
- Office・PDF・画像・テキスト・CSV・ZIPの出典付き抽出。混在PDFとOffice画像の日本語・英語OCR。
- 検索・絞り込み・原本確認、収録除外、抽出本文の訂正。原本更新時は訂正の競合を表示。
- 用途別資料セットを保存し、M365 TXT、Markdown、JSONL、出典、診断、差替一覧、指示文を生成。
- 毎日・曜日・間隔による定期更新。アプリ起動中とWindowsバックグラウンド実行の切替。
- 原本を変更しない世代保存、保留、停止・再開、設定と修正のバックアップ。

ブラウザを閉じても本体は動作します。完全に終了するときは画面の「アプリを終了する」を選びます。「アプリ終了後も実行」モードの予約は終了後もWindows側に残ります。Git更新の前にはバックグラウンド予約もいったん停止し、更新後に再開してください。

## 保存場所とバックアップ

Windows: `%LOCALAPPDATA%\ContextgenKai`。macOS: `~/Library/Application Support/ContextgenKai`。DBをBox/OneDrive等の同期フォルダへ移さないでください。入力資料は同期済みのフォルダを指定できます。オンラインのみのファイルは先に端末へ取得してください。

JSONバックアップには登録先、用途別セット、資料参照、利用者による本文修正、予約設定を含みます。**原本・抽出キャッシュ・出力世代は含みません**。原本は別途保管してください。復元は空の保存先へ行い、登録先のパスを確認・変更して読み取りを実行します。復元した予約は停止状態です。

出力世代は自動削除しません。保存容量は利用者が管理します。エラー、修正競合、前回からの収録量の大幅減少時は確認待ちとなり、既存世代が有効なまま残ります。

## macOS開発・試験

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
.venv/bin/python -m contextgen_kai
.venv/bin/python -m pytest -q
.venv/bin/python scripts/ui_smoke.py
```

同梱OCRはWindows用です。macOS開発時のOCRにはmacOS用Tesseract5とjpn/engを用意し、`CONTEXTGEN_TESSERACT` で実行ファイルを指定できます。Windows用EXEをmacOSでは選択しません。

`--state-dir <フォルダ>` で検証用保存先、`--port 8766` でポート、`--no-browser` でブラウザの自動起動を変更できます。OS予約は `--run-schedule <ID>` で同じ処理を実行します。Windows向けビルドはWindows上で `build_exe.bat` を実行します。

## 制約と権利

開発版です。Windows自動試験と、利用予定Windows11 PCでの最終受入は分けて記録しています。正式版1.0.0には昇格していません。

旧doc/xls/ppt形式は新形式への変換が必要です。図や写真の意味は解釈せず、文字をOCRします。資料のAI分析とCopilotへの投入は利用者が行います。自動アップロードや外部AI接続はありません。直接アップロード用パッケージは各セット20ファイル以内で、全量を一つのエージェントに無制限投入するものではありません。

新規部分は独立実装で、旧contextgenのソース・既存の権利表示を変更していません。新しい権利帰属・ライセンスの宣言はしていません。OCRのライセンス・ビルド出典は `ocr/`、EXE配布の依存ライセンスは `THIRD_PARTY_LICENSES/` に含めます。
