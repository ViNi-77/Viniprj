/* 世界ティッカー: 毎フレーム更新。累計は経過秒から計算し、足し込まない。 */
import { PRESETS, worldRates, worldSince, SOURCES, type SourceId } from '../data/model';
import { state } from '../state';
import { count, power, volume, volumeUnitFor, duration, fixed, type VolumeUnit } from './format';

export function chips(ids: SourceId[]): string {
  return ids.map((id) => `<a class="chip" href="methodology.html#src-${id}" title="${SOURCES[id].org}: ${SOURCES[id].title}">${id}</a>`).join('');
}

function tile(id: string, label: string, unitId: string, subId: string, ids: SourceId[]): string {
  return `<div class="tile" id="tile-${id}"><span class="label">${label}</span><span class="value num"><span id="${id}" data-value="0">—</span><small id="${unitId}"></small></span><span class="sub" id="${subId}"></span><span class="chips">${chips(ids)}</span></div>`;
}

export function createTicker(root: HTMLElement) {
  root.innerHTML =
    tile('tk-tps', 'トークン / 秒（世界、推計）', 'tk-tps-u', 'tk-tps-sub', ['G2', 'MS1']) +
    tile('tk-power', '平均電力', 'tk-power-u', 'tk-power-sub', ['V1', 'O1']) +
    tile('tk-lps', '蒸発する水 / 秒', 'tk-lps-u', 'tk-lps-sub', ['L1', 'A1', 'M1']) +
    tile('tk-since', '開いてから蒸発した水', 'tk-since-u', 'tk-since-sub', ['L1']);
  const $ = (id: string) => document.getElementById(id)!;
  const el = {
    tps: $('tk-tps'), tpsU: $('tk-tps-u'), tpsSub: $('tk-tps-sub'),
    power: $('tk-power'), powerU: $('tk-power-u'), powerSub: $('tk-power-sub'),
    lps: $('tk-lps'), lpsU: $('tk-lps-u'), lpsSub: $('tk-lps-sub'),
    since: $('tk-since'), sinceU: $('tk-since-u'), sinceSub: $('tk-since-sub'),
  };
  let sinceUnit: VolumeUnit = 'L', lastStatic = '', lastSince = '', lastSub = '';

  function setText(e: HTMLElement, t: string) { if (e.textContent !== t) e.textContent = t; }

  function renderStatic() {
    const a = state.assumptions;
    const r = worldRates(a), lo = worldRates(PRESETS.low), hi = worldRates(PRESETS.high);
    const key = JSON.stringify(a);
    if (key === lastStatic) return;
    lastStatic = key;
    setText(el.tps, count(r.tokensPerSec)); el.tps.dataset.value = String(r.tokensPerSec); setText(el.tpsU, '');
    setText(el.tpsSub, `Google + Microsoft の公表値 × ${fixed(a.worldMultiplier, 1)}（低 ${count(lo.tokensPerSec)} – 高 ${count(hi.tokensPerSec)}）`);
    const p = power(r.watts);
    setText(el.power, p.value); setText(el.powerU, p.unit); el.power.dataset.value = String(r.watts);
    setText(el.powerSub, `${fixed(a.whPerKTok, 1)} Wh / 1,000 トークン（低 ${power(lo.watts).text} – 高 ${power(hi.watts).text}）`);
    const v = volume(r.litersPerSecTotal);
    setText(el.lps, v.value); setText(el.lpsU, v.unit + '/秒'); el.lps.dataset.value = String(r.litersPerSecTotal);
    setText(el.lpsSub, `施設内 ${volume(r.litersPerSecOnsite).text}/秒 + 発電側（低 ${volume(lo.litersPerSecTotal).text} – 高 ${volume(hi.litersPerSecTotal).text}）`);
    // 5 分後の値で単位を決める（以後は上がる方向にだけ変える）
    sinceUnit = volumeUnitFor(r.litersPerSecTotal * 300);
    if (sinceUnit === 'mL') sinceUnit = 'L';
  }

  function tick(now: number) {
    renderStatic();
    const s = worldSince((now - state.t0) / 1000, state.assumptions);
    const order: VolumeUnit[] = ['L', '万 L', '億 L', '兆 L'];
    const cur = volumeUnitFor(s.litersTotal);
    if (order.indexOf(cur) > order.indexOf(sinceUnit) && s.litersTotal / { 'mL': 1e-3, 'L': 1, '万 L': 1e4, '億 L': 1e8, '兆 L': 1e12 }[sinceUnit] >= 10000) sinceUnit = cur;
    const v = volume(s.litersTotal, sinceUnit, 1);
    if (v.value !== lastSince) { lastSince = v.value; el.since.textContent = v.value; el.since.dataset.value = String(s.litersTotal); el.sinceU.textContent = v.unit; }
    const sub = `${duration(now - state.t0)} ・ トークン ${count(s.tokens)}`;
    if (sub !== lastSub) { lastSub = sub; el.sinceSub.textContent = sub; }
  }
  return { tick, renderStatic };
}
