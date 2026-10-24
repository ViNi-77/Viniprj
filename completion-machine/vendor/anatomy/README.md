# vendor/anatomy

[wheresryan22/anatomy](https://github.com/wheresryan22/anatomy) から、ビルドと検査に要るファイルだけを複製したもの（MIT、`LICENSE` 参照）。

- 取得元 commit: `1482e8469b0a9e0d8cc18ea2740a01423d29ae80`（2026-10-18）
- `kit/`: `iso-kit.mjs`（描画の核）、`lathe.mjs`・`tube.mjs`・`audit.mjs`（監査）、`iso.css`
- `scripts/`: `inline-kit.mjs`（キットをページに埋め込む）、`capture.mjs`・`drive.mjs`・`lines.mjs`・`line-ends.mjs`・`chrome-port.mjs`（Chrome での検査）

`scripts/inline-kit.mjs` は `../kit` を相対で読むので、ディレクトリ構造を変えない。
更新するときは同じファイルを新しい commit から取り直し、この README の commit を書き換える。
