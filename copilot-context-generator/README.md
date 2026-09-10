# copilot-context-generator

M365 Copilot エージェント用コンテキスト生成ツール
（CopilotM365ContextGenerator）の復元・改善・横展開プロジェクト。

## 経緯

元ソース (.pyw) が失われ、PyInstaller exe と解析データのみが残っていた。
本プロジェクトでは exe から抽出したバイトコードの逆アセンブルから
ソースを忠実復元し（オペコード列レベルで一致を機械検証）、
それを土台に改善5項目と他AIへの横展開を実装した。

## 構成

| フォルダ | 内容 |
|---|---|
| `work1_improvement/` | **ワーク1**: 復元ソース (`restored/`) + 改善版 `contextgen` パッケージ |
| `work2_cross_ai/` | **ワーク2**: AIサービス別パッケージャ + folder-context MCP サーバ + ガイド |

## クイックスタート

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e work1_improvement -e work2_cross_ai

# GUI（従来と同じ操作感）
.venv/bin/python -m contextgen.gui

# CLI（無人実行）
.venv/bin/python -m contextgen --source <参照元> --output <出力先>

# 他AI向けパッケージ（例: Claude Projects）
.venv/bin/crossai-packager --source <個人資料> --output <出力先> --profile claude-projects

# MCP サーバ（Claude からフォルダを直接検索・抽出）
claude mcp add folder-context -- .venv/bin/folder-context-mcp --root <資料フォルダ>

# テスト（work1: 46件 / work2: 16件）
cd work1_improvement && ../.venv/bin/python -m pytest tests -q; cd ..
cd work2_cross_ai && ../.venv/bin/python -m pytest tests -q; cd ..
```

## ドキュメント

- 改善版の使い方: [work1_improvement/docs/README.md](work1_improvement/docs/README.md)
- 夜間自動実行などの運用: [work1_improvement/docs/OPERATIONS.md](work1_improvement/docs/OPERATIONS.md)
- Windows exe ビルド: [work1_improvement/docs/BUILD_WINDOWS.md](work1_improvement/docs/BUILD_WINDOWS.md)
- 変更履歴: [work1_improvement/docs/CHANGELOG.md](work1_improvement/docs/CHANGELOG.md)
- 横展開ガイド（Claude/GPT/NotebookLM/MCP）: [work2_cross_ai/guides/README.md](work2_cross_ai/guides/README.md)

## 重要な不変条件

- `work1_improvement/restored/` は**変更禁止**（原本の証明付きスナップショット）
- `contextgen` の `--legacy` は原本 exe と同一出力を維持すること
  （`tests/test_parity.py` が回帰ネット）
