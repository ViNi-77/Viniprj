# 同梱ライブラリ（ビルド不要・オフライン動作）

| ファイル | ライブラリ | 版 | 用途 | ライセンス |
|---|---|---|---|---|
| `pico.min.css` | [Pico CSS](https://picocss.com/) | 2.0.6 | フォーム・ボタン・`<dialog>`・文字寸を rem 基準で統一（ノート PC の 125〜150% 表示でも比率が保たれる） | MIT（`LICENSE-pico.md`） |
| `split.min.js` | [Split.js](https://split.js.org/) | 1.6.5 | 3 ペインの幅の分割（最小幅を割らない） | MIT（`LICENSE-split.txt`） |

取得元: npm レジストリの tarball（`@picocss/pico@2.0.6`、`split.js@1.6.5`）。更新するときは同じ版を `package.json` で確認してから差し替える。
