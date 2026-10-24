/* 状態は 1 つ。購読者に (state, prev) を渡す。 */
import { PRESETS, type Assumptions, type Level, type ModelClass, type LadderScale } from './data/model';

export interface YourTokens {
  tokens: number;
  perDay: boolean;       // 「1 日あたり」で入力しているか
  modelClass: ModelClass;
  hubId: string;         // 地域（施設内 WUE の倍率に使う）
}

export interface MeWater {
  tokens: Record<'input' | 'cw5m' | 'cw1h' | 'cr' | 'out', number>;
  tokensTotal: number;
  messages: number;
  weightedTokens: number;
  byClass: Record<string, number>;
  kWh: Record<'low' | 'mid' | 'high', number>;
  liters: Record<'low' | 'mid' | 'high', number>;
  litersOnsite: number;
  litersNoCache: number;
  bottles: number;
}
export interface Me { asOf: string; today: MeWater; week: MeWater; session: MeWater; sessionId: string | null; days: Record<string, MeWater> }

export interface State {
  t0: number;
  assumptions: Assumptions;
  preset: Level | 'custom';
  your: YourTokens;
  tab: 'your' | 'assumptions' | 'method';
  hoverHub: string | null;
  reduced: boolean;
  webgl: boolean;
  me: Me | null;
  meStatus: 'unknown' | 'ok' | 'unavailable';
  view: 'globe' | 'bottle';
  ladderScale: LadderScale;
}

const prefersReduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export const state: State = {
  t0: Date.now(),
  assumptions: { ...PRESETS.mid },
  preset: 'mid',
  your: { tokens: 1e10, perDay: false, modelClass: 'standard', hubId: 'tyo' },
  tab: 'your',
  hoverHub: null,
  reduced: prefersReduced,
  webgl: true,
  me: null,
  meStatus: 'unknown',
  view: 'globe',
  ladderScale: 'now',
};

type Listener = (s: State, prev: State) => void;
const listeners: Listener[] = [];
export function subscribe(fn: Listener) { listeners.push(fn); return () => { const i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); }; }
export function setState(patch: Partial<State>) {
  const prev = { ...state };
  Object.assign(state, patch);
  for (const fn of listeners) fn(state, prev);
}
export function setAssumption(key: keyof Assumptions, value: number) {
  setState({ assumptions: { ...state.assumptions, [key]: value }, preset: 'custom' });
}
export function applyPreset(level: Level) {
  const p = PRESETS[level];
  setState({ assumptions: { whPerKTok: p.whPerKTok, wue: p.wue, offsite: p.offsite, worldMultiplier: p.worldMultiplier }, preset: level });
  try { localStorage.setItem('awl.preset', level); } catch { /* 無視 */ }
}
export function loadPrefs() {
  try {
    const p = localStorage.getItem('awl.preset') as Level | null;
    if (p && PRESETS[p]) { state.assumptions = { ...PRESETS[p] }; state.preset = p; }
  } catch { /* 無視 */ }
}
