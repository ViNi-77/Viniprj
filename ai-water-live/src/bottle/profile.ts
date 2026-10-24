import * as THREE from 'three';

/* 500 mL ペットボトルの輪郭。第 1 案（ai-water-footprint/js/data.js の bottle.path、200×520 の座標）の右半分を
 * 半径 × 高さ（m、上向き）に直す。高さ 21 cm、最大径 6.1 cm。 */
const H_UNITS = 442, BOTTOM = 498, CX = 100;
export const BOTTLE_H = 0.21;
const S = BOTTLE_H / H_UNITS;

type Pt = [number, number];
// SVG の順（首の上 → 底）。[x, y] と、2 次ベジェは [制御点, 終点]
const SEGS: (Pt | [Pt, Pt])[] = [
  [116, 56], [116, 82], [[116, 98], [140, 110]], [[164, 122], [164, 152]], [164, 238],
  [[164, 256], [156, 268]], [[148, 280], [148, 300]], [[148, 320], [156, 332]], [[164, 344], [164, 362]],
  [164, 468], [[164, 498], [134, 498]], [100, 498],
];

function svgPoints(): Pt[] {
  const out: Pt[] = [];
  let cur: Pt = SEGS[0] as Pt;
  out.push(cur);
  for (let i = 1; i < SEGS.length; i++) {
    const s = SEGS[i]!;
    if (typeof s[0] === 'number') { cur = s as Pt; out.push(cur); continue; }
    const [c, e] = s as [Pt, Pt];
    for (let k = 1; k <= 10; k++) {
      const t = k / 10, u = 1 - t;
      out.push([u * u * cur[0] + 2 * u * t * c[0] + t * t * e[0], u * u * cur[1] + 2 * u * t * c[1] + t * t * e[1]]);
    }
    cur = e;
  }
  return out;
}

/** 外側（ガラス）の輪郭: 底（r=0）→ 首の上 */
export function outerProfile(): THREE.Vector2[] {
  return svgPoints().reverse().map(([x, y]) => new THREE.Vector2((x - CX) * S, (BOTTOM - y) * S));
}

/** 内側（水）の輪郭: 肉厚 1.2 単位ぶん細く、底を 1.5 単位上げる */
export function innerProfile(): THREE.Vector2[] {
  const wall = 1.2 * S, base = 1.5 * S;
  return outerProfile().map((p) => new THREE.Vector2(Math.max(0, p.x - wall), Math.max(base, p.y)));
}

const INNER = innerProfile();
/** 高さ y（m）での内径 */
export function innerRadiusAt(y: number): number {
  for (let i = 1; i < INNER.length; i++) {
    const a = INNER[i - 1]!, b = INNER[i]!;
    if (y >= a.y && y <= b.y && b.y > a.y) return a.x + ((b.x - a.x) * (y - a.y)) / (b.y - a.y);
  }
  return y < INNER[0]!.y ? 0 : INNER[INNER.length - 1]!.x;
}

/** 水位（0..1 = 0..500 mL）→ 高さ。体積は断面積の積分で求める（くびれ・肩でも正しい水位） */
const LUT: { y: number; v: number }[] = (() => {
  const yb = INNER[0]!.y, yt = INNER[INNER.length - 1]!.y;
  const steps = 400, out = [{ y: yb, v: 0 }];
  let v = 0;
  for (let i = 1; i <= steps; i++) {
    const y0 = yb + ((yt - yb) * (i - 1)) / steps, y1 = yb + ((yt - yb) * i) / steps;
    const r = innerRadiusAt((y0 + y1) / 2);
    v += Math.PI * r * r * (y1 - y0);
    out.push({ y: y1, v });
  }
  return out;
})();
const V_FULL_AT = (() => {
  // 500 mL の線は肩の付け根（首の手前）。輪郭全体の体積に対する比で決める
  const total = LUT[LUT.length - 1]!.v;
  return total * 0.93;
})();
export function levelY(frac: number): number {
  const target = Math.max(0, Math.min(1, frac)) * V_FULL_AT;
  for (let i = 1; i < LUT.length; i++) if (LUT[i]!.v >= target) {
    const a = LUT[i - 1]!, b = LUT[i]!;
    return a.y + ((b.y - a.y) * (target - a.v)) / Math.max(1e-12, b.v - a.v);
  }
  return LUT[LUT.length - 1]!.y;
}
export const NECK_TOP = (BOTTOM - 56) * S;
export const BOTTLE_R = 64 * S;
