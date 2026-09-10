# 横展開ガイド — 個人環境のAIでコンテキスト生成を活かす

このフォルダには、work1 のコンテキスト生成を M365 Copilot 以外の
AIサービスで活用するためのツールとガイドが入っています。

## ⚠️ データガバナンス（最初に必ず読む）

- **会社の資料を個人契約の AI（claude.ai / ChatGPT / NotebookLM 等）に
  アップロードしないでください。** 情報持ち出しに該当します。
- ここでの横展開は「**個人の資料**（家庭の書類・個人の勉強資料・
  自分の創作物など）に同じ仕組みを使う」ためのものです。
- 会社データは従来どおり M365 Copilot（会社テナント内）だけに投入します。

## 構成

| パス | 内容 |
|---|---|
| `crossai_packager/` | JSONL → サービス別パッケージ変換 CLI |
| `mcp_server/` | folder-context MCP サーバ（Claude からフォルダを直接検索・抽出） |
| `guides/` | サービス別の手順書（このフォルダ） |

## セットアップ

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ../work1_improvement -e .
```

## どのシナリオを選ぶか

| 使いたいAI | ガイド | 方式 |
|---|---|---|
| Claude（claude.ai の Projects） | [claude-projects.md](claude-projects.md) | 静的パッケージをアップロード |
| ChatGPT（カスタムGPT / Projects） | [chatgpt-gpts.md](chatgpt-gpts.md) | 静的パッケージ（20ファイル上限が M365 と同型） |
| NotebookLM | [notebooklm.md](notebooklm.md) | 静的パッケージ（ソース50件以内） |
| Claude Code / Codex 等のコーディングエージェント | [coding-agents.md](coding-agents.md) | docs-context フォルダ + CLAUDE.md/AGENTS.md |
| Claude Desktop / Claude Code（常時・最新） | [mcp-setup.md](mcp-setup.md) | **MCP サーバでその場抽出（推奨・進化形）** |

静的パッケージは「アップロードした時点のスナップショット」、
MCP サーバは「質問のたびに最新のフォルダを直接読む」方式です。
頻繁に更新される資料は MCP、固定的な資料集は静的パッケージが向きます。
