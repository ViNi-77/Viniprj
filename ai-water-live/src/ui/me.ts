/* あなたの水: serve.py の /api/me から自分の実ログの集計を取り、左上のカードと地球儀の柱に出す。
 * 静的配信（Pages / Artifact）では /api/me が無いので、案内を 1 行出す（黙って消さない）。 */
import { state, setState, subscribe, type Me } from '../state';
import { worldRates, MODEL_CLASSES, type ModelClass } from '../data/model';
import { HUBS } from '../data/hubs';
import { volume, count, fixed } from './format';
import { chips } from './ticker';

const pollMs = () => (state.view === 'bottle' ? 2000 : 5000);

export async function fetchMe(): Promise<Me | null> {
  try {
    const r = await fetch('./api/me', { cache: 'no-store' });
    if (!r.ok) return null;
    const j = (await r.json()) as Me & { error?: string };
    return j && j.today && !j.error ? j : null;
  } catch {
    return null;
  }
}

function barHTML(frac: number, cells = 10): string {
  const f = Math.max(0, Math.min(1, frac)) * cells;
  return `<span class="me-bottle" aria-hidden="true">${Array.from({ length: cells }, (_, i) => `<i style="--f:${Math.max(0, Math.min(1, f - i)).toFixed(2)}"></i>`).join('')}</span>`;
}

export function createMe(card: HTMLElement, hint: HTMLElement, onRate: (hubId: string, rate: number) => void) {
  let lastAsOf = '';
  function render() {
    const me = state.me;
    if (state.meStatus === 'unavailable') {
      card.hidden = true;
      hint.hidden = false;
      onRate(state.your.hubId, 0);
      return;
    }
    hint.hidden = true;
    if (!me) { card.hidden = true; return; }
    card.hidden = false;
    const t = me.today, L = t.liters.mid;
    const bottles = Math.floor(L / 0.5), frac = (L % 0.5) / 0.5;
    const wr = worldRates(state.assumptions);
    const sec = L / wr.litersPerSecTotal;
    const saved = Math.max(0, t.litersNoCache - L);
    const v = volume(L);
    card.innerHTML = `
      <div class="me-head"><span class="label">あなたの今日（Claude Code の実ログ）</span><span class="chips">${chips(['PR1', 'MR1', 'L1'])}</span></div>
      <div class="me-main"><span class="value num accent"><span id="me-today" data-value="${L}">${v.value}</span><small>${v.unit}</small></span>${barHTML(frac)}<span class="me-bottles num">${count(bottles)}<small>本</small></span></div>
      <div class="me-sub">幅 ${volume(t.liters.low).text} – ${volume(t.liters.high).text} · ${count(t.weightedTokens)} 加重トークン · 世界の ${sec < 1 ? fixed(sec, 3) : fixed(sec, 1)} 秒分</div>
      <div class="me-sub">7 日 ${volume(me.week.liters.mid).text} · 直近の会話 ${volume(me.session.liters.mid).text}${saved >= 0.05 ? ` · キャッシュで節水 ${volume(saved).text}` : ''}</div>`;
    // 地球儀の柱: 1 時間あたりの L を 0..1 に（1 L/時 → 0.2、50 L/時 → 1）
    const now = new Date();
    const hours = Math.max(1, now.getHours() + now.getMinutes() / 60);
    const lph = L / hours;
    onRate(state.your.hubId, L > 0 ? Math.max(0.15, Math.min(1, 0.2 + Math.log10(Math.max(1, lph)) / 2.1)) : 0);
  }
  async function poll() {
    const me = await fetchMe();
    if (me) {
      if (me.asOf !== lastAsOf) { lastAsOf = me.asOf; setState({ me, meStatus: 'ok' }); }
    } else if (state.meStatus !== 'ok') {
      setState({ meStatus: 'unavailable' });
    }
  }
  subscribe((s, p) => { if (s.me !== p.me || s.meStatus !== p.meStatus || s.assumptions !== p.assumptions || s.your.hubId !== p.your.hubId) render(); });
  render();
  void poll();
  let lastPoll = 0;
  window.setInterval(() => { const n = Date.now(); if (!document.hidden && n - lastPoll >= pollMs() - 50) { lastPoll = n; void poll(); } }, 500);
}

/** 「実ログから」: 加重トークンを入力欄へ、いちばん多い級を選ぶ */
export function meToYourTokens(which: 'today' | 'week' | 'session'): { tokens: number; modelClass: ModelClass } | null {
  const me = state.me; if (!me) return null;
  const w = me[which];
  let best: ModelClass = 'standard', bestV = -1;
  for (const [k, v] of Object.entries(w.byClass)) if (k in MODEL_CLASSES && v > bestV) { bestV = v; best = k as ModelClass; }
  return { tokens: Math.round(w.weightedTokens), modelClass: best };
}

export const _hubs = HUBS;
