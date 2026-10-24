/* 方法: SOURCES と HUBS から表を描く（手書きしない）。index の「方法」タブと methodology.html の両方で使う */
import { SOURCES, PRESETS, MODEL_CLASSES, MODELS_AS_OF, COMPARISONS, WORLD_BASE_TPS, TOKENS_PER_PROMPT, waterFor, type Level } from '../data/model';
import { HUBS } from '../data/hubs';
import { count, fixed, volume } from './format';

export function methodologyHTML(compact = false): string {
  const levels: Level[] = ['low', 'mid', 'high'];
  const ex = levels.map((l) => { const p = PRESETS[l]; const r = waterFor(1e10, p.whPerKTok, p.wue, p.offsite, p.sourceIds); return `<td class="num">${volume(r.totalL.value).text}</td>`; }).join('');
  const perPrompt = levels.map((l) => { const p = PRESETS[l]; const r = waterFor(TOKENS_PER_PROMPT, p.whPerKTok, p.wue, p.offsite, p.sourceIds); return `<td class="num">${fixed(r.totalL.value * 1000, 2)} mL</td>`; }).join('');
  return `
    <h3>計算の鎖</h3>
    <p>トークン → 電力 → 水。<code>kWh = トークン ÷ 1,000 × (Wh / 1,000 トークン) ÷ 1,000</code>、<code>水 L = kWh × (施設内 WUE + 発電側)</code>。
    世界の量は <code>(Google 月 1.3 京 + Microsoft 年 500 兆) × 倍率</code> = 土台 ${count(WORLD_BASE_TPS)} トークン/秒 × 倍率。開いてからの累計は経過秒 × 毎秒の量で、足し込みません。</p>
    ${compact ? `<ul>${levels.map((l) => { const p = PRESETS[l]; return `<li>${p.label}: ${p.whPerKTok} Wh / 1,000 tok、施設内 ${p.wue} + 発電側 ${p.offsite} L/kWh、倍率 × ${p.worldMultiplier}</li>`; }).join('')}</ul>`
    : `<table class="src-table"><thead><tr><th>前提</th><th>Wh / 1,000 tok</th><th>施設内 L/kWh</th><th>発電側 L/kWh</th><th>倍率</th></tr></thead>
    <tbody>${levels.map((l) => { const p = PRESETS[l]; return `<tr><th scope="row">${p.label}</th><td class="num">${p.whPerKTok}</td><td class="num">${p.wue}</td><td class="num">${p.offsite}</td><td class="num">× ${p.worldMultiplier}</td></tr>`; }).join('')}</tbody></table>`}
    <p class="note">100 億トークンの水: ${levels.map((l, i) => `${PRESETS[l].label.slice(0, 1)} ${ex.split('</td>')[i]!.replace(/<[^>]+>/g, '')}`).join(' / ')}。1 回あたり: ${levels.map((l, i) => `${PRESETS[l].label.slice(0, 1)} ${perPrompt.split('</td>')[i]!.replace(/<[^>]+>/g, '')}`).join(' / ')}。
    Google の公表値 0.26 mL/回（施設内のみ）と、報道の 519 mL/通（ライフサイクル）は、この幅の外側の目安として「出典」に残しています。</p>
    <h3 id="models">モデルの級（例は ${MODELS_AS_OF} 時点）</h3>
    <p class="note">級はモデルの大きさ（価格帯）で分けています。Microsoft Research の Joule 論文（MR1）では、15 倍長い推論クエリの電力は約 13 倍で、トークンあたりはほぼ同じでした。つまり推論（思考）は「トークンが増える」ことで効くので、思考トークンを出力トークンとして数えればこの級の値で計算できます。例示は時点のもので、各モデルの実測値ではありません。</p>
    <ul>${Object.values(MODEL_CLASSES).map((m) => `<li><b>${m.label}</b>: ${m.whPerKTok} Wh / 1,000 トークン — ${m.examples.join('、')}（${m.sourceIds.join(', ')}）</li>`).join('')}</ul>
    <h3 id="hubs">代表的な拠点（想定シェア）</h3>
    <p class="note">拠点の位置は主要クラウドのリージョンから選び、シェアは公表されていないため本アプリの仮定です（HUB）。施設内 WUE の倍率は気候の目安（乾燥・高温 > 1、冷涼 < 1）で、実測ではありません。</p>
    ${compact ? '' : `<table class="src-table"><thead><tr><th>拠点</th><th>地域</th><th>想定シェア</th><th>WUE 倍率</th></tr></thead><tbody>${HUBS.map((h) => `<tr><th scope="row">${h.name}</th><td>${h.region}</td><td class="num">${h.share}%</td><td class="num">× ${h.wueFactor}</td></tr>`).join('')}</tbody></table>`}
    <h3>出典</h3>
    ${compact ? `<ul class="src-list">${Object.values(SOURCES).map((s) => `<li id="src-${s.id}"><b>${s.id}</b> ${s.url.startsWith('http') ? `<a href="${s.url}" target="_blank" rel="noopener">${s.org}（${s.year}）</a>` : s.org}: ${s.value}</li>`).join('')}</ul><p class="note"><a href="methodology.html">出典の全文と注意は「方法と出典」のページに。</a></p>`
    : `<table class="src-table"><thead><tr><th>ID</th><th>出典</th><th>値</th><th>注意</th></tr></thead><tbody>
    ${Object.values(SOURCES).map((s) => `<tr id="src-${s.id}"><th scope="row">${s.id}</th><td>${s.url.startsWith('http') ? `<a href="${s.url}" target="_blank" rel="noopener">${s.org}「${s.title}」（${s.year}）</a>` : `${s.org}「${s.title}」（${s.year}）`}</td><td>${s.value}</td><td class="note">${s.note ?? ''}</td></tr>`).join('')}
    </tbody></table>`}
    <h3>換算に使った容量</h3>
    <ul>${COMPARISONS.map((c) => `<li>${c.name}: ${volume(c.liters).text}${c.sourceIds.length ? '（' + c.sourceIds.join(', ') + '）' : '（目安）'}</li>`).join('')}</ul>
    <h3>読むときの注意</h3>
    <ul>
      <li>すべて推計です。事業者・地域・季節・モデル・応答の長さで桁が変わります。</li>
      <li>「消費」は蒸発して流域に戻らない分を指し、「取水」とは異なります。</li>
      <li>事業者の公表値は施設内の冷却水だけを数えることが多く、研究推計は発電側の水や学習の按分を含むことが多い。並べるときは「何を含むか」を添えています。</li>
      <li>Google の月間トークン数は推論モデルの内部トークンを含むため、人が送った量より大きい可能性があります。</li>
    </ul>`;
}
