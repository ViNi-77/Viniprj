# Presentation JSON 仕様書 v1.0

> 機械可読な定義は `schema/presentation.schema.json`（JSON Schema 2020-12）。本書は人が読むための補足。

## 1. 基本方針
- **単位**: すべて pt（1pt = 1/72 inch）。PPTX の EMU（12700 EMU = 1pt）と Web の px（1pt = 96/72 px）へ双方向に変換できる。
- **座標系**: 原点はスライド左上、x 右向き、y 下向き。`bbox = {x, y, w, h}`。
- **キャンバス**: 16:9 の既定値は 960 × 540 pt（13.333 × 7.5 inch）。
- **bbox: null**: 座標未確定（HTML 由来など）。`layout.py` が決定的に配置する。
- **画像**: `assets` に base64 で内包し、要素からは `asset_id` で参照。同一画像は SHA-1 で重複排除。
- **版**: `schema_version` は `1.x`。同一メジャー内は後方互換（新規フィールドは省略可）。

## 2. 構造

```
{
  "schema_version": "1.0",
  "meta":   { "title", "author", "created_at", "generator", "source": {"type": "pptx|html|manual|json", "filename"} },
  "canvas": { "width_pt": 960, "height_pt": 540, "aspect": "16:9" },
  "theme":  { "template_id", "fonts": {"heading", "body"}, "colors": {"primary","secondary","accent","background","surface","text","muted","line"} },
  "assets": { "<asset_id>": {"mime", "filename", "data_base64", "width_px", "height_px"} },
  "slides": [ <slide> ],
  "warnings": [ <warning> ]
}
```

### slide
| フィールド | 型 | 説明 |
|---|---|---|
| id | string | 一意。`s001` 形式。分割時は `s004_p2` |
| index | int | 0 始まりの並び順。保存時に振り直す |
| layout | enum | `title, section, title_body, two_column, three_column, image, table, blank` |
| title | string/null | 表示題名（目次・一覧用）。要素とは別に持つ |
| notes | string/null | 発表者ノート |
| background | {color} / null | 単色背景のみ |
| elements | element[] | 描画順は `z` 昇順 |
| warnings | warning[] | このスライドに関する警告 |

### element（共通）
| フィールド | 型 | 説明 |
|---|---|---|
| id | string | スライド内で一意 |
| type | enum | `text, image, shape, line, table, unsupported` |
| role | enum/null | `title, subtitle, body, caption, card, footer, header`。既定フォントサイズ・色の選択に使う |
| bbox | bbox/null | 座標。null は未確定 |
| z | int | 重ね順 |
| layout_hint | {column, columns} | 自動レイアウトの列指定（カード等） |
| editable | bool | 出力先で編集可能か |
| vertical_align | enum/null | `top, middle, bottom` |

### 型別フィールド
| type | フィールド |
|---|---|
| text | `paragraphs[]`, `fill`（任意の背景色） |
| shape | `shape`（rect / rounded_rect / ellipse）, `fill`, `stroke`, `stroke_width_pt`, `paragraphs[]` |
| image | `asset_id`, `alt`, `fit`（contain / cover / stretch） |
| line | `points[[x1,y1],[x2,y2]]`, `stroke`, `stroke_width_pt` |
| table | `rows[][]`（cell）, `header_rows`, `col_widths_pt[]` |
| unsupported | `original_type`, `alt`（表示用ラベル） |

### paragraph / run
```
paragraph: { "runs": [run], "level": 0-8, "bullet": "bullet"|"number"|null, "align": "left|center|right|justify"|null, "space_after_pt" }
run:       { "text", "bold", "italic", "underline", "size_pt", "color": "#RRGGBB", "font", "href", "inherited": ["size_pt","color","font","bold"] }
```
- `inherited` は、run に明示が無くマスター等の継承で補った属性名。テンプレート適用や出力時は「明示値は保持、継承値は上書き可」の判断に使う（PPTX 出力・Web 表示では継承フォント名を書かずテーマ既定に任せる）。
- `size_pt` / `color` / `font` が無い場合は `role` とテーマから既定値を決める（title 28pt、body 16pt、caption 12pt。`config/app_config.json` の `layout.*`）。

### cell
`{ "text", "paragraphs"(任意), "bold", "fill", "colspan", "rowspan", "align" }`。結合セルは起点セルのみ持ち、結合先は出力しない。

### warning
`{ "stage", "code", "message", "slide_id", "element_id", "fallback" }`。stage は `pptx_parser, html_parser, layout, pptx_generator, repair, quality_check`。

## 3. 検証と修復
- `validate.validate()` でスキーマ違反一覧を得る。
- `validate.repair()` は欠落キー補完、不正要素の除外、色の正規化（`#abc`, `rgb()` → `#RRGGBB`）、index 振り直し、段落・ラン・セルの型強制、bbox のキャンバス 2 倍への丸め、size_pt の範囲（0〜400）確認を行い、修復内容を warning で返す。
- API はすべて「検証 → 失敗なら修復 → 再検証」を通す。

## 4. 互換性の約束
- 未知のトップレベルキーは修復時に削除される（`additionalProperties: false`）。拡張はまず `meta` 配下に置く。
- 要素の未知フィールドは保持されるが、スキーマに無いため検証で警告になる。追加時はスキーマと本書を同時に更新する。
