"""HTML 図解テーマの試験資料を作る。

実ファイル 1 つに合わせ込むと他で壊れるので、**壊れる軸を網羅して作る**
（Phase L の `make_template_matrix.py` と同じ考え方）:

| ファイル | 軸 |
|---|---|
| `theme_cards.html`    | ふつうの書き方。`<style>` に直接色を書く。カード 3 分割 |
| `theme_flow.html`     | フロー。矢印と番号。インライン `style=` 併用 |
| `theme_compare.html`  | Before / After の 2 カラム |
| `theme_kpi.html`      | 数値強調。色が少ない |
| `theme_vars.html`     | **CSS 変数**（`:root { --brand: }`）。AI が書く HTML で一番多い書き方 |
| `theme_external.html` | 外部 CSS を `<link>` で読む。**取りに行けない**ので警告が出るべき |

出力は `samples/html_themes/`（.gitignore 済み）。
"""
from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "html_themes"

CARDS = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>要点カード テーマ</title>
<style>
  body { background:#F7F9FC; color:#222222; font-family:"Noto Sans JP",sans-serif; margin:0; padding:40px; }
  h1 { color:#0B3D91; font-family:"Meiryo",sans-serif; font-size:32px; }
  h2 { color:#0B3D91; }
  .lead { color:#666666; }
  .grid { display:flex; gap:16px; }
  .card { background:#FFFFFF; border:1px solid #D7DEE8; border-radius:12px; padding:24px;
          box-shadow:0 2px 8px rgba(0,0,0,.08); }
  .card h3 { color:#E07A1F; margin:0 0 8px; }
</style></head><body>
<section>
  <h1>導入で得られること</h1>
  <p class="lead">3 つの観点でまとめました</p>
  <div class="grid">
    <div class="card"><h3>時間</h3><p>二重作成がなくなる</p></div>
    <div class="card"><h3>品質</h3><p>体裁のばらつきが消える</p></div>
    <div class="card"><h3>安心</h3><p>社外に送信しない</p></div>
  </div>
</section>
</body></html>
"""

FLOW = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>手順フロー テーマ</title>
<style>
  body { background:#FFFFFF; color:#1A1A1A; font-family:"Yu Gothic",sans-serif; padding:32px; }
  h1 { color:#005BAC; }
  .row { display:flex; align-items:center; gap:12px; }
  .step { background:#005BAC; color:#FFFFFF; border-radius:8px; padding:18px 22px; }
  .arrow { color:#9AA5B1; font-size:28px; }
</style></head><body>
<section>
  <h1>申請の流れ</h1>
  <div class="row">
    <div class="step">① 申請</div><span class="arrow">→</span>
    <div class="step">② 上長承認</div><span class="arrow">→</span>
    <div class="step">③ 経理確認</div><span class="arrow">→</span>
    <div class="step" style="background:#00A05B">④ 振込</div>
  </div>
</section>
</body></html>
"""

COMPARE = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>比較 テーマ</title>
<style>
  body { background:#FAFAFA; color:#333333; font-family:sans-serif; padding:40px; }
  h1 { color:#B23A2E; }
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
  .box { border-radius:6px; padding:20px; }
  .before { background:#FDECEA; border:2px solid #B23A2E; }
  .after  { background:#E8F5EC; border:2px solid #1E7A46; }
</style></head><body>
<section>
  <h1>導入前後の比較</h1>
  <div class="cols">
    <div class="box before"><h3>Before</h3><p>PowerPoint と Web を手で二重管理</p></div>
    <div class="box after"><h3>After</h3><p>1 つの元データから両方へ展開</p></div>
  </div>
</section>
</body></html>
"""

KPI = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>数値 テーマ</title>
<style>
  body { background:#101828; color:#F2F4F7; font-family:"Segoe UI",sans-serif; padding:48px; }
  h1 { color:#FFFFFF; }
  .n { font-size:64px; color:#12B76A; }
</style></head><body>
<section>
  <h1>導入効果</h1>
  <p><span class="n">62</span> % 作成時間を削減</p>
  <p><span class="n">200</span> 件 月あたりの処理件数</p>
  <p><span class="n">16</span> 時間 月あたりの削減時間</p>
</section>
</body></html>
"""

VARS = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>CSS変数 テーマ</title>
<style>
  :root {
    --brand: #6C3CE0;
    --brand-ink: #FFFFFF;
    --bg: #FBFAFF;
    --ink: #241C3B;
    --muted: #7A7291;
    --line: #E2DCF5;
    --font-head: "Hiragino Kaku Gothic ProN", sans-serif;
    --font-body: "Noto Sans JP", sans-serif;
    --radius: 16px;
  }
  body { background:var(--bg); color:var(--ink); font-family:var(--font-body); padding:40px; }
  h1, h2 { color:var(--brand); font-family:var(--font-head); }
  .muted { color:var(--muted); }
  .card { background:#FFFFFF; border:1px solid var(--line); border-radius:var(--radius); padding:20px; }
  .badge { background:var(--brand); color:var(--brand-ink); border-radius:999px; padding:4px 12px; }
</style></head><body>
<section>
  <h1>サービスの特長</h1>
  <p class="muted">利用者から見た価値</p>
  <div class="card"><span class="badge">01</span><h3>すぐ使える</h3><p>インストール不要</p></div>
  <div class="card"><span class="badge">02</span><h3>安全</h3><p>手元だけで動く</p></div>
</section>
</body></html>
"""

EXTERNAL = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>外部CSS テーマ</title>
<link rel="stylesheet" href="https://example.com/theme.css">
<link rel="stylesheet" href="./local-theme.css">
</head><body>
<section>
  <h1>外部のスタイルを読むテーマ</h1>
  <div class="card"><h3>項目 A</h3><p>説明</p></div>
  <div class="card"><h3>項目 B</h3><p>説明</p></div>
</section>
</body></html>
"""

FILES = {
    "theme_cards.html": CARDS,
    "theme_flow.html": FLOW,
    "theme_compare.html": COMPARE,
    "theme_kpi.html": KPI,
    "theme_vars.html": VARS,
    "theme_external.html": EXTERNAL,
}


def build(out_dir: Path = OUT) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for name, body in FILES.items():
        p = out_dir / name
        p.write_text(body, encoding="utf-8")
        made.append(p)
    return made


if __name__ == "__main__":
    for p in build():
        print(p)
    sys.exit(0)
