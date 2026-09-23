# Git同梱OCR（Windows 11 / 64bit）

`git clone` または `git pull --ff-only` で、このフォルダもアプリと一緒に取得・更新します。
Git LFS・別ダウンロード・OCRの個別インストールは不要です。アプリから自動検出します。

- `tesseract.exe`: Tesseract 5.5.1。Windows x64、静的依存関係込み。
- `tessdata/eng.traineddata` / `jpn.traineddata`: 英語・日本語の認識データ。
- `licenses/` と `tessdata/LICENSE`: 第三者コンポーネントの権利表示。
- `BUNDLE-MANIFEST.json`: 全22個の実行時ファイル・権利表示のSHA-256、サイズ、ビルド来歴。

実行時ファイルと権利表示は合計17,538,000 bytes、最大ファイルは10,802,176 bytesです。
デバッグシンボル（PDB）は通常利用に不要なため含みません。macOSではこのWindows用実行ファイルは使わず、
`CONTEXTGEN_TESSERACT` で指定したOCRまたはmacOSのPATH上のTesseractを使います。

## 取得元・再現方法

このバイナリは[Windows CI 35801435958](https://github.com/ViNi-77/Viniprj/actions/runs/35801435958)
の検証済み配布ZIP（artifact 10726425648）から取り出したものです。
元のZIPのSHA-256、ビルド元コミットは `BUNDLE-MANIFEST.json` の `origin` に記録しています。
この由来情報はアプリの更新後も、OCRを再構築するまでそのまま保持します。

ビルドは[microsoft/vcpkg](https://github.com/microsoft/vcpkg/tree/ef7dbf94b9198bc58f45951adcf1f041fcbc5ea0)の
固定コミット `ef7dbf94b9198bc58f45951adcf1f041fcbc5ea0`、認識データは
[tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast/tree/65727574dfcd264acbb0c3e07860e4e9e9b22185)の
固定コミット `65727574dfcd264acbb0c3e07860e4e9e9b22185` です。
日本語・空白入りパスの処理に必要な `activeCodePage=UTF-8` を、元の実行権限情報を残してEXEのmanifestに追加しています。

通常のアプリ配布ビルドは `packaging/build_windows.ps1` がこのフォルダを検証・同梱します。
OCR自体を更新するときは、Windows上で固定コミットのvcpkgを用意して
`packaging/build_ocr_windows.ps1 -VcpkgRoot <vcpkgの場所>` を実行し、出力された `build/ocr-native/` を検証します。
採用する場合だけ、実体・権利表示・manifestをこのフォルダに置き換えてWindows CIで再検証します。

完全性の確認:

```console
python packaging/verify_ocr_bundle.py --root ocr
```

ライセンスや著作権の帰属をアプリ独自のものへ変更していません。各コンポーネントの原文は同梱の権利表示を参照してください。
