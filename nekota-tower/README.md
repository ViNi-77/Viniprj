# ねこ太と十二月の塔 — 年末クエスト

架空の携帯機 **NETTA BOY** で動く、1 ファイルのレトロ風クエストゲーム。
「年末までにやり切る 10 のミッション」を**現実でこなして**、塔の長老に報告すると しるし が増える。
ビルドなし・通信なし。`index.html` をダブルクリックするだけで遊べる（PC 向け。主に Edge で確認）。

> NETTA BOY、NETTA、ゲーム部は この作品のための架空のハード・メーカー・ブランドです。実在の企業・製品とは関係ありません。

## 遊び方

| 操作 | キー |
|---|---|
| 移動 | 矢印 / WASD（クリックした場所へ歩くこともできる） |
| けってい・話す | Z / Enter / Space |
| やめる・とじる | X / Esc |
| メニュー | C |
| ダッシュ | Shift を押しながら移動 |

1. 電源を入れ（任意のキー）、タイトルで **はじめから**。なまえを入れて きろく（セーブ枠）を選ぶ。
2. 10F から塔を降りる。各階の依頼人に話しかけると クエスト を受けられる。
3. クエスト画面は **じゅんび**（いつ・どこで・どうやって、リスト）→ **じっこう**（現実でやったら押す）→ **ほうこく**（条件がそろったら長老へ）。
4. 3 つの しるし で合格。1F の扉がひらく。
5. **石碑** に触れると きろく できる。本体メモリは 3 枠。

10 のクエストすべてが遊べる。① は 1F の奥の部屋で「10 分なにもしない」ボス戦（さわるとボスが回復する。X でいつでも中断でき、失敗にはならない）。① をクリアして長老に話すとエンディング（スタッフロール）が見られる。トゥルー／バッドエンディングと 2 周目は次の版。

## セーブについて

- **本体メモリ**：ブラウザの保存領域（localStorage）に 3 枠。手動セーブのみ。未保存で閉じようとするとブラウザの確認が出る。タブを隠したときは「ちゅうだんデータ」を自動で残す。
- **メモリーカード**：タイトルまたはメニューの「メモリーカード」から、きろくを **ひらがなの呪文で書かれた CSV** に書き出せる（`nekota-tower_card_YYYYMMDD_slotN.csv`）。別の PC へ持ち運ぶとき、ファイルを移動するときはこちらを使う。中身は暗号化してあり、1 文字でも書き換えると読めなくなる（鍵は HTML に埋め込んであるので、秘密を守る仕組みではなく「読めなくする」仕組み）。任意で あいことば（パスワード）を付けられる。
- **注意**：Firefox は `index.html` の置き場所ごとに保存領域が分かれる。ファイルを移動・改名すると本体メモリは見えなくなるので、だいじな きろくは メモリーカードへ。

## 開発

```
nekota-tower/
├── index.html          ビルド生成物（コミットする。手で編集しない）
├── src/                ソース（css / data / svg / js / fonts / index.tpl.html）
├── scripts/build.py    src/ を連結して index.html を作る（標準ライブラリのみ）
├── scripts/ui_smoke.py 画面検査（Playwright）
├── scripts/codec_test.mjs  メモリーカードの暗号コーデックの単体試験（node --test）
├── docs/               01 要件定義 / 02 設計 / 04 受入試験 / 11 引き継ぎ / 99 意思決定ログ
└── LICENSES/           同梱フォントのライセンス
```

```bash
cd nekota-tower
python scripts/build.py            # src/ → index.html
python scripts/build.py --check    # index.html がソースと一致するか（CI 代わり）
python scripts/build.py --dev      # dev.html（src を直接読む。開発中の反復用）
node --test scripts/codec_test.mjs # コーデックの単体試験
pip install playwright && python scripts/ui_smoke.py   # 画面検査（playwright install は不要。ブラウザは /opt/pw-browsers から探す）
```

フォントを作り直すときは `tools/fonts/` に `PixelMplus12-Regular.ttf` と `DotGothic16-Regular.ttf` を置いて `python scripts/build.py --subset`（fontTools が必要）。手順は `src/fonts/README.md`。

### ライセンス

- 本文フォント **PixelMplus12**（M+ FONT LICENSE）、見出しフォント **DotGothic16**（SIL Open Font License 1.1）をサブセット化して同梱。全文は `LICENSES/`。
- ねこ太・依頼人・音・絵はすべてこのリポジトリのオリジナル。
