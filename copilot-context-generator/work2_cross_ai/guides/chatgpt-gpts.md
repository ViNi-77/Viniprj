# ChatGPT（カスタムGPT / Projects）で使う

カスタムGPT のナレッジは「最大20ファイル」という M365 Copilot と
同型の制約があります。このツールの「INDEX 1 + 本文19」設計が
そのまま適用できます。

## 手順

```bash
crossai-packager --source ~/Documents/レシピと料理メモ \
    --output ~/Desktop/gpt_pkg --profile chatgpt-gpts
```

1. ChatGPT → GPTs → Create a GPT
2. Configure → Knowledge に `GPTKnowledge_INDEX.txt` と
   `GPTKnowledge_001.txt` 以降をアップロード（合計20ファイル以内）
3. Instructions に追記:

```
Knowledge の各 Source セクションには FileName / SourcePath / Chunk の
メタデータがあります。回答の根拠となった SourcePath を明記してください。
```

ChatGPT Projects のファイルアップロードでも同じパッケージが使えます。

## 上限あふれ（OverflowWarning）が出たら

- INDEX の `OverflowChunkCount` を確認
- フォルダを分けて GPT を複数作る、または
  `crossai-packager --source <サブフォルダ>` で対象を絞る
