import { state, setState, subscribe, loadPrefs } from './state';
import { worldRates } from './data/model';
import { HUBS } from './data/hubs';
import { loop } from './globe/loop';
import { createGlobe, type Globe } from './globe/scene';
import { createTicker } from './ui/ticker';
import { createYourTokens } from './ui/yourTokens';
import { createAssumptions } from './ui/assumptions';
import { methodologyHTML } from './ui/methodology';
import { createMe } from './ui/me';
import { createBottleView, type BottleView } from './ui/bottleView';
import { EXAMPLE } from './data/example';
import { volume, fixed } from './ui/format';

declare global { interface Window { __awl: { webgl: boolean; rafActive: () => boolean; readCenter: () => number; bottle: () => BottleView | null; exampleResponseL: number; hubScreen: (id: string) => { x: number; y: number; visible: boolean } | null; state: typeof state } } }
export {};

function boot() {
  loadPrefs();
  const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

  // 地球儀（WebGL が無ければ数字だけ）
  let globe: Globe | null = null;
  try {
    globe = createGlobe($('globe'), () => {
      const narrow = matchMedia('(max-width: 56rem)').matches;
      const panel = $('panel').getBoundingClientRect(), ticker = $('ticker').getBoundingClientRect();
      const card = $('me-card'), hint = $('me-hint');
      const low = !card.hidden ? card.getBoundingClientRect().top : !hint.hidden ? hint.getBoundingClientRect().top : window.innerHeight - 40;
      if (narrow) return { right: 0, top: 0, bottom: 0 };
      return { right: window.innerWidth - panel.left, top: ticker.bottom, bottom: Math.max(0, window.innerHeight - low) };
    });
  } catch (e) {
    console.warn('WebGL unavailable', e);
    $('no-webgl').hidden = false; $('globe').style.display = 'none';
    setState({ webgl: false });
  }

  globe?.faceHub(state.your.hubId);
  const ticker = createTicker($('ticker'));
  createYourTokens($('tab-your'));
  createAssumptions($('tab-assumptions'));
  $('tab-method').innerHTML = methodologyHTML(true);
  createMe($('me-card'), $('me-hint'), (hubId, rate) => globe?.setYou(hubId, rate));
  // カードの出入りで空き領域が変わるので、地球の位置を取り直す
  subscribe((s, p) => { if (s.meStatus !== p.meStatus) requestAnimationFrame(() => globe?.resize()); });

  // タブ
  document.querySelectorAll<HTMLButtonElement>('.tabs [data-tab]').forEach((b) => b.addEventListener('click', () => setState({ tab: b.dataset.tab as typeof state.tab })));
  function renderTabs() {
    document.querySelectorAll<HTMLButtonElement>('.tabs [data-tab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === state.tab)));
    for (const t of ['your', 'assumptions', 'method'] as const) $('tab-' + t).hidden = t !== state.tab;
  }
  renderTabs();
  subscribe((s, p) => { if (s.tab !== p.tab) renderTabs(); });

  // 強さ（相対値）→ 地球儀
  function applyIntensity() {
    if (!globe) return;
    const r = worldRates(state.assumptions);
    const tk = Math.max(0.12, Math.min(1, (Math.log10(r.tokensPerSec) - 8) / 1.8));
    const wt = Math.max(0.12, Math.min(1, (Math.log10(Math.max(1, r.litersPerSecTotal)) - 2) / 2.2));
    globe.setIntensity(tk, wt);
  }
  applyIntensity();
  subscribe((s, p) => { if (s.assumptions !== p.assumptions) applyIntensity(); });

  // 拠点のツールチップ
  const tip = $('tooltip');
  const canvas = $<HTMLCanvasElement>('globe');
  let lastPick = 0;
  canvas.addEventListener('pointermove', (e) => {
    if (!globe || e.pointerType === 'touch') return;
    const now = performance.now(); if (now - lastPick < 40) return; lastPick = now;
    const hub = globe.pickHub(e.clientX, e.clientY);
    const id = hub ? hub.id : null;
    if (id !== state.hoverHub) { setState({ hoverHub: id }); globe.setHover(id); canvas.style.cursor = id ? 'pointer' : 'grab'; }
  });
  canvas.addEventListener('pointerleave', () => { if (state.hoverHub) { setState({ hoverHub: null }); globe?.setHover(null); } });
  function renderTip() {
    const id = state.hoverHub; if (!id || !globe) { tip.hidden = true; return; }
    const hub = HUBS.find((h) => h.id === id)!;
    const pos = globe.hubScreen(id); if (!pos || !pos.visible) { tip.hidden = true; return; }
    const r = worldRates(state.assumptions);
    const share = hub.share / 100;
    const onsite = r.litersPerSecOnsite * share * hub.wueFactor, offsite = (r.litersPerSecTotal - r.litersPerSecOnsite) * share;
    tip.innerHTML = `<b>${hub.name}</b><span>${hub.region} · 想定シェア ${hub.share}%</span><br><span class="num">${volume(onsite + offsite).text}/秒</span>（施設内 ${volume(onsite).text} · WUE × ${fixed(hub.wueFactor, 1)}）`;
    tip.style.left = pos.x + 'px'; tip.style.top = pos.y + 'px'; tip.hidden = false;
  }

  // reduced-motion
  if (state.reduced) { loop.setReduced(true); globe?.setReduced(true); }

  // 画面の切替（ボトルは初めて開いたときに作る）
  let bottle: BottleView | null = null;
  const bottleCanvas = $<HTMLCanvasElement>('bottle'), bottleHud = $('bottle-hud');
  function bottleLayout() {
    const narrow = matchMedia('(max-width: 56rem)').matches;
    const ticker = $('ticker').getBoundingClientRect(), hud = bottleHud.getBoundingClientRect(), cv = bottleCanvas.getBoundingClientRect();
    if (narrow) return { right: 0, top: ticker.bottom - cv.top, bottom: Math.max(0, cv.bottom - hud.top) };
    const panel = $('panel').getBoundingClientRect();
    const right = window.innerWidth - panel.left;
    // 背が低い画面（ノート PC の 125%）では、下の表示の「右」にボトルを置く。高い画面では「上」に置く
    if (window.innerHeight - ticker.bottom - hud.height < 240) return { left: hud.right + 8, right, top: ticker.bottom, bottom: 0 };
    return { right, top: ticker.bottom, bottom: Math.max(0, window.innerHeight - hud.top) };
  }
  function renderView() {
    const v = state.view;
    document.body.dataset.view = v;
    document.querySelectorAll<HTMLButtonElement>('.view-switch [data-view]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.view === v)));
    $('globe').hidden = v !== 'globe' || !globe;
    bottleCanvas.hidden = v !== 'bottle';
    bottleHud.hidden = v !== 'bottle';
    $('hud-hint').textContent = v === 'globe' ? 'ドラッグで回す · 拠点にカーソルで詳細' : 'ドラッグで回す · 下の目盛りで縮尺を変える';
    if (v === 'bottle') {
      if (!bottle && state.webgl) {
        try { bottle = createBottleView(bottleCanvas, bottleHud, bottleLayout); if (state.reduced) bottle.scene.setReduced(true); }
        catch (e) { console.warn('bottle unavailable', e); }
      }
      requestAnimationFrame(() => bottle?.show());
    } else requestAnimationFrame(() => globe?.resize());
  }
  document.querySelectorAll<HTMLButtonElement>('.view-switch [data-view]').forEach((b) => b.addEventListener('click', () => setState({ view: b.dataset.view as 'globe' | 'bottle' })));
  subscribe((s, p) => { if (s.view !== p.view) renderView(); });
  if (location.hash === '#bottle') setState({ view: 'bottle' }); else renderView();

  let rafActive = false;
  loop.register((now, dt) => {
    rafActive = !loop.reduced;
    const t = (now - state.t0) / 1000;
    if (state.view === 'bottle' && bottle) bottle.tick(now, dt);
    else globe?.render(t, dt);
    ticker.tick(now);
    if (state.hoverHub) renderTip();
  });
  loop.start();

  window.__awl = { webgl: !!globe, rafActive: () => rafActive && loop.running, readCenter: () => (state.view === 'bottle' ? (bottle ? bottle.scene.readCenter() : -1) : globe ? globe.readCenter() : -1), bottle: () => bottle, exampleResponseL: EXAMPLE.response.liters, hubScreen: (id: string) => (globe ? globe.hubScreen(id) : null), state };
}

document.addEventListener('DOMContentLoaded', boot);
