/* 共有カード（1200×630 PNG）。Canvas に描く。日本語は OS のフォントに任せる。 */
import type { yourResult } from './yourTokens';
import { COMPARISONS, MODEL_CLASSES } from '../data/model';
import { state } from '../state';
import { count, volume, energy, times } from './format';

type Res = ReturnType<typeof yourResult>;
const FONT = '"Hiragino Sans", "Yu Gothic UI", "Meiryo", "Noto Sans CJK JP", "IPAPGothic", system-ui, sans-serif';

export async function renderShareCard(res: Res): Promise<Blob> {
  if (document.fonts && document.fonts.ready) { try { await document.fonts.ready; } catch { /* 無視 */ } }
  const W = 1200, H = 630;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d')!;
  const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#0b1118'); bg.addColorStop(1, '#07090b');
  g.fillStyle = bg; g.fillRect(0, 0, W, H);
  // 下の水面
  const wl = g.createLinearGradient(0, 470, 0, H); wl.addColorStop(0, '#2f6fa5'); wl.addColorStop(1, '#1d4f7c');
  g.fillStyle = wl; g.beginPath(); g.moveTo(0, H);
  for (let x = 0; x <= W; x += 20) g.lineTo(x, 478 + Math.sin(x / 90) * 6 + Math.sin(x / 37) * 3);
  g.lineTo(W, H); g.closePath(); g.fill();

  g.fillStyle = '#9aa3a9'; g.font = `500 22px ${FONT}`; g.textBaseline = 'alphabetic';
  g.fillText('トークンの水 — 生成 AI の冷却で蒸発した淡水', 64, 70);
  g.fillStyle = '#f1ece2'; g.font = `700 54px ${FONT}`;
  g.fillText(`${count(res.tokens)} トークン${res.perDay ? '（1 日 ' + count(state.your.tokens) + ' × 365 日）' : ''}`, 64, 150);
  const total = volume(res.r.totalL.value);
  g.fillStyle = '#e07a53'; g.font = `800 150px "Helvetica Neue", "Segoe UI", ${FONT}`; g.fillText(total.value, 60, 310);
  const w = g.measureText(total.value).width;
  g.fillStyle = '#9aa3a9'; g.font = `600 44px ${FONT}`; g.fillText(total.unit + ' の淡水', 60 + w + 18, 310);
  // 換算 3 行
  const L = res.r.totalL.value;
  const list = COMPARISONS.filter((x) => L / x.liters >= 0.05).slice(-3);
  g.fillStyle = '#f1ece2'; g.font = `600 30px ${FONT}`;
  (list.length ? list : [COMPARISONS[0]]).forEach((x, i) => g.fillText(`= ${x!.name} ${times(L / x!.liters)} ${x!.unit}分`, 64, 372 + i * 40));
  // 右下: 前提
  g.fillStyle = '#9aa3a9'; g.font = `500 22px ${FONT}`; g.textAlign = 'right';
  g.fillText(`電力 ${energy(res.r.kWh.value).text} · ${MODEL_CLASSES[state.your.modelClass].label} · ${res.hub.name}`, W - 64, 372);
  g.fillText(`施設内 WUE ${res.wue.toFixed(2)} L/kWh + 発電側 ${state.assumptions.offsite.toFixed(1)} L/kWh（${res.ids.join(', ')}）`, W - 64, 408);
  g.fillText(`推計 · ${new Date().toISOString().slice(0, 10)}`, W - 64, 444);
  g.textAlign = 'left';
  g.fillStyle = 'rgba(255,255,255,0.75)'; g.font = `500 20px ${FONT}`;
  g.fillText('出典: Google 2025 / OpenAI 2025 / Jegham ら 2025 / LBNL 2024 / Microsoft FY25 / Amazon 2024', 64, 600);
  return new Promise((resolve, reject) => c.toBlob((b) => (b ? resolve(b) : reject(new Error('toBlob failed'))), 'image/png'));
}
