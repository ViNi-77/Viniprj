# 実装境界（0.3.0）

文書版 0.4 / 更新日 2026-09-24 / 状態: 実装・自動試験中。利用予定PCとCopilotでの手動受入は別途記録する。
旧v3とpptx-web-bridgeは変更しない。アプリはcontextgen_kaiで完結し、外部AI/APIを呼ばない。

## 読み取りと整理

extract_document(path, ocr=True, max_pages=500, timeout=60) -> Extraction。text/status/warnings/units/metadataを返す。
抽出形式版EXTRACTOR_VERSION=2。unitsはunit_id/locator/text/status/kind/hidden/source_refsを持つ。
kindはbody/table_row/metadata/note/image/embedded。table_headers/values/cells/formulas/clean_text/image_hash等を必要に応じて追加する。
原文textと抽出単位は非破壊で保存。formulasは保存済み値と式を分離し再計算しない。metadata.retryableが真なら無変更でも再試行する。
prepare_document(doc, collection)をプレビューと出力が共用し、original_text/text/units/raw_units/changes/before_chars/after_charsを返す。
raw_unitsは除外前の正規化単位。キーは資料ID:unit_id。全文修正の出典は文書全体（位置未特定）。類似文を自動削除しない。

## 保存と編集

catalog.sqlite3は追加型schema2移行。documents.revision、collection_options、edit_history、handoffsを追加。
既存セットはcleanup=none。新規API/UIセットはstandard。固定選択はID、動的選択は検索条件に追従する。
編集はexpected_hashとexpected_revisionを照合し、同時保存をSQLiteトランザクションで排他する。旧内容を履歴へ保存する。
原本または再抽出本文が変わった修正は確認待ち。原本には書き込まない。個別採否は原本hashと単位本文hashを基準に保存し、変化・基準欠落・位置消失時は原文を保持して再確認まで確定を止める。

## HTTP

全更新にGET /api/statusで得たX-Contextgen-Tokenが必要。localhost/Origin制約を維持する。
GET /api/documents: library_id,q,status,extension,offset,limit。本文抜粋のみを一覧へ送る。
GET /api/documents/{id}: 原文・修正文・単位・revision。PUT: text?,excluded?,expected_hash,expected_revision。
GET /api/documents/{id}/history、POST /reextract。PDF/画像previewと原本openは登録済み資料に限定。
collections: name,library_id,library_ids,selection_mode,query,folder,document_ids,excluded_document_ids,purpose,instructions,target,cleanup,include_hidden,include_notes,include_embedded,unit_overrides,unit_override_bases,audience,answer_scope,out_of_scope,description,evaluation_questions。
POST /api/collections/preview: 未保存セットの候補（offset/limit）。POST /api/collections/{id}/preview-document: document_idと任意options（未保存設定）。GET /preflight: 原本属性と警告。
POST /api/exports: collection_id,force=false,refresh_sources=true。生成前に登録元の追加・削除・内容hashを照合する。
GET /api/exportsにはfile_count/target。POST /{id}/activateは原本・設定・修正・manifest/hashを再確認して切替。
GET /api/exports/{id}/handoff: 登録対象/変更/削除。POST同API: filesとremoved。部分記録は未変更の登録済みファイルを保持。
GET /api/backupはschema2 JSON（上限512MB）。POST /restoreはschema1/2を空領域へ復元。原本・抽出キャッシュ・出力本体は含まない。
その他libraries/uploads/jobs/stop/resume/schedules/shutdownは従来APIを維持。

## 生成と受け渡し

Builder: TXT INDEX+本文最大19ファイル/セット。複数セットは別の登録範囲であり単一エージェントの20件上限を増やさない。
Studio: Markdown、INDEX込み500件/各512MB。上限超過はforceでも公開不可。
全分割に資料ID/相対ファイル名/抽出位置/全参照元/必要な表見出しを付ける。
instructions.txt、knowledge-descriptions.md、registration-guide.md、読取/健康診断/未収録/出典JSONL、整理差分、登録済み基準のupload-changesを含む。
利用者が入力した評価質問を保存。Studio用CSVの列はQuestion,Expected response（100問、質問1000文字まで）。生成・採点は行わない。
有効世代は検査後にDBで切替。確認待ち・失敗時は前回出力を保持。登録記録は外部サービスの状態を検証したものではない。

## 予約・配布・文書

Scheduler(state_dir, callback)は別schedules.sqlite3。既存app/backgroundモードを維持。複数登録元のセットは当面手動生成。
復元は設定・編集履歴・登録記録と停止した予約を同一処理で戻す。Windows予約のOS登録は明示保存時のみ。
Windows配布はEXE/HTML/最初にお読みください.txt/_internalの4点。OCR日本語英語・画像・画面資源・権利表示を同梱。
Windows上でビルド・EXE起動・OCR・予約・UI・manual file/HTTP/printを確認。マニュアル画像はWindows実アプリと合成サンプルから撮影する。
README/要件定義書/概要と履歴/設計基準/HTMLを同時更新し、ローカル試験・CI・実機・Copilot実利用を分けて記録する。
