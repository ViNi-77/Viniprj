# THIRD_PARTY_NOTICES

模擬 PPTX の生成・検査に使用するサードパーティソフトウェア。フォントは OS 標準（Arial / Noto Sans JP 相当）を参照するのみで、リポジトリには含めない。画像はすべてコード内で生成し、外部素材を使用しない。

| ソフトウェア | 用途 | ライセンス |
|---|---|---|
| python-pptx | PPTX 生成・再読込検査 | MIT |
| Pillow | 抽象画像の生成、縦横比検査 | HPND（MIT-CMU） |
| lxml | コネクター矢頭（OOXML）の追記 | BSD-3-Clause |
| pytest | 自動検査 | MIT |
| Playwright + Chromium | プレビュー PDF（任意） | Apache-2.0 / BSD-3-Clause |
