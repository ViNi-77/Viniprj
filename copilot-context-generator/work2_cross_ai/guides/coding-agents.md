# Claude Code / Codex などのコーディングエージェントで使う

コーディングエージェントはテキストファイルは直接読めますが、
**xlsx / pptx / pdf の中身は grep できない**のが弱点です。
このツールで事前にテキスト化しておくと、エージェントが
Excel 仕様書や PowerPoint 設計資料を検索・引用できるようになります。

## 方式A: docs-context フォルダ（静的）

```bash
# リポジトリ内に資料のテキスト版を生成
python -m contextgen --source ./docs --output ./docs-context --no-cache
```

`CLAUDE.md`（Claude Code）または `AGENTS.md`（Codex 等）に追記:

```markdown
## 資料の参照方法

./docs には Excel/PowerPoint/PDF の原本があるが、エージェントは
./docs-context/_AI_CONTEXT_DATA.jsonl と _AI_CONTEXT_SUMMARY_*.md を
参照すること。各レコード/セクションの SourcePath が原本の場所を示す。
仕様の根拠を答えるときは SourcePath を引用する。
```

`.gitignore` に `docs-context/` を入れるか、リポジトリにコミットするかは
チームの方針で選択（コミットすると全員のエージェントが恩恵を受けます）。

## 方式B: MCP サーバ（動的・推奨）

[mcp-setup.md](mcp-setup.md) の folder-context MCP サーバを使うと、
事前生成なしでエージェントが資料フォルダを直接検索・抽出できます。

```bash
claude mcp add folder-context -- folder-context-mcp --root ./docs
```

## JSONL の再利用

`_AI_CONTEXT_DATA.jsonl` は 1行1チャンクの構造化データなので、
そのまま RAG の入力・埋め込み生成・全文検索インデックス作成に使えます。

```python
import json
records = [json.loads(l) for l in open('docs-context/_AI_CONTEXT_DATA.jsonl')]
```
