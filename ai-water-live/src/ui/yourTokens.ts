/* 「あなたのトークン」: トークン数 → 電力・水・換算・共有カード */
import { MODEL_CLASSES, MODELS_AS_OF, COMPARISONS, waterFor, worldRates, SOURCES, type ModelClass, type SourceId } from '../data/model';
import { HUBS } from '../data/hubs';
import { state, setState, subscribe } from '../state';
import { count, volume, energy, times, fixed } from './format';
import { chips } from './ticker';
import { renderShareCard } from './shareCard';
import { meToYourTokens } from './me';

const PRESETS_TOKENS: [string, number][] = [['1 億', 1e8], ['10 億', 1e9], ['100 億', 1e10], ['1 兆', 1e12]];

/** 「1億」「10,000」「1.5兆」などを数に */
export function parseTokens(s: string): number | null {
  const t = s.replace(/[,\s，]/g, '').replace(/[０-９．]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0));
  const m = t.match(/^(\d+(?:\.\d+)?)(京|兆|億|万|k|K|M|B|T)?$/);
  if (!m) return null;
  const mult: Record<string, number> = { 京: 1e16, 兆: 1e12, 億: 1e8, 万: 1e4, k: 1e3, K: 1e3, M: 1e6, B: 1e9, T: 1e12 };
  const v = Number(m[1]) * (m[2] ? mult[m[2]] ?? 1 : 1);
  return Number.isFinite(v) && v >= 0 ? v : null;
}

export function yourResult() {
  const y = state.your, a = state.assumptions;
  const mc = MODEL_CLASSES[y.modelClass];
  const hub = HUBS.find((h) => h.id === y.hubId) ?? HUBS[0]!;
  const wue = a.wue * hub.wueFactor;
  const ids: SourceId[] = [...mc.sourceIds, 'L1', 'HUB'];
  const tokens = y.perDay ? y.tokens * 365 : y.tokens;
  return { tokens, perDay: y.perDay, hub, wue, r: waterFor(tokens, mc.whPerKTok, wue, a.offsite, ids), ids, mc };
}

export function createYourTokens(root: HTMLElement) {
  root.innerHTML = `
    <p class="panel-lead">トークン数を入れると、電力と、冷却と発電で蒸発した淡水に換算します。API の利用量ページの数字をそのまま貼れます。</p>
    <div class="field">
      <label for="yt-tokens">トークン数</label>
      <div class="input-row"><input id="yt-tokens" type="text" inputmode="numeric" autocomplete="off" value="100億"><span class="input-unit">トークン</span></div>
      <div class="chips-row me-row" id="yt-me" hidden><span class="me-row-label">実ログから</span><button type="button" class="pill pill-accent" data-me="session">直近の会話</button><button type="button" class="pill pill-accent" data-me="today">今日</button><button type="button" class="pill pill-accent" data-me="week">7 日</button></div>
      <div class="chips-row" id="yt-presets">${PRESETS_TOKENS.map(([l, v]) => `<button type="button" class="pill" data-tokens="${v}">${l}</button>`).join('')}</div>
      <div class="seg-row" role="group" aria-label="期間">
        <button type="button" class="seg-btn" data-perday="0" aria-pressed="true">合計</button>
        <button type="button" class="seg-btn" data-perday="1" aria-pressed="false">1 日あたり（× 365 日）</button>
      </div>
    </div>
    <div class="field-2">
      <div class="field"><label for="yt-model">モデルの級</label><select id="yt-model">${Object.entries(MODEL_CLASSES).map(([k, m]) => `<option value="${k}">${m.label}（${m.examples[0]} など）· ${m.whPerKTok} Wh/1,000</option>`).join('')}</select></div>
      <div class="field"><label for="yt-hub">データセンターの地域</label><select id="yt-hub">${HUBS.map((h) => `<option value="${h.id}">${h.name}（WUE × ${h.wueFactor}）</option>`).join('')}</select></div>
    </div>
    <p class="help" id="yt-model-help"></p>
    <div class="result">
      <div class="result-big"><span class="label">蒸発した淡水（施設内 + 発電側）</span><span class="value num accent"><span id="yt-total" data-value="0">—</span><small id="yt-total-u"></small></span><span class="chips" id="yt-chips"></span></div>
      <ul class="result-grid">
        <li><span class="label">電力</span><span class="value num"><span id="yt-kwh">—</span><small id="yt-kwh-u"></small></span></li>
        <li><span class="label">施設内の冷却水</span><span class="value num"><span id="yt-onsite">—</span><small id="yt-onsite-u"></small></span></li>
        <li><span class="label">発電側の水</span><span class="value num"><span id="yt-offsite">—</span><small id="yt-offsite-u"></small></span></li>
        <li><span class="label">世界の何秒分か</span><span class="value num"><span id="yt-worldsec">—</span><small>秒</small></span></li>
      </ul>
      <ul class="equiv" id="yt-equiv"></ul>
      <p class="note" id="yt-note"></p>
      <div class="actions"><button type="button" class="btn-primary" id="yt-share">共有カードを作る（PNG）</button><a id="yt-download" class="btn-link" hidden download="token-water.png">ダウンロード</a></div>
    </div>`;

  const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
  const input = $<HTMLInputElement>('yt-tokens'), model = $<HTMLSelectElement>('yt-model'), hubSel = $<HTMLSelectElement>('yt-hub');
  model.value = state.your.modelClass; hubSel.value = state.your.hubId;

  input.addEventListener('input', () => { const v = parseTokens(input.value); input.classList.toggle('is-invalid', v === null); if (v !== null) setState({ your: { ...state.your, tokens: v } }); });
  root.querySelectorAll<HTMLButtonElement>('[data-tokens]').forEach((b) => b.addEventListener('click', () => { input.value = b.textContent ?? ''; setState({ your: { ...state.your, tokens: Number(b.dataset.tokens) } }); }));
  root.querySelectorAll<HTMLButtonElement>('[data-perday]').forEach((b) => b.addEventListener('click', () => {
    root.querySelectorAll<HTMLButtonElement>('[data-perday]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    setState({ your: { ...state.your, perDay: b.dataset.perday === '1' } });
  }));
  root.querySelectorAll<HTMLButtonElement>('[data-me]').forEach((b) => b.addEventListener('click', () => {
    const r = meToYourTokens(b.dataset.me as 'today' | 'week' | 'session'); if (!r) return;
    input.value = count(r.tokens); model.value = r.modelClass;
    setState({ your: { ...state.your, tokens: r.tokens, modelClass: r.modelClass, perDay: false } });
    root.querySelectorAll<HTMLButtonElement>('[data-perday]').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.perday === '0')));
  }));
  subscribe((s, p) => { if (s.meStatus !== p.meStatus) $('yt-me').hidden = s.meStatus !== 'ok'; });
  model.addEventListener('change', () => setState({ your: { ...state.your, modelClass: model.value as ModelClass } }));
  hubSel.addEventListener('change', () => setState({ your: { ...state.your, hubId: hubSel.value } }));
  $('yt-share').addEventListener('click', async () => {
    const res = yourResult();
    const blob = await renderShareCard(res);
    const a = $<HTMLAnchorElement>('yt-download');
    const url = URL.createObjectURL(blob);
    a.href = url; a.hidden = false; a.textContent = 'PNG をダウンロード';
    const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
    const file = new File([blob], 'token-water.png', { type: 'image/png' });
    if (nav.share && nav.canShare && nav.canShare({ files: [file] })) { try { await nav.share({ files: [file], title: 'トークンの水' }); } catch { /* 取消 */ } }
    else a.click();
  });

  function render() {
    const { tokens, perDay, hub, r, ids } = yourResult();
    const total = volume(r.totalL.value); $('yt-total').textContent = total.value; $('yt-total-u').textContent = total.unit; $('yt-total').dataset.value = String(r.totalL.value);
    const e = energy(r.kWh.value); $('yt-kwh').textContent = e.value; $('yt-kwh-u').textContent = e.unit;
    const on = volume(r.onsiteL.value); $('yt-onsite').textContent = on.value; $('yt-onsite-u').textContent = on.unit;
    const off = volume(r.offsiteL.value); $('yt-offsite').textContent = off.value; $('yt-offsite-u').textContent = off.unit;
    const wr = worldRates(state.assumptions);
    $('yt-worldsec').textContent = fixed(tokens / wr.tokensPerSec, tokens / wr.tokensPerSec < 10 ? 2 : 1);
    $('yt-chips').innerHTML = chips(ids);
    // 換算: 量に合う 3 つ
    const L = r.totalL.value;
    const list = COMPARISONS.filter((c) => L / c.liters >= 0.05).slice(-3);
    const items = (list.length ? list : [COMPARISONS[0]]).map((c) => `<li><b class="num">${times(L / c!.liters)}</b> ${c!.unit}分の${c!.name}${c!.sourceIds.length ? ' ' + chips(c!.sourceIds) : ''}</li>`);
    $('yt-equiv').innerHTML = items.join('');
    $('yt-model-help').textContent = `例（${MODELS_AS_OF} 時点）: ${MODEL_CLASSES[state.your.modelClass].examples.join('、')}。思考（reasoning）トークンは出力トークンとして課金されるので、トークン数に含めてください。`;
    $('yt-note').textContent = `${count(tokens)} トークン${perDay ? '（1 日 ' + count(state.your.tokens) + ' × 365 日）' : ''} · ${MODEL_CLASSES[state.your.modelClass].label} · ${hub.name}（施設内 WUE ${fixed(state.assumptions.wue * hub.wueFactor, 2)} L/kWh）· 発電側 ${fixed(state.assumptions.offsite, 1)} L/kWh。すべて推計。`;
  }
  render();
  subscribe((s, p) => { if (s.your !== p.your || s.assumptions !== p.assumptions) render(); });
  return { render };
}

export const _sources = SOURCES;
