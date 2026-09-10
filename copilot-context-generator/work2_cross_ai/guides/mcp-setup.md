# folder-context MCP サーバのセットアップ

静的パッケージの生成・アップロードなしで、Claude Desktop / Claude Code が
資料フォルダ（Word/Excel/PowerPoint/PDF/txt/zip）を**その場で**
検索・抽出できるようにする MCP サーバです。

20ファイル上限や再アップロードの手間から解放される、このツールの
正統進化形です。抽出結果は `~/.folder-context-mcp/` にキャッシュされ、
2回目以降は高速です。

## 提供ツール

| ツール | 説明 |
|---|---|
| `search_files` | ファイル名・拡張子でファイルを検索 |
| `read_document` | 本文テキストを抽出（長文はページング） |
| `get_summary` | 見出し+先頭段落の要約と抽出ステータス |
| `search_content` | 全ファイルの本文からキーワード検索 |
| `list_recent_changes` | 直近 N 日に更新されたファイル一覧 |

## Claude Code への登録

```bash
claude mcp add folder-context -- \
    /path/to/.venv/bin/folder-context-mcp --root ~/Documents/資料
```

## Claude Desktop への登録

`claude_desktop_config.json`（設定 → 開発者 → 構成を編集）:

```json
{
  "mcpServers": {
    "folder-context": {
      "command": "/path/to/.venv/bin/folder-context-mcp",
      "env": {
        "FOLDER_CONTEXT_ROOT": "C:\\Users\\you\\Documents\\資料"
      }
    }
  }
}
```

## 動作確認

```bash
# スモークテスト（サーバ起動 → ツール一覧 → 検索呼び出し）
python scripts/smoke_mcp.py ~/Documents/資料
```

## セキュリティ

- サーバは `--root`（または FOLDER_CONTEXT_ROOT）配下のみアクセスします。
  ルート外へのパス指定は拒否されます
- 会社の資料フォルダを個人の claude.ai アカウント配下の Claude Desktop に
  つなぐ場合は、社内の AI 利用ポリシーに従ってください
