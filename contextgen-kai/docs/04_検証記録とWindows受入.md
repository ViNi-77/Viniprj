# 検証記録とWindows受入

対象: contextgen 改 0.3.0 / 文書版0.4 / 2026-09-24

## 0.3.0 検証の進行状況

2026-09-24、ローカルの統合試験を実施。Windows配布物を検証中。以下の過去版実績は0.3.0の合格を意味しない。

- ローカル: 実OCRを含む全自動試験142件成功、Windows専用1件スキップ。[結果](evidence/local-tests-0.3.0.json)。
- 1万件: 初回49.093秒、無変更1.555秒（再抽出0件）、20件変更1.806秒（再抽出20件）。検索40回の95%点19.699ms。一時テキスト資料の測定で、画像主体の業務資料の所要時間を保証しない。[測定](evidence/local-benchmark-10000-0.3.0.json)。
- 旧プロジェクト: ソース差分0。同一旧PPTXソースで[Linux CI再実行](https://github.com/ViNi-77/Viniprj/actions/runs/35827127899/attempts/2)の単体73件・E2E18件・UI34件成功。
- マニュアル: 合成Word・正式テーブル付きExcel・単発資料を実アプリで操作し、ローカル撮影18枚。HTML掲載17画像・21リンク、file/HTTPの画像拡大、5幅、印刷25ページを確認。横溢れ・外部リクエスト・ブラウザエラー0。ローカル記録は `artifacts/manual-0.3.0-source/verification.json`。配布用はWindowsで再撮影し、配布EXEによる検証を別途行う。
- Windows CI: 新版は未確認。配布物の実行・OCR・タスク予約・マニュアルの結果を別途記録する。
- 利用予定Windows11 PC: 未実施。125〜150%表示、実業務資料、Builder/Studioでの手動登録と出典確認は利用先で実施する。

| 追加受入項目 | 検証場所 |
|---|---|
| 両profile・全5用途・説明項目・評価CSV | `tests/test_export_profiles.py` |
| 整理なしの原文維持、完全一致の集約・全参照、採否 | `tests/test_export_profiles.py` |
| 全分割の位置・表見出し、全文修正の位置未特定 | `tests/test_export_profiles.py` |
| 未投入/一部投入を基準にした追加変更削除 | `tests/test_export_profiles.py` とAPI統合試験 |
| Studio上限で全成果物保持、強制確定拒否 | `tests/test_export_profiles.py` |
| 混在PDF・Excel保存値・未読再読・revision競合 | 抽出・APIの追加試験 |

## 0.2.1 配布整理の検証

利用者ZIPを4点構成へ整理し、開発情報をソース側に分離。HTMLマニュアルをZIP展開からの手順へ変更。Windows上で画面画像を撮影する工程を追加した。利用予定Windows11 PCの受入は未実施。

- ローカル自動試験: 79件成功・Windows専用1件スキップ（ライセンス収集の新規6件を含む）。実OCR、APIのsource/frozen両配置、実行時ライセンスの保持とコード誤混入拒否を含む。
- マニュアル: 実画像13枚、内部リンク21件。5画面幅・拡大・HTTP表示・オフライン表示・印刷を確認。
- 旧PPTXアプリ: ソース差分0を確認した上で[既存CIループを再実行](https://github.com/ViNi-77/Viniprj/actions/runs/35815961908/attempts/2)。2026-09-23、全工程成功。v3とpptx-web-bridgeを編集していない。
- [Windows CI 35826419586](https://github.com/ViNi-77/Viniprj/actions/runs/35826419586)（6fa344a、Windows Server2022 / Python3.12）成功。80件成功・失敗0・スキップ0。
- Windowsで合成資料を操作し、マニュアル画像13枚を撮影。資料登録先は撮影用の `C:\ContextgenKai-Example`。個人資料・個人のパスは使用していない。[撮影記録](evidence/manual-capture-0.2.1.json)。
- 新ZIPの入口4点、OCRの内部配置、開発文書・来歴・外出しPythonソース・キャッシュ・デバッグ記号・Macメタデータの非同梱を確認。実EXEの抽出・自動出力・日本語/英語OCR・アプリ終了後の実Windows予約まで9項目成功。[配布試験](evidence/windows-smoke-0.2.1.json)。
- 配布EXEのHTMLマニュアルをfile://と実EXEのHTTP配信の両方で検査。13画像・21リンク・拡大・5画面幅・印刷19ページ、外部リクエスト0・ブラウザエラー0。[配布マニュアル検証](evidence/manual-packaged-windows-0.2.1.json)。
- ソースからのclone直後の起動・OCR・依存再取得なしの再起動・実行中の更新拒否も継続成功。[clone試験](evidence/windows-clone-smoke-0.2.1.json)。
- 完成ZIPを実アーカイブから再監査。41項目成功、外出しPythonソース/キャッシュ/デバッグ記号/Macメタデータ/開発資料0、画像13枚にメタデータなし、実収録の第三者コンポーネントと権利表示を照合。[配布内容の監査](evidence/distribution-audit-0.2.1.json)。
- ビルド来歴は利用者ZIPに含めず、[開発者用記録](evidence/windows-build-0.2.1.json)へ保持。初回CIで発見した新規テストのCRLF比較の不一致は、実ファイルとHTTPのバイト列比較に修正して解消。

## 0.2.0 追加検証

Git同梱OCR、初回準備、既存clone更新、画像付きマニュアルを追加。以下の0.1.0実績と区別する。利用予定Windows11 PCの受入は未実施。

### macOS / 2026-09-23

- Python3.12.13で73件成功。Windowsジャンクション1件のみ対象OS外としてスキップ。実際の英語・日本語OCRを含む。

- OCR実行ファイル・言語データ・ライセンス22ファイル（17,538,000 bytes）のSHA256とサイズを照合。改変・欠落・保存先逸脱を拒否する試験を追加。
- 実Gitのローカルbareリポジトリでfast-forward更新、ローカル変更保持、履歴分岐の拒否を確認。
- 実プロセスの共有・排他ロックで、背景処理と同期済み起動の共存、実行中の更新拒否を確認。
- 4画面の実操作（合成資料57件）、1093×614/1280×720で横溢れなし、ブラウザ例外0。[画面証跡](evidence/macos-ui-0.2.0.json)。
- マニュアル実画面13枚・ローカルリンク26件。file://とHTTP配信の双方で全画像・画像拡大が動作。外部リクエスト0、HTTP consoleエラー0。1440/1280/1093/760/390幅で横溢れなし。印刷PDF20ページの本文も確認。[証跡](evidence/manual-0.2.0.json)。
- 旧PPTXアプリの無変更コピーでLinux既存ループを再実行。pytest73件、E2E18件、UI34件すべて成功。旧2プロジェクトのGit差分は0。

### Windows / 2026-09-23

[CI実行35815655542](https://github.com/ViNi-77/Viniprj/actions/runs/35815655542)（122d095、Windows Server2022 x64 / Python3.12.10）で次が成功した。

- 同梱OCRを使用する自動試験74件成功、失敗0・スキップ0。
- 実Git cloneの日本語・空白入りパスからBATで初回仮想環境作成・固定依存導入。再起動はpip呼出しを禁止しても成功。
- cloneしたOCRの自動選択と画像文字抽出、アプリ実行中の更新拒否、終了後のロック解放を確認。[Git取得検証8項目の証跡](evidence/windows-clone-smoke-0.2.0.json)。
- 同梱EXEを開発Python/OCRのPATHなしで起動。Office・混在PDF・画像・ZIPをエラーなしで抽出し、強制確定なしの出力を確認。
- 配布ルートの3文書・README、HTMLマニュアル・13画像・操作JSが、実ファイルとアプリからのHTTP取得で一致。
- 実Windowsタスク登録、アプリ終了後の読み取りと出力、予約解除まで確認。[配布物・OS予約の証跡](evidence/windows-smoke-0.2.0.json)。
- EXE・OCR・文書・マニュアルを含むWindows配布ZIPを生成。利用予定Windows11 PCでの最終受入は別途必要。

初回の配布検査では、Windowsの改行変換と動的な画像拡大枠を試験側が誤判定した。ファイルのバイト列照合と掲載画像の識別に修正し、同じ配布文書の検査をローカルAPI試験でも実行してから再検証した。

## 自動試験

| 領域 | 対応要件 | 試験 |
|---|---|---|
| Office/PDF/画像/埋め込み/ZIP/OCR | FR02/03 | tests/test_extractors.py |
| 登録・変更・出力・復元・localhost制約 | FR01/04/05/06/10 | tests/test_api.py |
| 差分・再開・競合・世代保護 | FR04/07/09 | tests/test_workflow.py |
| 予約・OS操作失敗・二重実行 | FR08 | tests/test_scheduling.py |
| 4画面・実操作・小型PC | FR01/04/05/08/10 | scripts/ui_smoke.py |
| 1万件・差分20件・検索 | FR09 | scripts/benchmark_10000.py |
| 配布EXE・OCR・OS予約 | FR03/08/11 | scripts/windows_smoke.py / GitHub Actions |

### 0.1.0 / 2026-09-23 macOS実績

- macOS26.6.2 arm64 / Python3.12.13: 自動試験59件成功、Windowsジャンクション1件のみ対象OS外としてスキップ。実際の英語・日本語OCR、混在PDF、Office内画像も成功。
- ローカルの実HTTPサーバーとChromeによる画面操作: 合成資料57件を使い、登録、移動、抽出、修正、出力ZIP、予約操作、バックアップを通過。ブラウザ例外0件。4画面とも1093×614/1280×720で横溢れなし。
- 1万件の生成UTF-8資料（計7.18MB）: 初回42.482秒、変更なし1.439秒・再抽出0件、20件変更1.675秒・再抽出20件。検索40回のp95は14.826ms、分割一覧の最大0.968ms。
- 親プロセス最大RSS35.9MB、完了した解析子プロセス28.5MB。別々の最大値であり、同時使用量の合計とは扱わない。Office/OCR主体の資料やWindows実機の速度を示す結果ではない。
- 停止・再開、修正競合、本文文字数だけが大幅減少した世代の保留、容量不足、原本範囲外へのリンク差替、バックアップ内の不正ID、出力の世代保護を回帰試験で確認。

機械可読記録: [1万件測定](evidence/macos-benchmark-10000.json) / [画面試験](evidence/macos-ui.json)。画面キャプチャ自体は開発端末の試験成果物に保存し、JSON内のファイル名はその成果物を指す。

### 旧プロジェクトの保全

旧2プロジェクトへのGit差分なし。既存PPTXアプリは一時コピーで検査し、元の実装・試験37ファイルのSHA256一致を確認した。macOSでは既存のポート判定試験1件が失敗したため、元コードを変更せずLinuxコンテナ（Python3.11.16、Playwright1.63）で `python scripts/loop.py` を実行。pytest73件、E2E18件、UI34件すべて成功、終了コード0。失敗した試験の無効化・スキップは行っていない。

### 0.1.0 Windows自動試験

[CI実行35800929238](https://github.com/ViNi-77/Viniprj/actions/runs/35800929238)（コミット7c136ca、Windows Server2022 x64 / Python3.12）で、EXE・OCRビルドと同梱OCRを使う60件の試験が成功した（失敗0・スキップ0）。

配布一式を日本語・空白入りフォルダへ移し、開発用Python/OCRのPATHを除いた状態で次を確認した。

- 同梱OCRで日本語・英語の文字認識が成功。
- 配布EXEがローカル画面/APIを提供し、Office・文字/画像混在PDF・画像・ZIPの7資料をエラーなしで抽出。
- 出力が手動の強制確定を使わず自動確定し、ZIPを取得。
- 実際のWindowsタスクスケジューラへInteractiveToken・通常権限で予約登録。
- アプリ終了後にOS予約が走査と出力を完了し、履歴へ結果を記録。試験後に予約解除。

[機械可読証跡](evidence/windows-smoke.json)。初回の配布試験で検出した日本語パスの文字化けは、既存manifestを保持したUTF-8コードページ設定で解消した。本文文字数の急減ガードも含めて成功している。最新の実行結果は[専用CI一覧](https://github.com/ViNi-77/Viniprj/actions/workflows/contextgen-kai.yml?query=branch%3Acodex%2Fcontextgen-kai)から確認できる。

Windows CIは実際の利用予定Windows11 PCとは別環境。ダブルクリックからの既定ブラウザ起動、フォルダ選択、表示倍率、Box/OneDrive等の実運用は下記の実機受入で確認する。1.0.0へは昇格していない。

## 利用予定Windows PCでの最終確認（未実施）

1. Windows11 x64、CPU、メモリ、ブラウザ、表示倍率とアプリ版を記録する。
2. Pythonを利用しない状態で配布ZIPを展開し、EXEをダブルクリックして画面が開くことを確認する。
3. 日本語・空白を含むフォルダを選び、Word・Excel・PowerPoint・文字PDF・日本語画像PDFを実行する。
4. 原本と抽出内容を比較し、OCRを訂正して保存。原本更新・再実行で競合が確認できることを確かめる。
5. Copilot用セットを生成し、INDEX・本文・出典・指示文を確認する。ダミー資料の一組をCopilotへ投入し、出典付きで参照できることを確認する。
6. アプリ内予約とバックグラウンド予約を切替え、アプリ終了後の実行、次回予定、二重実行防止、解除を確認する。
7. Box/OneDriveのオンラインのみ資料、同期中のファイル、ネットワーク不通時の状態表示を確認する。
8. 125%・150%で画面を操作し、ダイアログの閉じる・保存ボタンが常に利用できることを確認する。
9. バックアップを別の空保存領域へ復元し、原本参照と修正を確認する。予約が勝手に有効化されないことを確かめる。

## 受入記録欄

- 確認者・日時: 未実施
- PC構成・表示倍率: 未確認
- 配布物のコミット・SHA256: 未記入
- 合否と残件: 未実施。1.0.0へ昇格していない
