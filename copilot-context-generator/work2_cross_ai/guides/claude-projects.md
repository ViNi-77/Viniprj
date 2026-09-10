# Claude Projects で使う

個人の資料フォルダを Claude（claude.ai）の Project ナレッジにする手順。

## 手順

```bash
# 1. パッケージ生成（フォルダから一括）
crossai-packager --source ~/Documents/家の書類 \
    --output ~/Desktop/claude_pkg --profile claude-projects
```

2. claude.ai で Project を作成（例:「わが家の書類アシスタント」）
3. Project knowledge に `claude_pkg` 内の
   `ClaudeProjectContext_INDEX.md` と `ClaudeProjectContext_001.md` 以降を
   すべてアップロード
4. Project instructions に以下を追記すると引用が安定します:

```
ナレッジの各 Source セクションには FileName / SourcePath / Chunk の
メタデータが付いています。回答が特定の書類に依存する場合は、
必ず SourcePath を引用してください。見つからない場合は INDEX ファイルの
SourceChunkIndex を確認してください。
```

## 運用

- 資料が変わったら再生成し、変わったファイルだけ置き換え
  （ファイル名は固定なので差し替えが楽です）
- Projects は容量が大きく RAG 検索も入るため、M365 のような
  20ファイル制約はありません（プロファイルは 90 ファイルまで生成）

## 活用例（個人資料）

- 家電の取扱説明書 PDF 一式 →「エアコンのフィルター掃除の手順は？」
- 保険・契約書類 →「火災保険の水濡れ補償の範囲は？」
- 家計の Excel →「2025年の光熱費合計は？」
