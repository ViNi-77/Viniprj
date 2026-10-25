/* トークンの水 — 45 秒の映像。第 1 案（ai-water-footprint/film.html）の作りを引き継ぐ:
 * draw(f) がフレーム番号だけから絵を決める（時計・乱数を使わない）。1920×1080、60 fps、2700 フレーム、Canvas 2D。
 * ?record=1 で UI を消し window.AWF.seek(f) を公開（scripts/render_film.py が MP4 にする）。
 * 数字はすべて params.json / model.ts / example-usage.json（作例・仮の数字）から計算し、ここに直書きしない。特定の人の利用記録は使わない。 */
import { PRESETS, MODEL_CLASSES, TOKEN_WEIGHTS, VESSELS, BOTTLE_LITERS, worldRates } from '../data/model';
void BOTTLE_LITERS;
import { EXAMPLE } from '../data/example';
import { count, fixed, volume } from '../ui/format';

const W = 1920, H = 1080, FPS = 60, DUR = 45, FRAMES = DUR * FPS;
const C = { bg: '#0f1418', ink: '#f1ece2', ink2: '#9aa3a9', ink3: '#5f6a72', line: '#3b454d', water: '#4f9bd6', deep: '#2c6a9c', light: '#8cc3ea', accent: '#e07a53' };
const JP = '"Hiragino Sans", "Yu Gothic", "Meiryo", "Noto Sans CJK JP", "IPAPGothic", sans-serif';
const NUM = '"Helvetica Neue", "Segoe UI", "Hiragino Sans", "Noto Sans CJK JP", "IPAPGothic", sans-serif';
const font = (w: number, px: number, fam = JP) => `${w} ${px}px ${fam}`;

// ---- 数（すべて計算で出す）
const mid = PRESETS.mid, low = PRESETS.low, high = PRESETS.high;
const n = EXAMPLE.responsesPerDay;
const per = { cr: EXAMPLE.perResponse.cr, cw: EXAMPLE.perResponse.cw1h, out: EXAMPLE.perResponse.out, input: EXAMPLE.perResponse.input };
const perWeighted = EXAMPLE.response.weighted;
const frontierWh = MODEL_CLASSES[EXAMPLE.modelClass].whPerKTok;
const perKWh = EXAMPLE.response.kWh;
const perL = EXAMPLE.response.liters;
const film = {
  litersMid: EXAMPLE.dayMid.liters, litersLow: EXAMPLE.dayLow.liters, litersHigh: EXAMPLE.dayHigh.liters,
  litersNoCache: EXAMPLE.dayNoCache.liters, bottles: EXAMPLE.bottlesPerDay, messages: n,
};
const world = worldRates(mid);
const worldDayL = world.litersPerSecTotal * 86400;
const pool = VESSELS.find((v) => v.id === 'pool')!;

// ---- 道具
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
const lerp = (a: number, b: number, p: number) => a + (b - a) * p;
const seg = (t: number, a: number, b: number) => clamp((t - a) / (b - a), 0, 1);
const fade = (t: number, a: number, b: number, d = 0.35) => Math.min(seg(t, a, a + d), 1 - seg(t, b - d, b));
const E = { out: (p: number) => 1 - Math.pow(1 - p, 3), inOut: (p: number) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2), expo: (p: number) => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)), back: (p: number) => { const c = 1.70158; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); } };
function hash(i: number, j: number): number {
  let h = (Math.imul(i | 0, 374761393) + Math.imul((j | 0) + 1, 668265263)) ^ 0x5bd1e995;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
function tabular(g: CanvasRenderingContext2D, text: string, x: number, y: number, align: 'left' | 'center' | 'right' = 'left'): number {
  const dw = Math.max(...'0123456789'.split('').map((c) => g.measureText(c).width));
  const ws = [...text].map((c) => (/[0-9]/.test(c) ? dw : g.measureText(c).width));
  const total = ws.reduce((a, b) => a + b, 0);
  let cx = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x;
  const prev = g.textAlign; g.textAlign = 'center';
  [...text].forEach((c, i) => { g.fillText(c, cx + ws[i]! / 2, y); cx += ws[i]!; });
  g.textAlign = prev; return total;
}
function text(g: CanvasRenderingContext2D, s: string, x: number, y: number, px: number, alpha: number, o: { color?: string; weight?: number; align?: CanvasTextAlign; rise?: number; fam?: string } = {}) {
  g.save(); g.globalAlpha *= alpha; g.fillStyle = o.color ?? C.ink; g.font = font(o.weight ?? 600, px, o.fam); g.textAlign = o.align ?? 'left'; g.textBaseline = 'alphabetic';
  g.fillText(s, x, y + (1 - alpha) * (o.rise ?? 0)); g.restore();
}
function kicker(g: CanvasRenderingContext2D, s: string, x: number, y: number, a: number) {
  g.save(); g.globalAlpha *= a; g.strokeStyle = C.line; g.lineWidth = 1.5; g.beginPath(); g.moveTo(x, y - 7); g.lineTo(x + 36, y - 7); g.stroke();
  g.fillStyle = C.ink2; g.font = font(500, 24); g.fillText(s, x + 50, y); g.restore();
}
function big(g: CanvasRenderingContext2D, value: string, unit: string, x: number, y: number, px: number, a: number, color = C.ink, align: 'left' | 'center' = 'left') {
  g.save(); g.globalAlpha *= a; g.fillStyle = color; g.font = font(700, px, NUM); g.textBaseline = 'alphabetic';
  const w = tabular(g, value, x, y, align);
  g.fillStyle = C.ink2; g.font = font(500, px * 0.32); g.textAlign = 'left'; g.fillText(unit, (align === 'center' ? x + w / 2 : x + w) + px * 0.08, y);
  g.restore();
}
function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath(); g.moveTo(x + r, y); g.lineTo(x + w - r, y); g.quadraticCurveTo(x + w, y, x + w, y + r); g.lineTo(x + w, y + h - r);
  g.quadraticCurveTo(x + w, y + h, x + w - r, y + h); g.lineTo(x + r, y + h); g.quadraticCurveTo(x, y + h, x, y + h - r); g.lineTo(x, y + r); g.quadraticCurveTo(x, y, x + r, y); g.closePath();
}
// 第 1 案のボトル輪郭（200×520）
function bottlePath(g: CanvasRenderingContext2D) {
  g.beginPath();
  g.moveTo(84, 56); g.lineTo(116, 56); g.lineTo(116, 82); g.quadraticCurveTo(116, 98, 140, 110); g.quadraticCurveTo(164, 122, 164, 152); g.lineTo(164, 238);
  g.quadraticCurveTo(164, 256, 156, 268); g.quadraticCurveTo(148, 280, 148, 300); g.quadraticCurveTo(148, 320, 156, 332); g.quadraticCurveTo(164, 344, 164, 362); g.lineTo(164, 468);
  g.quadraticCurveTo(164, 498, 134, 498); g.lineTo(66, 498); g.quadraticCurveTo(36, 498, 36, 468); g.lineTo(36, 362); g.quadraticCurveTo(36, 344, 44, 332); g.quadraticCurveTo(52, 320, 52, 300);
  g.quadraticCurveTo(52, 280, 44, 268); g.quadraticCurveTo(36, 256, 36, 238); g.lineTo(36, 152); g.quadraticCurveTo(36, 122, 60, 110); g.quadraticCurveTo(84, 98, 84, 82); g.closePath();
}
function wave(g: CanvasRenderingContext2D, levelY: number, t: number, amp: number, x0: number, x1: number, bottom: number, phase = 0) {
  g.beginPath(); g.moveTo(x0, bottom); g.lineTo(x0, levelY);
  const step = Math.max(3, (x1 - x0) / 36);
  for (let x = x0; x <= x1 + step; x += step) g.lineTo(Math.min(x, x1), levelY + amp * Math.sin(x / ((x1 - x0) * 0.11) + t * 2.2 + phase) + amp * 0.45 * Math.sin(x / ((x1 - x0) * 0.045) - t * 1.3));
  g.lineTo(x1, bottom); g.closePath();
}
function bottle(g: CanvasRenderingContext2D, cx: number, by: number, h: number, frac: number, t: number, o: { alpha?: number; amp?: number; cap?: boolean; stroke?: string; fill?: string } = {}) {
  const s = h / 520;
  g.save(); g.globalAlpha *= o.alpha ?? 1; g.translate(cx - 100 * s, by - 520 * s); g.scale(s, s);
  bottlePath(g); g.fillStyle = 'rgba(79,155,214,0.07)'; g.fill();
  if (frac > 0) {
    g.save(); bottlePath(g); g.clip();
    const ly = 496 - clamp(frac, 0, 1) * (496 - 104), amp = (o.amp ?? 3) / Math.max(s, 0.05);
    const gr = g.createLinearGradient(0, ly, 0, 498); gr.addColorStop(0, o.fill ?? C.water); gr.addColorStop(1, C.deep);
    wave(g, ly, t, amp, 0, 200, 520); g.fillStyle = gr; g.fill(); g.restore();
  }
  bottlePath(g); g.strokeStyle = o.stroke ?? C.ink; g.lineWidth = 2.5 / Math.max(s, 0.25); g.lineJoin = 'round'; g.stroke();
  if (o.cap !== false) { g.fillStyle = o.stroke ?? C.ink; roundRect(g, 78, 30, 44, 28, 5); g.fill(); }
  g.restore();
}
function drop(g: CanvasRenderingContext2D, x: number, y: number, r: number, a = 1) {
  g.save(); g.globalAlpha *= a; g.fillStyle = C.water; g.beginPath(); g.moveTo(x, y - r * 2.2); g.quadraticCurveTo(x + r * 1.1, y - r * 0.4, x + r, y + r * 0.2);
  g.arc(x, y + r * 0.2, r, 0, Math.PI, false); g.quadraticCurveTo(x - r * 1.1, y - r * 0.4, x, y - r * 2.2); g.closePath(); g.fill(); g.restore();
}

// ---- 場面
function s1(g: CanvasRenderingContext2D, t: number) {   // 0–5 1 回の応答
  const a = fade(t, 0, 5, 0.3); if (a <= 0) return;
  g.save(); g.globalAlpha = a;
  kicker(g, '01', 160, 230, seg(t, 0.1, 0.5));
  text(g, 'あなたの AI が、1 回応答する。', 160, 310, 64, E.out(seg(t, 0.2, 0.8)), { rise: 20 });
  const rows: [string, number, number, string][] = [
    ['キャッシュ読み', per.cr, TOKEN_WEIGHTS.cacheRead, '前の会話を読み返す'],
    ['キャッシュ書き', per.cw, TOKEN_WEIGHTS.cacheWrite1h, '次のために覚える'],
    ['出力', per.out, TOKEN_WEIGHTS.output, '新しく書く'],
  ];
  rows.forEach(([label, v, w, note], i) => {
    const t0 = 1.0 + i * 0.6, p = E.expo(seg(t, t0, t0 + 1.2)), y = 450 + i * 120;
    const ra = seg(t, t0 - 0.1, t0 + 0.2);
    text(g, label, 160, y, 34, ra, { color: C.ink2, weight: 500 });
    text(g, note, 160, y + 36, 22, ra, { color: C.ink3, weight: 500 });
    g.save(); g.globalAlpha *= ra; g.fillStyle = C.ink; g.font = font(700, 64, NUM); tabular(g, count(Math.round(v * p)), 900, y, 'right'); g.restore();
    text(g, `× ${w}`, 940, y, 40, ra, { color: C.accent, fam: NUM });
    g.save(); g.globalAlpha *= ra; g.fillStyle = C.ink2; g.font = font(600, 40, NUM); tabular(g, count(Math.round(v * w * p)), 1420, y, 'right'); g.restore();
  });
  const ta = seg(t, 3.2, 3.6);
  g.save(); g.globalAlpha *= ta; g.strokeStyle = C.line; g.lineWidth = 2; g.beginPath(); g.moveTo(940, 790); g.lineTo(1420, 790); g.stroke(); g.restore();
  big(g, count(Math.round(perWeighted * E.out(seg(t, 3.3, 4.2)))), '加重トークン', 1420 - 520, 870, 72, ta);
  text(g, `重み = 価格比。内訳は作例（仮の数字）`, 160, 960, 22, seg(t, 3.6, 4.0), { color: C.ink3, weight: 500 });
  g.restore();
}

function s2(g: CanvasRenderingContext2D, t: number) {   // 5–13 電力 → 水
  const a = fade(t, 5, 13, 0.3); if (a <= 0) return;
  g.save(); g.globalAlpha = a;
  kicker(g, '02', 160, 230, seg(t, 5.1, 5.5));
  text(g, '電気になり、水になる。', 160, 310, 64, E.out(seg(t, 5.2, 5.8)), { rise: 20 });
  const lines: [string, string][] = [
    [`${count(Math.round(perWeighted))} 加重トークン`, ''],
    [`× ${frontierWh} Wh / 1,000（最上位モデル）`, `= ${fixed(perKWh * 1000, 0)} Wh`],
    [`× ${mid.wue} + ${mid.offsite} L / kWh（施設内 + 発電側）`, `= ${volume(perL).text}`],
  ];
  lines.forEach(([l, r], i) => {
    const t0 = 5.8 + i * 0.9, ra = E.out(seg(t, t0, t0 + 0.5));
    text(g, l, 160, 440 + i * 80, 36, ra, { weight: 500, color: i === 0 ? C.ink : C.ink2 });
    if (r) text(g, r, 160, 440 + i * 80 + 0, 36, 0); // 位置合わせ用（描かない）
    if (r) text(g, r, 860, 440 + i * 80, 40, ra, { color: i === 2 ? C.accent : C.ink, weight: 700, fam: NUM });
  });
  // ボトル 2 本: 注がれて 1 本目が満ち、2 本目へ
  const pourP = E.inOut(seg(t, 8.4, 11.6));
  const filled = perL / BOTTLE_LITERS * pourP;
  const b1 = clamp(filled, 0, 1), b2 = clamp(filled - 1, 0, 1);
  const bx = 1380, by = 960, bh = 560;
  bottle(g, bx, by, bh, b1, t, { amp: 4 });
  bottle(g, bx + 260, by, bh, b2, t, { amp: 4, alpha: seg(t, 9.6, 10.0) });
  // 注ぐ水の筋
  if (pourP > 0 && pourP < 1) {
    const tx = b1 < 1 ? bx : bx + 260;
    for (let i = 0; i < 18; i++) { const ph = ((t * 3 + i / 18) % 1); drop(g, tx + (hash(i, 3) - 0.5) * 6, lerp(by - bh - 120, by - bh * 0.4, ph), 6, 0.9); }
  }
  text(g, `1 回の応答で、500 mL ボトル ${fixed(perL / BOTTLE_LITERS, 1)} 本。`, 160, 820, 44, seg(t, 11.4, 11.9), { weight: 700, rise: 10 });
  text(g, '（中の前提。低 / 高 では桁が変わる — 最後に）', 160, 868, 24, seg(t, 11.7, 12.1), { color: C.ink3, weight: 500 });
  g.restore();
}

function s3(g: CanvasRenderingContext2D, t: number) {   // 13–21 1 日の作業
  const a = fade(t, 13, 21, 0.3); if (a <= 0) return;
  g.save(); g.globalAlpha = a;
  kicker(g, '03', 160, 200, seg(t, 13.1, 13.5));
  text(g, '1 日、AI と仕事をすると。', 160, 280, 64, E.out(seg(t, 13.2, 13.8)), { rise: 20 });
  // 棚: 1 フレームに 1 本ずつ
  const total = film.bottles, cols = 23, bw = 34, bh = 92, gx = 8, gy = 14, x0 = 900, y0 = 360;
  const fNow = Math.floor(t * FPS), f0 = Math.floor(14.2 * FPS);
  const shownN = clamp(fNow - f0 + 1, 0, total);
  for (let i = 0; i < shownN; i++) {
    const c = i % cols, r = Math.floor(i / cols);
    const age = (fNow - f0 - i) / 8, s = E.back(clamp(age, 0, 1));
    const cx = x0 + c * (bw + gx) + bw / 2, by = y0 + (r + 1) * (bh + gy);
    g.save(); g.translate(cx, by); g.scale(s, s); g.translate(-cx, -by);
    bottle(g, cx, by, bh, 1, t, { amp: 0.5, cap: true, stroke: C.ink2 });
    g.restore();
  }
  const p = shownN / total;
  big(g, fixed(film.litersMid * p, p < 1 ? 1 : 0), 'L', 160, 560, 160, seg(t, 14.0, 14.3), C.accent);
  text(g, `500 mL ボトル ${count(shownN)} 本`, 160, 640, 38, seg(t, 14.2, 14.6), { weight: 600 });
  text(g, `作例: 最上位モデルで 1 日 ${film.messages} 応答（仮の数字）`, 160, 700, 26, seg(t, 14.6, 15.0), { color: C.ink2, weight: 500 });
  text(g, `幅 ${volume(film.litersLow).text} – ${volume(film.litersHigh).text}。キャッシュが無ければ ${volume(film.litersNoCache).text}。`, 160, 744, 26, seg(t, 18.2, 18.7), { color: C.ink2, weight: 500 });
  text(g, '「1 日に数十リットル」は、使い込めば届く桁。', 160, 840, 36, seg(t, 18.8, 19.4), { weight: 700, rise: 10 });
  g.restore();
}

function s4(g: CanvasRenderingContext2D, t: number) {   // 21–29 世界
  const a = fade(t, 21, 29, 0.3); if (a <= 0) return;
  g.save(); g.globalAlpha = a;
  const density = seg(t, 21.2, 23.5) * 220;
  for (let i = 0; i < density; i++) {
    const sp = 0.9 + hash(i, 3) * 0.6, yy = ((t * 900 * sp) / 1300 + hash(i, 4)) % 1;
    g.globalAlpha = a * 0.45; drop(g, hash(i, 5) * W, yy * (H + 60) - 40, 2.2 + hash(i, 6) * 2.5); g.globalAlpha = a;
  }
  kicker(g, '04', 160, 230, seg(t, 21.1, 21.5));
  text(g, '世界では、毎秒。', 160, 310, 64, E.out(seg(t, 21.2, 21.8)), { rise: 20 });
  const cp = E.expo(seg(t, 21.8, 24.5));
  big(g, count(Math.round(world.tokensPerSec * cp)), 'トークン / 秒', 160, 480, 120, seg(t, 21.8, 22.1));
  big(g, fixed(world.litersPerSecTotal * cp, 0), 'L / 秒', 160, 640, 120, seg(t, 22.4, 22.7), C.light);
  text(g, `Google（月 ${count(1.3e15)} トークン）+ Microsoft（年 ${count(5e14)}）× ${mid.worldMultiplier}（推計）`, 160, 700, 24, seg(t, 23.0, 23.4), { color: C.ink3, weight: 500 });
  const pools = worldDayL / pool.liters;
  text(g, `= 1 日で 25 m プール ${count(Math.round(pools))} 杯`, 160, 790, 44, seg(t, 24.8, 25.3), { weight: 700 });
  const cols = 40, gw = 34, gh = 12, gx0 = 160, gy0 = 830, maxN = Math.min(Math.round(pools), 480);
  const fNow = Math.floor(t * FPS), f0 = Math.floor(25.2 * FPS);
  for (let i = 0; i < clamp(fNow - f0, 0, maxN); i++) {
    const c = i % cols, r = Math.floor(i / cols);
    g.fillStyle = C.water; g.globalAlpha = a * 0.9; roundRect(g, gx0 + c * (gw + 4), gy0 + r * (gh + 4), gw, gh, 2); g.fill(); g.globalAlpha = a;
  }
  if (pools > maxN) text(g, `…ほか ${count(Math.round(pools - maxN))} 杯`, 1760, 1050, 22, seg(t, 28.0, 28.4), { color: C.ink3, weight: 500, align: 'right' });
  g.restore();
}

function s5(g: CanvasRenderingContext2D, t: number) {   // 29–37 器の梯子
  const a = fade(t, 29, 37, 0.3); if (a <= 0) return;
  g.save(); g.globalAlpha = a;
  kicker(g, '05', 160, 200, seg(t, 29.1, 29.5));
  text(g, '器を大きくしていくと。', 160, 280, 64, E.out(seg(t, 29.2, 29.8)), { rise: 20 });
  // 実寸比の器を、カメラが引くように縮尺を log で変える。各段の縮尺は「その器が幅 1,000 px・高さ 460 px に収まる」値
  const stages = VESSELS;
  const fit = (v: (typeof VESSELS)[number]) => Math.min(460 / v.h, 1000 / v.w);
  const p = seg(t, 30.0, 35.8) * (stages.length - 1);
  const k = Math.floor(clamp(p, 0, stages.length - 1.0001)), f = E.inOut(p - k);
  const pxPerM = Math.exp(lerp(Math.log(fit(stages[k]!)), Math.log(fit(stages[Math.min(k + 1, stages.length - 1)]!)), f));
  const ground = 900, right = 1100;
  g.strokeStyle = C.line; g.lineWidth = 1.5; g.beginPath(); g.moveTo(120, ground); g.lineTo(1800, ground); g.stroke();
  // 右端をそろえ、小さい器ほど右に（大きい器の手前に）置く
  for (let i = stages.length - 1; i >= 0; i--) {
    const v = stages[i]!, w = v.w * pxPerM, h = v.h * pxPerM;
    // 画面に収まらない器は、縮尺が追いつくまで出さない（収まりかけたら薄く出す）
    const tooBig = Math.max(h / 520, w / 1100);
    const al = clamp((1.35 - tooBig) / 0.35, 0, 1) * clamp(h / 3, 0, 1);
    if (al <= 0) continue;
    const xr = right - (i === stages.length - 1 ? 0 : 0);
    g.save(); g.globalAlpha *= al;
    if (v.id === 'bottle') bottle(g, xr - w / 2, ground, h, 1, t, { amp: 0.5, stroke: C.ink2 });
    else if (v.id === 'dome') { g.beginPath(); g.ellipse(xr - w / 2, ground, w / 2, h, 0, Math.PI, 0); g.closePath(); g.fillStyle = 'rgba(79,155,214,0.30)'; g.fill(); g.strokeStyle = C.ink; g.lineWidth = 2; g.stroke(); }
    else { g.fillStyle = i === k + 1 ? 'rgba(79,155,214,0.35)' : 'rgba(79,155,214,0.55)'; g.fillRect(xr - w, ground - h, w, h); g.strokeStyle = C.ink; g.lineWidth = 2; g.strokeRect(xr - w, ground - h, w, h); }
    g.restore();
  }
  const cur = stages[Math.round(clamp(p, 0, stages.length - 1))]!;
  text(g, cur.name, 1240, 470, 52, 1, { weight: 700 });
  text(g, `${volume(cur.liters).text}（1 ${cur.unit}）`, 1240, 530, 30, 1, { color: C.ink2, weight: 500 });
  const cnt = film.litersMid / cur.liters;
  text(g, `あの 1 日 = ${cnt >= 1 ? fixed(cnt, cnt >= 10 ? 0 : 1) : cnt >= 0.1 ? fixed(cnt, 2) : '1/' + count(Math.round(1 / cnt))} ${cur.unit}`, 1240, 590, 30, 1, { color: C.accent, weight: 600 });
  const wc = worldDayL / cur.liters;
  text(g, `世界の 1 日 = ${wc >= 10 ? count(Math.round(wc)) : fixed(wc, 2)} ${cur.unit}`, 1240, 640, 30, 1, { color: C.light, weight: 600 });
  text(g, '同じ縮尺。小さい器は右下の点になっていく。', 160, 960, 24, seg(t, 31, 31.5), { color: C.ink3, weight: 500 });
  g.restore();
}

function s6(g: CanvasRenderingContext2D, t: number) {   // 37–45 幅と結び
  const a = fade(t, 37, 45, 0.5); if (a <= 0) return;
  g.save(); g.globalAlpha = a;
  const rp = seg(t, 37.2, 40.6);
  if (rp < 1) {
    kicker(g, '06', 160, 230, seg(t, 37.1, 37.5));
    text(g, 'ただし、数字には幅がある。', 160, 310, 64, E.out(seg(t, 37.2, 37.8)), { rise: 20 });
    const lv = [[low, film.litersLow, '事業者の公表値'], [mid, film.litersMid, '公的統計の平均'], [high, film.litersHigh, '研究推計の上限']] as const;
    const maxL = Math.log10(film.litersHigh + 1);
    lv.forEach(([p, L, name], i) => {
      const y = 460 + i * 130, ra = E.out(seg(t, 37.8 + i * 0.4, 38.4 + i * 0.4));
      text(g, `${p.label.slice(0, 1)} · ${name}`, 160, y, 32, ra, { weight: 600 });
      text(g, `${p.whPerKTok} Wh/1,000 · ${p.wue} + ${p.offsite} L/kWh`, 160, y + 36, 22, ra, { color: C.ink3, weight: 500 });
      g.save(); g.globalAlpha *= ra * (1 - seg(t, 40.0, 40.6)); g.fillStyle = i === 1 ? C.accent : C.water;
      g.fillRect(760, y - 34, (Math.log10(L + 1) / maxL) * 760 * ra, 40); g.restore();
      big(g, volume(L).value, volume(L).unit, 1560, y, 48, ra * (1 - seg(t, 40.0, 40.6)));
    });
    text(g, `同じ作例（1 日 ${film.messages} 応答）を、3 つの前提で数えた値`, 160, 880, 24, seg(t, 39.0, 39.4) * (1 - seg(t, 40.0, 40.6)), { color: C.ink3, weight: 500 });
  }
  // 結び
  const lvY = H - E.out(seg(t, 40.6, 43.0)) * 300;
  if (t > 40.6) {
    const gr = g.createLinearGradient(0, lvY, 0, H); gr.addColorStop(0, C.water); gr.addColorStop(1, C.deep);
    wave(g, lvY, t, 8, 0, W, H); g.fillStyle = gr; g.fill();
    text(g, 'トークンの水', W / 2, 400, 120, E.out(seg(t, 41.0, 41.8)), { weight: 700, align: 'center', rise: 20 });
    text(g, '世界と、あなたの AI が蒸発させる淡水を、器で見る', W / 2, 480, 34, seg(t, 41.6, 42.2), { color: C.ink2, weight: 500, align: 'center' });
    // ステータス行の見本
    const sa = seg(t, 42.4, 43.0);
    g.save(); g.globalAlpha *= sa; g.fillStyle = '#0b0f12'; roundRect(g, W / 2 - 420, 560, 840, 64, 10); g.fill(); g.strokeStyle = C.line; g.lineWidth = 1.5; g.stroke();
    g.fillStyle = C.ink; g.font = font(500, 28, 'ui-monospace, Menlo, Consolas, monospace'); g.textAlign = 'center';
    const L = film.litersMid * 0.37;
    g.fillText(`💧今日 ${fixed(L, 1)} L ▕██▍     ▏${Math.floor(L / 0.5)}本 · 節水 ${fixed(film.litersNoCache * 0.37 - L, 0)} L`, W / 2, 602); g.restore();
    text(g, 'あなたの今日は、Claude Code のステータス行に出せる。', W / 2, 680, 30, seg(t, 43.0, 43.5), { weight: 600, align: 'center' });
    text(g, '出典: Google 2025 / Microsoft Research 2026 / LBNL 2024 / Anthropic 価格（重み）。利用量は作例（仮の数字）。すべて推計。', W / 2, 730, 20, seg(t, 43.4, 43.9), { color: C.ink3, weight: 500, align: 'center' });
  }
  g.restore();
}

// ---- 1 フレーム
const canvas = document.getElementById('stage') as HTMLCanvasElement;
const g = canvas.getContext('2d', { alpha: false })!;
let grainCanvas: HTMLCanvasElement | null = null;
function grain(f: number) {
  if (!grainCanvas) {
    grainCanvas = document.createElement('canvas'); grainCanvas.width = grainCanvas.height = 256;
    const gg = grainCanvas.getContext('2d')!; const img = gg.createImageData(256, 256);
    for (let i = 0; i < 256 * 256; i++) { const v = 180 + Math.floor(hash(i, 7) * 75); img.data[i * 4] = v; img.data[i * 4 + 1] = v; img.data[i * 4 + 2] = v; img.data[i * 4 + 3] = 255; }
    gg.putImageData(img, 0, 0);
  }
  g.save(); g.globalAlpha = 0.045; g.globalCompositeOperation = 'overlay';
  g.translate(-Math.floor(hash(f, 11) * 256), -Math.floor(hash(f, 13) * 256));
  g.fillStyle = g.createPattern(grainCanvas, 'repeat')!; g.fillRect(0, 0, W + 256, H + 256); g.restore();
}
function draw(f: number) {
  f = clamp(Math.floor(f), 0, FRAMES - 1);
  const t = f / FPS;
  g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
  g.fillStyle = C.bg; g.fillRect(0, 0, W, H);
  s1(g, t); s2(g, t); s3(g, t); s4(g, t); s5(g, t); s6(g, t);
  const vg = g.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.95); vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,0.42)');
  g.fillStyle = vg; g.fillRect(0, 0, W, H);
  grain(f);
  const out = seg(t, 44.5, 45); if (out > 0) { g.fillStyle = `rgba(7,9,11,${out})`; g.fillRect(0, 0, W, H); }
}

// ---- 再生制御
declare global { interface Window { AWF: { seek: (f: number) => number; frames: number; fps: number; play?: () => void; pause?: () => void } } }
const params = new URLSearchParams(location.search);
const record = params.get('record') === '1';
let frame = 0, playing = false, startWall = 0, startFrame = 0, raf = 0;
const $ = (id: string) => document.getElementById(id) as HTMLElement;
const pad = (x: number, w: number) => String(x).padStart(w, '0');
const fmtT = (fr: number) => { const s = fr / FPS; return `${pad(Math.floor(s / 60), 2)}:${pad(Math.floor(s % 60), 2)}.${pad(Math.floor((s % 1) * 100), 2)}`; };
function show(f: number) {
  frame = clamp(Math.floor(f), 0, FRAMES - 1); draw(frame);
  if (!record) { ($('scrub') as HTMLInputElement).value = String(frame); $('time').textContent = `${fmtT(frame)} / ${fmtT(FRAMES)}`; }
  return frame;
}
function tick() {
  if (!playing) return;
  const f = startFrame + Math.floor(((performance.now() - startWall) * FPS) / 1000);
  if (f >= FRAMES) { show(FRAMES - 1); pause(); return; }
  show(f); raf = requestAnimationFrame(tick);
}
function play() { if (playing) return; if (frame >= FRAMES - 1) frame = 0; playing = true; startWall = performance.now(); startFrame = frame; $('play').textContent = '停止'; $('play').setAttribute('aria-pressed', 'true'); raf = requestAnimationFrame(tick); }
function pause() { playing = false; cancelAnimationFrame(raf); $('play').textContent = '再生'; $('play').setAttribute('aria-pressed', 'false'); }
function seek(f: number) { const was = playing; pause(); show(f); if (was) play(); }

if (record) {
  document.body.classList.add('record');
  window.AWF = { seek: (f) => show(f), frames: FRAMES, fps: FPS };
  show(Number(params.get('f') ?? 0));
} else {
  window.AWF = { seek: (f) => { seek(f); return frame; }, frames: FRAMES, fps: FPS, play, pause };
  $('play').addEventListener('click', () => (playing ? pause() : play()));
  $('restart').addEventListener('click', () => { pause(); show(0); play(); });
  $('scrub').addEventListener('input', () => seek(Number(($('scrub') as HTMLInputElement).value)));
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space') { e.preventDefault(); playing ? pause() : play(); }
    else if (e.code === 'ArrowRight') { e.preventDefault(); seek(frame + (e.shiftKey ? FPS : 1)); }
    else if (e.code === 'ArrowLeft') { e.preventDefault(); seek(frame - (e.shiftKey ? FPS : 1)); }
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
  show(0);
  play();
}
