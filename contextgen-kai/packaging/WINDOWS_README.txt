contextgen 改 0.2.0（開発版） / Windows 11 64bit

1. ZIP を任意のフォルダにすべて展開します。ZIP 内から直接実行しないでください。
2. ContextgenKai.exe または 起動.bat をダブルクリックします。ブラウザでアプリ画面が開きます。
3. 「資料フォルダを登録」または単発ファイル追加から開始します。
4. 操作方法は contextgen改_操作マニュアル.html をブラウザで開きます。実画面の画像も同梱しています。

このEXE配布版ではPythonのインストールや初回のOCRダウンロードは不要です。
EXE と _internal、ocr、THIRD_PARTY_LICENSES、画像・マニュアルは一緒に保持してください。
この開発版は未署名です。既存 contextgen v3 のデータやファイルは変更しません。

Git利用の場合は、同じViniprjのcontextgen-kaiフォルダにOCR本体・日本語/英語データも含まれます。
既存cloneで更新.bat（git pull --ff-only相当）を使って更新します。ソース版の初回起動には
Python 3.12と依存関係の取得用インターネット接続が必要です。詳しくはREADME.mdを参照してください。
この配布ZIPには.gitがないため更新.batによるGit更新はできません。新しいZIPを別フォルダへ展開します。

通常の状態保存先: %LOCALAPPDATA%\ContextgenKai
ブラウザだけを閉じてもアプリ本体は動き続けます。アプリ画面の「終了」で終了してください。
「アプリ終了後も実行」は利用者ログイン中にWindowsタスクスケジューラが処理します。
電源OFF・スリープ・ログアウト中には実行しません。実行漏れは次回可能時に1回分を実行します。
配布フォルダを移動した場合は背景予約をアプリで保存し直してください。
バックアップは原本ファイルを含みません。復元した予約は停止状態になるため再設定してください。

OCRは文字認識です。図や写真の意味を説明する機能ではありません。
読み取り結果と出典を確認し、必要な資料だけCopilotにアップロードしてください。

アプリ直下の文書:
  仕様書兼要件定義書.md
  アプリ概要とバージョン履歴.md
  アプリ基本設計基準書.md
  contextgen改_操作マニュアル.html（画像: images\）
検証記録: docs\04_検証記録とWindows受入.md
第三者コンポーネントの権利表示: THIRD_PARTY_LICENSES\、ocr\licenses\、ocr\tessdata\LICENSE
Tesseract 5.5.1 / tessdata_fast（日本語・英語、固定コミット）
アプリのビルド来歴: BUILD-MANIFEST.json
OCRのビルド来歴とファイルのSHA-256: ocr\BUNDLE-MANIFEST.json

検証状態: Windows CIの成功と、利用予定のWindows PCでの受入確認は別です。
利用予定PCでの起動、フォルダ選択、125〜150%表示、定期実行を確認してください。
