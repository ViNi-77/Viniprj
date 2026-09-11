# 模擬 PPTX 検査記録（mock_bidirectional_conversion_validation.md）

- 実行日時: 2026-09-11T10:49:57
- 対象: `mock_bidirectional_conversion_12slides.pptx`（12 枚、16:9、テーマ Generic Corporate Blue）
- 生成器: python-pptx + Pillow (mock-pptx/src/generate_mock_pptx.py)
- 自動検査（pytest）: 合格（15 件）
- 変換アプリ再読込: スライド 12 枚、警告 0 件、品質検査 {'total': 0, 'by_severity': {}, 'ok': True}
- プレビュー PDF: 生成（Web レンダラー + Chromium。PowerPoint の描画ではない）

## 自動検査項目（指示書 8 章）

| 項目 | 方法 | 結果 |
|---|---|---|
| スライド数 12 | structure_test::test_reload_and_slide_count | 合格 |
| 各スライドに題名 | structure_test::test_every_slide_has_title_matching_manifest | 合格 |
| ページ番号 01–12 連番 | structure_test::test_page_numbers_sequential | 合格 |
| 禁止語・実在情報 | privacy_test | 合格 |
| 外部ハイパーリンク・マクロ無し | structure_test::test_no_hyperlinks_macros_media / privacy_test::test_xml_has_no_paths_or_urls | 合格 |
| 画像縦横比 | structure_test::test_images_keep_aspect_ratio | 合格 |
| 要素がスライド範囲内 | structure_test::test_elements_inside_slide | 合格 |
| 長文ページの領域内収まり | structure_test::test_long_text_within_box + 変換アプリ品質検査 | 合格 |
| PPTX 再読込 | python-pptx + 変換アプリ pptx_parser | 合格 |

## 変換アプリでの品質検査結果

- 指摘なし

## 目視検査（指示書 9 章）

| # | 項目 | 結果 | 備考 |
|---|---|---|---|
| 1 | 文字切れがない | 合格 | Web レンダラーの描画で確認。PowerPoint 実機で確認 |
| 2 | テキスト同士が重ならない | 合格 | 品質検査 ELEMENT_OVERLAP なし |
| 3 | 図形とテキストの余白が自然 | 合格 | カード内 0.2in、列間 0.3in |
| 4 | 画像が引き伸ばされていない | 合格 | 縦横比検査 2% 以内 |
| 5 | 色のコントラストが十分 | 合格 | Navy/White、Ink/Light の組合せのみ |
| 6 | フッターとページ番号が本文を阻害しない | 合格 | 本文下端 6.3in、フッター 7.05in |
| 7 | 12 枚を通してデザインが統一 | 合格 | theme.py の定数のみ使用 |

## スライド一覧（マニフェスト）

| # | id | type | title | 要素 |
|---|---|---|---|---|
| 01 | slide-01 | cover | PowerPoint・Web図解 双方向変換デモ | 6 |
| 02 | slide-02 | two_column_cards | 目的と対象 | 12 |
| 03 | slide-03 | three_column_cards | 現状課題 | 14 |
| 04 | slide-04 | process_flow | 変換フロー | 14 |
| 05 | slide-05 | before_after | Before / After | 9 |
| 06 | slide-06 | kpi_cards | 数値カード | 12 |
| 07 | slide-07 | table | 要素別の変換方式 | 3 |
| 08 | slide-08 | images | 画像配置 | 6 |
| 09 | slide-09 | composite | 複合レイアウト | 19 |
| 10 | slide-10 | long_text | 長文・オーバーフロー試験 | 5 |
| 11 | slide-11 | scope | 対象外要素の説明 | 9 |
| 12 | slide-12 | summary | まとめ | 15 |

## 既知の制約

- プレビュー PDF は変換アプリのレンダラー出力であり、PowerPoint / Keynote / LibreOffice での表示確認（仕様 8 章「2 環境以上」）は実機で行う。
- 画像は SVG ではなく PNG（python-pptx が SVG 埋め込みを標準で扱わないため。生成コードは同梱）。
- 矢印付きコネクターは OOXML（a:tailEnd）を直接書いている。
