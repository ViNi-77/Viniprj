/* 日本語の数値整形。Intl は 万・億 を出さないので手書き。 */
const nfCache = new Map<number, Intl.NumberFormat>();
export function fixed(v: number, d: number): string {
  let f = nfCache.get(d);
  if (!f) { f = new Intl.NumberFormat('ja-JP', { minimumFractionDigits: d, maximumFractionDigits: d }); nfCache.set(d, f); }
  return f.format(v);
}
const isInt = (v: number) => Math.abs(v - Math.round(v)) < 1e-9;
function autoDecimals(v: number, minD = 0): number {
  const a = Math.abs(v);
  let d = a < 10 ? 2 : a < 100 ? 1 : 0;
  if (isInt(a) && minD === 0) d = 0;
  return Math.max(d, minD);
}

/** 個数（トークン数など）。1 万以上は 万・億・兆・京 */
export function count(n: number, minD = 0): string {
  const a = Math.abs(n);
  if (a < 1e4) return fixed(n, autoDecimals(n, minD));
  const big = (v: number, u: string) => fixed(v, v < 100 && !(isInt(v) && minD === 0) ? Math.max(1, minD) : minD) + u;
  if (a < 1e8) return big(n / 1e4, '万');
  if (a < 1e12) return big(n / 1e8, '億');
  if (a < 1e16) return big(n / 1e12, '兆');
  return big(n / 1e16, '京');
}

export type VolumeUnit = 'mL' | 'L' | '万 L' | '億 L' | '兆 L';
const VOL: Record<VolumeUnit, number> = { 'mL': 1e-3, 'L': 1, '万 L': 1e4, '億 L': 1e8, '兆 L': 1e12 };
export function volumeUnitFor(liters: number): VolumeUnit {
  const a = Math.abs(liters);
  return a < 1 ? 'mL' : a < 1e4 ? 'L' : a < 1e8 ? '万 L' : a < 1e12 ? '億 L' : '兆 L';
}
/** 水量。unit を渡すと単位を固定する（転がる間に単位が変わらないように） */
export function volume(liters: number, unit?: VolumeUnit, minD = 0): { value: string; unit: VolumeUnit; text: string } {
  const u = unit ?? volumeUnitFor(liters);
  const v = liters / VOL[u];
  const d = u === 'mL' || u === 'L' ? autoDecimals(v, minD) : Math.max(v < 100 && !isInt(v) ? 1 : 0, minD);
  const value = fixed(v, d);
  return { value, unit: u, text: value + ' ' + u };
}

export type EnergyUnit = 'Wh' | 'kWh' | 'MWh' | 'GWh' | 'TWh';
const EN: Record<EnergyUnit, number> = { Wh: 1e-3, kWh: 1, MWh: 1e3, GWh: 1e6, TWh: 1e9 };
export function energyUnitFor(kWh: number): EnergyUnit {
  const a = Math.abs(kWh);
  return a < 1 ? 'Wh' : a < 1e3 ? 'kWh' : a < 1e6 ? 'MWh' : a < 1e9 ? 'GWh' : 'TWh';
}
export function energy(kWh: number, unit?: EnergyUnit, minD = 0) {
  const u = unit ?? energyUnitFor(kWh);
  const v = kWh / EN[u];
  const value = fixed(v, autoDecimals(v, minD));
  return { value, unit: u, text: value + ' ' + u };
}

export type PowerUnit = 'W' | 'kW' | 'MW' | 'GW';
export function power(watts: number) {
  const a = Math.abs(watts);
  const u: PowerUnit = a < 1e3 ? 'W' : a < 1e6 ? 'kW' : a < 1e9 ? 'MW' : 'GW';
  const v = watts / { W: 1, kW: 1e3, MW: 1e6, GW: 1e9 }[u];
  return { value: fixed(v, autoDecimals(v)), unit: u, text: fixed(v, autoDecimals(v)) + ' ' + u };
}

/** 「◯杯分」 */
export function times(x: number): string {
  if (x >= 100) return count(Math.round(x));
  if (isInt(x)) return fixed(x, 0);
  if (x >= 10) return fixed(x, 1);
  if (x >= 0.01) return fixed(x, 2);
  return fixed(x, 3);
}

export function duration(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(r)}` : `${pad(m)}:${pad(r)}`;
}
