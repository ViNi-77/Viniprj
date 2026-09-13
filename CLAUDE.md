# Viniprj で開発するときの約束

小規模な業務改善ツールを 1 つのリポジトリで管理する。**このリポジトリが唯一の開発拠点**（以前使っていた private リポジトリ `ViNi-77/Aisin` は Phase D 相当で凍結済み。あちらのブランチは使わない）。

| フォルダ | 中身 | 主な入口 |
|---|---|---|
| `pptx-web-bridge/` | PowerPoint ⇄ Web図解 双方向変換アプリ（FastAPI + 素の JS、ローカル起動） | `start_windows.bat` / `./start.sh` / exe 版 |
| `copilot-context-generator/` | M365 Copilot 用ナレッジ生成ツール（contextgen） | `work1_improvement/` が本体、`work2_cross_ai/` が横展開 |

現在地・完了範囲・未実施の手動確認は **[`pptx-web-bridge/docs/11_引き継ぎ.md`](pptx-web-bridge/docs/11_引き継ぎ.md)** を先に読む。

---

## 1. コミット前に必ず通すもの

```bash
cd pptx-web-bridge && python scripts/loop.py
```

pytest → 模擬 12 枚 PPTX の生成と検査 → 往復 E2E → UI スモーク（Playwright）を順に回し、1 つでも落ちたら `=== 不合格: 修正して再実行 ===` で止まる。**全部緑になるまでコミットしない。** 実装中の高速反復は `--quick`（pytest だけ）、記録に Issue を残すなら `--issue X`。

「試験が落ちたから試験を飛ばす／無効にする」は禁止。落ちた理由を直す。

## 2. ブランチと PR

- ブランチ名は `feat/<topic>` / `fix/<topic>` / `chore/<topic>`。
- **PR の base は必ず `main`。ブランチを積まない（スタックしない）。**
  - 一度これで事故っている: PR #6〜#8 を積んで、途中の PR を先にマージした結果 Phase F/G が `main` から丸ごと漏れた。復旧に PR #9 が要った。
  - 複数の PR が並ぶときは **番号の小さい順にマージ**し、マージ後に `git merge-base --is-ancestor <各コミット> origin/main` で全部入ったことを確かめる。
- ユーザーは細かいレビューを望まない。**指示があればこちらでマージまでやる**（ドラフトで出す → `draft: false` → merge）。

## 3. コミットの作法

```bash
git -c user.name="ViNi-77" -c user.email="103969841+ViNi-77@users.noreply.github.com" \
    commit -F <メッセージファイル> \
    --author="ViNi-77 <103969841+ViNi-77@users.noreply.github.com>"
```

- **ユーザーのメールアドレスを git config に書かない**（`-c` で都度渡す）。
- メッセージは日本語で「**症状 → 原因 → 対処**」。何を直したかではなく、なぜそれで直るのかが分かるように書く。
- 末尾に `Co-Authored-By:` と `Claude-Session:` を付ける。**モデル名をコミットや PR、コード中に書かない。**

## 4. 版（バージョン）は必ず上げる

`backend/app/version.py` の `APP_VERSION` と `FEATURES` を、機能を足すたびに更新する。

画面右上の「版 0.5.0 (コミット)」バッジと `/api/version` が、利用者にとって**「更新できているか」を確かめる唯一の手掛かり**。ここを忘れると「アプデしたのに変わらない」という報告に戻る。過去の原因は次の 3 つで、いずれも対策済み:

1. 古いサーバーがポート 8765 に残っていて、ブラウザが古い画面を開いていた → `backend/run_server.py` の `port_in_use` / `occupant_is_this_app` / `pick_port` が検知して警告し、別ポートへ逃げる。
2. ブラウザキャッシュ → JS/CSS の URL に `?v=<asset_tag>`、`/` に `Cache-Control: no-store`。
3. クローンが古い → バッジのコミットと `git log --oneline -1` を突き合わせてもらう。

## 5. この環境の制約（引っかかりやすい順）

- **CDN が塞がれている。** `cdn.jsdelivr.net` / `unpkg` / `cdnjs` は proxy が 403 を返す。フロントの外部ライブラリは `registry.npmjs.org` の tarball から取って **`frontend/vendor/` に同梱**する（現在: Pico.css 2.0.6 / Split.js 1.6.5。ライセンスは同フォルダの README に）。
- **Playwright のブラウザは `/opt/pw-browsers` に入っている。`playwright install` を実行しない**（`PLAYWRIGHT_BROWSERS_PATH` が設定済み）。
- **exe には Playwright を同梱しない**（`packaging/pptx-web-bridge.spec` の `excludes`）。Node.js ドライバが約 120MB あり、配布物が肥大化して展開先のパス長・ウイルス対策の誤検知を招く。無ければ `rasterize.is_available()` が False を返して編集性優先モードへ自動代替されるので機能は落ちない。
- タグの push と `workflow_dispatch` は権限が足りず 403 になることがある。exe は `build-windows` が `main` への push で自動実行し、`dist/windows` ブランチに最新 1 件が置かれるので、そこから取る。

## 6. 画面の受入ライン

利用者は**ノート PC**（Windows の 125〜150% 表示）で使う。

- 文字・ボタンが切れないこと、横スクロールが出ないことが受入条件。`scripts/ui_smoke.py` の `laptop_checks` が 1366×768@125%（1093×614 CSS px）と 1920×1080@150%（1280×720 CSS px）の 2 構成で守っている。
- CSS は px 固定にしない。`rem` / `clamp()` / `dvh` を使い、寸法の土台は Pico.css の CSS 変数に乗せる。
- モーダルは `<dialog>`。**保存・キャンセルは `<footer>` に固定**し、スクロールするのは本文だけ（`frontend/ui.js` の `openModal` / `bindModal`）。過去に「保存ボタンが見切れてスクロールもできない」で使えなくなっている。
- キャンバスの拡縮は `ResizeObserver` に任せる（手で `fit()` を呼ぶ設計にしない）。

## 7. 機密の扱い

- このアプリは**資料の本文をそのまま Copilot に貼る**前提。社外秘の資料は**社内テナントの M365 Copilot でのみ**使い、外部の AI サービスには貼らない。README と `docs/03` に同じ注意を書いてある。
- **このリポジトリは public**。追加するファイルに認証情報・トークン・社内ホスト名・個人情報が混ざっていないか、追加前に確認する。

## 8. 文書の置き場

`pptx-web-bridge/docs/` の番号は固定。変更を入れたら該当するものを同じ PR で更新する。

| 番号 | 中身 | 更新するとき |
|---|---|---|
| 00–01 | 初回レビュー / 要件定義 | 要件が変わったとき |
| 02 | Presentation JSON 仕様 | スキーマにフィールドを足したとき |
| 03 | 変換マッピング仕様 | 取込・出力・着せ替えの規則を変えたとき |
| 04 | 受入試験仕様 | 試験を足したとき（自動化欄に試験名を書く） |
| 05 | AI 開発指示書 | 役割・禁止事項を変えたとき |
| 06 | 起動方式比較 | 配布・起動の方式を変えたとき |
| 07 | 既知課題と確認事項 | 制約が増えた／解消したとき |
| 08 | 特許出願アイディア | 新規性の論点になり得る構造を実装したとき |
| 09 | ループ運用 | 検査の回し方を変えたとき |
| 10 | デバッグ所見 | 境界入力の探索結果 |
| 11 | 引き継ぎ | 現在地が変わったとき（版・完了範囲・残り） |
| 99 | 意思決定ログ | **判断したら必ず 1 行足す**（日付・版・決めたこと・理由・却下案・裏付けの試験） |

`docs/ループ実行記録.md` と `docs/試験結果.md` は `scripts/loop.py` が自動で追記するので手で書かない。

## 9. 設計の土台（変えるときは 99 に理由を残す）

- **描画器は 1 つだけ**。`backend/app/web_renderer.slide_html` が出した HTML 断片を、そのままキャンバス・サムネイル・ビューアで使う。JS 側に描画を持たない（二重実装を避けるため）。
- **文字サイズの決め方は `typography.py` に一本化**。役割ごとの帯域にクランプし、明示値は触らない。ここを迂回して個別に既定値を持たない。
- **図解は要素を増やさない**。`kind: "diagram"` 1 つに `{type, items[]}` を持たせ、描画・出力時に `diagrams.expand_diagram()` でプリミティブへ展開する。
- **着せ替えは必ず元に戻せる**（`restyle.py` の `meta.original_style` → `unstyle()`）。冪等（`meta.restyled_with`）。
- **テンプレート推定は必ず外れる前提**。UI の表で役割を変えられるようにしておく（`set_part_role`）。推定規則を増やし続けて精度で殴らない。
