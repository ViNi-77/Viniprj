# 同梱フォント（subset 済み woff2）

`index.html` は 2 つのビットマップ風フォントを `@font-face` の `data:` URL で同梱する。ここにあるのは
元フォントから必要な文字だけを抜いた **subset**。元の TTF は `tools/fonts/`（`.gitignore` 済み）に各自置く。

| CSS family | ファイル | 元フォント | 役割 |
|---|---|---|---|
| `PM12` | `PixelMplus12-sub.woff2` | PixelMplus12-Regular.ttf（itouhiro / M+ FONTS 派生） | 本文・会話・メニュー。利用者が打つ名前も出すので広め |
| `DG16` | `DotGothic16-sub.woff2` | DotGothic16-Regular.ttf（Fontworks） | タイトル・見出し。小さく保つ |

CSS の family 名は独自（`PM12` / `DG16`）で、元のフォント名は名乗らない（OFL の Reserved Font Name に触れないため。後述）。

## 作り方

```bash
# 1. 元 TTF を置く（gitignore 済み。配布元から取得する）
#    tools/fonts/PixelMplus12-Regular.ttf  https://github.com/itouhiro/PixelMplus （releases の zip）
#    tools/fonts/DotGothic16-Regular.ttf   https://github.com/fontworks-fonts/DotGothic16 または Google Fonts
# 2. subset を作り直して、そのまま index.html を組む
python scripts/build.py --subset
```

`--subset` は `fontTools`（4.68 で確認）と `brotli` が要る（`pip install fonttools brotli`）。通常の
`python scripts/build.py` / `--check` / `--dev` は標準ライブラリだけで動き、ここにある woff2 を読むだけ。

内部では `fontTools.subset.main()` を次の引数で呼ぶ（`pyftsubset` の CLI と同じ）:

```
pyftsubset tools/fonts/<元>.ttf --output-file=src/fonts/<名>-sub.woff2 --unicodes=<下記の符号位置>
  --flavor=woff2 --no-hinting --desubroutinize --layout-features='' --drop-tables+=DSIG,FFTM
  --no-recalc-timestamp --name-IDs+=13,14
```

- `--no-recalc-timestamp`: `head.modified` を触らないので、同じ入力なら同じバイト列になる（2 回作って SHA-256 が一致することを確認済み）。
- `--layout-features=''`: GSUB/GPOS の機能を全部落とす（縦書き・合字は使わない）。
- `--drop-tables+=DSIG,FFTM`: 署名（subset すると無効になる）と FontForge の時刻表を捨てる。
- `--name-IDs+=13,14`: 既定で残る著作権表示（ID 0）に加えて、ライセンス記述と URL の name レコードも残す。

## 収録範囲

`scripts/build.py` の `pm12_unicodes()` / `dg16_unicodes()` が正。元フォントに無い符号位置は黙って飛ばされる。

### PM12（本文）

- U+0020–007E（ASCII）、U+00A1–00FF（Latin-1 記号）
- U+2010–2312（句読点・矢印・数学記号・罫線前の技術記号）、U+2460–24FF（①〜）、U+2500–25FF（罫線・ブロック・▶▼など）、
  U+2600–266F（★☆など）、U+2700–27BF（装飾記号。❶–❿ を狙ったが元フォントに無い。下記）
- U+3000–303F（和文記号）、U+3041–309F（ひらがな）、U+30A0–30FF（カタカナ）、U+FF01–FF9F（全角英数記号・半角カナ）
- **JIS 第一水準漢字 2,965 字** = cp932 の 16〜47 区（0x889F〜0x9872 の 2 バイト符号を 1 つずつ `cp932` で復号）。
  利用者が名前に打つ漢字をおおむね出すため。
- 加えて `src/data` `src/svg` `src/js` の全 `.js` の**文字列リテラル**に現れる文字（コメントと正規表現は除く。`\uXXXX` は復号）。

### DG16（見出し）

- U+0020–007E、U+3000–303F、ひらがな、カタカナ、U+FF01–FF65（全角記号・英数、半角句読点「。「」、・」）
- ❶–❿（U+2776–277F）、★☆
- 加えて上と同じ文字列リテラル走査の文字（見出しに漢字を使うと、その分だけ増える）

## 元フォントに無い字（game 側でフォールバックすること）

`--subset` 実行時に表示される。現時点:

| フォント | 無い字 | 備考 |
|---|---|---|
| PM12 | ❶–❿（U+2776–277F）全部 | 本文で丸数字を使うなら ①–⑩（U+2460–2469、収録あり）か DG16 に切り替える |
| PM12 | ✓ – 〜 〖〗〘〙 〻 ゕ ゖ | ソースの文字列に出てくるが元に無い。〜（U+301C）は ～（U+FF5E）なら出る |
| DG16 | ❿（U+277F）、▶（U+25B6） | ❶–❾ はある。❿ だけ別扱い、▶ は PM12 で描く |

ブラウザは無い字をシステムフォントで補うので文字化けはしないが、ドット絵の見た目が崩れる。

## subset が古くなる条件

ソースの文字列に新しい字（たとえば見出しの漢字）を足すと、その字は subset に入っていない。
`--subset` は要求した符号位置を `subset.json` に記録し、通常ビルドはそれと現在のソースを突き合わせて
「subset が古い」と警告する（fontTools なしで判定できる範囲。警告が出たら `--subset` を回してコミットする）。
`subset.json` は手で編集しない。

## 大きさ（現時点。ソースの文字列が増えると変わる）

| ファイル | woff2 | base64（index.html 内） | 収録 |
|---|---|---|---|
| `PixelMplus12-sub.woff2` | 134.7 KB | 179.6 KB | 3,672 字（要求 5,060） |
| `DotGothic16-sub.woff2` | 25.9 KB | 34.5 KB | 637 字（要求 685） |

## ライセンス

全文は `LICENSES/` にあり、`build.py` が index.html の `<style>` 直後に HTML コメントとして**原文どおり**同梱する
（行末の CRLF だけ LF に揃える。本文は変えない）。

- **PixelMplus** — M+ FONT LICENSE（`LICENSES/PixelMplus-LICENSE_E.txt`）。改変の有無・商用非商用を問わず、
  使用・複製・配布が無制限に許される。無保証。
- **DotGothic16** — SIL Open Font License 1.1（`LICENSES/DotGothic16-OFL.txt`）。改変版の配布は許されるが、
  **Reserved Font Name「DotGothic16」を改変版の名前に使ってはならない**（OFL 第 3 条）。
  このプロジェクトでは CSS の family 名を `DG16` とし、フォント内部の名前も変更しないままにしている
  （subset はフォントの「改変」にあたり、OFL は改変版にフォント本体の著作権表示とライセンス全文の同梱を求める。
  上記の HTML コメントと name レコード 0/13/14 の保持がそれ）。フォント単体での販売は禁止だが、ゲームに同梱して配布するのは問題ない。

subset 化は、どちらのライセンスでも許されている「改変」の範囲。
