/* ボトル画面の重ね表示と配線。3D は src/bottle/scene.ts、文字はすべてここ（HTML）。 */
import { state, setState, subscribe } from '../state';
import { LADDER_SCALES, ladderLiters, BOTTLE_LITERS, SOURCES, type LadderScale } from '../data/model';
import { EXAMPLE } from '../data/example';
import { createBottleScene, type BottleScene, type StageLayout } from '../bottle/scene';
import { volume, count, times, fixed } from './format';
import { chips } from './ticker';

export interface BottleView { scene: BottleScene; tick(now: number, dt: number): void; show(): void }

export function createBottleView(canvas: HTMLCanvasElement, hud: HTMLElement, layout: () => StageLayout): BottleView {
  const scene = createBottleScene(canvas, layout);
  hud.innerHTML = `
    <div class="bv-scales" role="tablist" aria-label="縮尺">${LADDER_SCALES.map((s) => `<button type="button" role="tab" data-scale="${s.id}" aria-selected="false" title="${s.help}">${s.label}</button>`).join('')}</div>
    <div class="bv-main"><span class="value num accent"><span id="bv-liters" data-value="0">0</span><small id="bv-unit">L</small></span><span class="bv-eq" id="bv-eq"></span></div>
    <p class="bv-sub" id="bv-sub"></p>
    <p class="bv-last" id="bv-last" aria-live="polite"></p>
    <div class="bv-manual" id="bv-manual" hidden>
      <button type="button" class="send-btn" id="bv-send">応答 1 回ぶん注ぐ <span class="kbd">Space</span></button>
      <span class="bv-manual-note">1 回 = ${fixed(EXAMPLE.response.liters, 2)} L（作例: 最上位モデルで キャッシュ読み ${count(EXAMPLE.perResponse.cr)}・出力 ${count(EXAMPLE.perResponse.out)} トークンの応答。仮の数字）</span>
    </div>
    <div class="bv-labels" id="bv-labels" aria-hidden="true"></div>`;
  const $ = (id: string) => document.getElementById(id)!;
  let manualL = 0, prevMsgs = -1, prevL = -1, prevDay = '', lastText = '', lastScaleKey = '';

  function todayL(): number { return state.me ? state.me.today.liters.mid : manualL; }
  function weekL(): number { return state.me ? state.me.week.liters.mid : manualL; }

  function setScale(s: LadderScale) { setState({ ladderScale: s }); }
  hud.querySelectorAll<HTMLButtonElement>('[data-scale]').forEach((b) => b.addEventListener('click', () => setScale(b.dataset.scale as LadderScale)));
  $('bv-send').addEventListener('click', () => pourManual());
  document.addEventListener('keydown', (e) => {
    if (state.view !== 'bottle' || state.meStatus === 'ok' || e.code !== 'Space') return;
    const tag = (e.target as HTMLElement | null)?.tagName ?? '';
    if (/INPUT|SELECT|TEXTAREA|BUTTON|A/.test(tag)) return;
    e.preventDefault(); pourManual();
  });
  function pourManual() {
    manualL += EXAMPLE.response.liters;
    scene.pour(EXAMPLE.response.liters);
    $('bv-last').textContent = `+${volume(EXAMPLE.response.liters).text}（作例の応答 1 回）`;
    render();
  }

  function applyScale(force = true) {
    const s = state.ladderScale;
    const key = `${s}:${Math.round(ladderLiters(s, todayL(), weekL(), state.assumptions) * 100)}`;
    if (!force && key === lastScaleKey) { render(); return; }
    lastScaleKey = key;
    hud.querySelectorAll<HTMLButtonElement>('[data-scale]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.scale === s)));
    const L = ladderLiters(s, todayL(), weekL(), state.assumptions);
    if (s === 'now') scene.setMode('now');
    else if (s === 'week') scene.setMode('week');
    else {
      const info = scene.setMode('ladder', L)!;
      const pct = (todayL() / L) * 100;
      $('bv-eq').innerHTML = `= ${info.vessel.name} <b class="num">${times(info.count)}</b> ${info.vessel.unit}分${info.hidden > 0 ? `（描いたのは ${count(info.shown)} ${info.vessel.unit}）` : ''}`;
      $('bv-sub').innerHTML = s === 'world'
        ? `世界の毎秒 ${volume(L / 86400).text} × 86,400 秒（推計）。あなたの今日はこの ${todayL() > 0 ? '1/' + count(Math.round(L / todayL())) : '—'}。 ${chips(['G2', 'MS1', 'L1'])}`
        : `今日の ${volume(todayL()).text} × 365 日。手前の小さいのは、ひとつ前の器（同じ縮尺）。 ${chips(['PR1', 'MR1', 'L1'])}`;
    }
    render();
  }

  function render() {
    const s = state.ladderScale;
    const L = ladderLiters(s, todayL(), weekL(), state.assumptions);
    const v = volume(L);
    const el = $('bv-liters'); el.textContent = v.value; el.dataset.value = String(L); $('bv-unit').textContent = v.unit;
    $('bv-manual').hidden = state.meStatus === 'ok' || s !== 'now';
    if (s === 'now') {
      const b = Math.floor(L / BOTTLE_LITERS);
      $('bv-eq').innerHTML = `= 500 mL ボトル <b class="num">${count(b)}</b> 本 + ${fixed(((L % BOTTLE_LITERS) / BOTTLE_LITERS) * 100, 0)}%`;
      const me = state.me;
      $('bv-sub').innerHTML = me
        ? `今日の Claude Code（実ログ、応答 ${count(me.today.messages ?? 0)} 件）。幅 ${volume(me.today.liters.low).text} – ${volume(me.today.liters.high).text}。キャッシュが無ければ ${volume(me.today.litersNoCache).text}。 ${chips(['PR1', 'MR1', 'L1'])}`
        : `実ログが無いので、手で注ぎます。ローカルで <code>python scripts/serve.py</code> から開くと、あなたの応答ごとに自動で注がれます。`;
    } else if (s === 'week') {
      const days = state.me ? Object.keys(state.me.days).length : 0;
      $('bv-eq').innerHTML = `= 500 mL ボトル <b class="num">${count(Math.floor(L / BOTTLE_LITERS))}</b> 本（${days} 日）`;
      $('bv-sub').innerHTML = state.me ? `1 段 = 1 日。棚の高さが、その日に蒸発させた水。 ${chips(['PR1', 'MR1', 'L1'])}` : '7 日の棚は実ログがあるときだけ描けます。';
    }
  }

  // 実ログの更新 → 増えた分を注ぐ
  subscribe((st, p) => {
    if (st.me !== p.me && st.me) {
      const me = st.me, day = me.asOf.slice(0, 10);
      const msgs = me.today.messages ?? 0, L = me.today.liters.mid;
      if (prevMsgs >= 0 && day === prevDay && msgs > prevMsgs && L > prevL) {
        const text = `+${volume(L - prevL).text}（応答 ${msgs - prevMsgs} 件）`;
        if (text !== lastText) { $('bv-last').textContent = text; lastText = text; }
      }
      scene.setToday(L, { instant: prevMsgs < 0 || day !== prevDay });
      prevMsgs = msgs; prevL = L; prevDay = day;
      scene.setWeek(Object.entries(me.days).map(([d, w]) => ({ day: d, liters: w.liters.mid })));
      if (st.ladderScale !== 'now') applyScale(false); else render();
    }
    if (st.ladderScale !== p.ladderScale || st.meStatus !== p.meStatus || (st.assumptions !== p.assumptions && st.ladderScale === 'world')) applyScale();
  });

  // 7 日の日付ラベル（3D の位置に HTML を重ねる）
  const labels = $('bv-labels');
  function tickLabels() {
    if (state.ladderScale !== 'week' || !state.me) { if (labels.childElementCount) labels.textContent = ''; return; }
    const days = Object.entries(state.me.days).slice(-7);
    if (labels.childElementCount !== days.length) labels.innerHTML = days.map(() => '<span class="bv-label"></span>').join('');
    days.forEach(([d, w], i) => {
      const el = labels.children[i] as HTMLElement;
      const p = scene.blockScreen(i);
      if (!p || !p.visible) { el.style.display = 'none'; return; }
      el.style.display = '';
      el.style.left = p.x + 'px'; el.style.top = p.y + 'px';
      const t = `${d.slice(5).replace('-', '/')}<b>${volume(w.liters.mid).text}</b>`;
      if (el.innerHTML !== t) el.innerHTML = t;
    });
  }

  applyScale();
  return {
    scene,
    tick(now, dt) { scene.render((now - state.t0) / 1000, dt); tickLabels(); },
    show() { scene.resize(); applyScale(); },
  };
}

export const _src = SOURCES;
