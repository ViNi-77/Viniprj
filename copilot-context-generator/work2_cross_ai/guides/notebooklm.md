# NotebookLM で使う

NotebookLM はソース数上限（無料50 / Pro 300）があるため、
1ソースを大きめ（20万字）にした `notebooklm` プロファイルを使います。

## 手順

```bash
crossai-packager --source ~/Documents/研究資料 \
    --output ~/Desktop/nlm_pkg --profile notebooklm
```

1. NotebookLM で新しいノートブックを作成
2. ソースの追加 → `NotebookLMSource_INDEX.md` と
   `NotebookLMSource_001.md` 以降をアップロード
3. 音声概要（Audio Overview）やマインドマップもこのソースから生成可能

## 補足

- NotebookLM は引用箇所を自動でハイライトするため、Source セクションの
  メタデータ（SourcePath）がそのまま出典表示に活きます
- 資料更新時はソースを削除して再アップロード
