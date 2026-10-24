/* 前提パネル: プリセットと 4 本のスライダー */
import { PRESETS, RANGES, type Assumptions, type Level } from '../data/model';
void RANGES;
import { state, setAssumption, applyPreset, subscribe } from '../state';
import { fixed } from './format';
import { chips } from './ticker';

const FIELDS: { key: keyof Assumptions; label: string; help: string }[] = [
  { key: 'whPerKTok', label: '電力（Wh / 1,000 トークン）', help: 'Microsoft Research（Joule 2026）の典型クエリ中央値 0.31 Wh ≈ 300 トークンから 1.0。軽量モデルで 0.3（Google 公表値）、最上位で 3 前後。推論はトークン数が増えることで効く' },
  { key: 'wue', label: '施設内の冷却水 WUE（L / kWh）', help: '事業者の公表値は 0.15〜0.30。LBNL の米国平均は 0.375。業界平均として 0.84 が引かれることもある' },
  { key: 'offsite', label: '発電側の水（L / kWh）', help: '電気を作るときに蒸発する水。LBNL 2023 の比では 4.5。事業者の公表値は通常これを含まない' },
  { key: 'worldMultiplier', label: '世界のトークン量の倍率（公表値 ×）', help: 'Google（月 1.3 京）+ Microsoft（年 500 兆）の公表値に、OpenAI・Anthropic・Meta・OSS など未公表分の倍率を掛ける' },
];

export function createAssumptions(root: HTMLElement) {
  root.innerHTML = `
    <p class="panel-lead">数字の幅は、誰が・何を含めて測ったかで決まります。3 つの前提を切り替えるか、スライダーで自分の前提を作ってください。地球儀とティッカーは即座に追従します。</p>
    <div class="preset-grid" role="group" aria-label="前提のプリセット">${(['low', 'mid', 'high'] as Level[]).map((l) => `<button type="button" class="preset-btn" data-preset="${l}" aria-pressed="false"><b>${PRESETS[l].label.slice(0, 1)}</b><span>${PRESETS[l].label.slice(2, -1)}</span></button>`).join('')}</div>
    <p class="note" id="as-preset-src"></p>
    ${FIELDS.map((f) => `
      <div class="slider">
        <label for="as-${f.key}"><span>${f.label}</span><output class="num" id="as-${f.key}-o"></output></label>
        <input type="range" id="as-${f.key}" min="${RANGES[f.key].min}" max="${RANGES[f.key].max}" step="${RANGES[f.key].step}">
        <p class="help">${f.help}</p>
      </div>`).join('')}`;
  const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
  for (const f of FIELDS) {
    const el = $<HTMLInputElement>('as-' + f.key);
    el.addEventListener('input', () => setAssumption(f.key, Number(el.value)));
  }
  root.querySelectorAll<HTMLButtonElement>('[data-preset]').forEach((b) => b.addEventListener('click', () => applyPreset(b.dataset.preset as Level)));

  function render() {
    for (const f of FIELDS) {
      const v = state.assumptions[f.key];
      $<HTMLInputElement>('as-' + f.key).value = String(v);
      $('as-' + f.key + '-o').textContent = f.key === 'worldMultiplier' ? `× ${fixed(v, 1)}` : fixed(v, 2);
    }
    root.querySelectorAll<HTMLButtonElement>('[data-preset]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.preset === state.preset)));
    const src = $('as-preset-src');
    src.innerHTML = state.preset === 'custom' ? '自分の前提（出典なし）。' : `出典: ${chips(PRESETS[state.preset].sourceIds)}`;
  }
  render();
  subscribe((s, p) => { if (s.assumptions !== p.assumptions || s.preset !== p.preset) render(); });
}
