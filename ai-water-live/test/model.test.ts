import { describe, it, expect } from 'vitest';
import { PRESETS, waterFor, worldRates, worldSince, WORLD_BASE_TPS, SOURCES, COMPARISONS, MODEL_CLASSES, chooseVessel, ladderLiters, VESSELS } from '../src/data/model';
import { HUBS, HUB_SHARE_TOTAL } from '../src/data/hubs';

describe('計算式の代表値（docs/02 の表と一致させる）', () => {
  it('中: 100 億トークン → 10 MWh、約 49 kL', () => {
    const a = PRESETS.mid;
    const r = waterFor(1e10, a.whPerKTok, a.wue, a.offsite, a.sourceIds);
    expect(r.kWh.value).toBeCloseTo(10000, 0);
    expect(r.onsiteL.value).toBeCloseTo(3750, 0);
    expect(r.totalL.value).toBeCloseTo(48750, 0);
  });
  it('低: 100 億トークン → 3 MWh、450 L（施設内のみ）', () => {
    const a = PRESETS.low;
    const r = waterFor(1e10, a.whPerKTok, a.wue, a.offsite, a.sourceIds);
    expect(r.kWh.value).toBeCloseTo(3000, 0);
    expect(r.totalL.value).toBeCloseTo(450, 0);
  });
  it('高: 100 億トークン → 30 MWh、160 kL', () => {
    const a = PRESETS.high;
    const r = waterFor(1e10, a.whPerKTok, a.wue, a.offsite, a.sourceIds);
    expect(r.totalL.value).toBeCloseTo(160200, 0);
  });
  it('中: 1,000 トークン ≈ 4.9 mL', () => {
    const a = PRESETS.mid;
    expect(waterFor(1000, a.whPerKTok, a.wue, a.offsite, a.sourceIds).totalL.value * 1000).toBeCloseTo(4.875, 1);
  });
  it('世界の土台は約 5.1 億トークン/秒', () => {
    expect(WORLD_BASE_TPS / 1e8).toBeCloseTo(5.1, 0);
  });
  it('中: 世界 ≈ 3.7 GW、約 5,000 L/秒（発電含む）、約 380 L/秒（施設内）', () => {
    const r = worldRates(PRESETS.mid);
    expect(r.watts / 1e9).toBeCloseTo(3.7, 0);
    expect(r.litersPerSecTotal).toBeGreaterThan(4500);
    expect(r.litersPerSecTotal).toBeLessThan(5500);
    expect(r.litersPerSecOnsite).toBeGreaterThan(340);
    expect(r.litersPerSecOnsite).toBeLessThan(420);
  });
  it('累計は経過秒に比例し、足し込まない', () => {
    const a = PRESETS.mid;
    expect(worldSince(120, a).litersTotal).toBeCloseTo(worldSince(60, a).litersTotal * 2, 6);
  });
});

describe('出典と仮定の整合', () => {
  it('プリセットとモデルの級の出典 ID はすべて SOURCES にある', () => {
    for (const p of Object.values(PRESETS)) for (const id of p.sourceIds) expect(SOURCES[id]).toBeDefined();
    for (const m of Object.values(MODEL_CLASSES)) for (const id of m.sourceIds) expect(SOURCES[id]).toBeDefined();
    for (const c of COMPARISONS) for (const id of c.sourceIds) expect(SOURCES[id]).toBeDefined();
  });
  it('モデルの級は 4 つで、例示と時点を持つ', () => {
    expect(Object.keys(MODEL_CLASSES)).toEqual(['light', 'standard', 'frontier', 'upper']);
    for (const m of Object.values(MODEL_CLASSES)) expect(m.examples.length).toBeGreaterThan(0);
  });
  it('拠点のシェアは合計 100', () => {
    expect(HUB_SHARE_TOTAL).toBe(100);
    expect(HUBS.length).toBe(20);
  });
});

describe('器の梯子', () => {
  it('量に合う器を選ぶ', () => {
    expect(chooseVessel(0.3).vessel.id).toBe('bottle');
    expect(chooseVessel(85).vessel.id).toBe('bottle');       // 170 本 ≤ 300 本は棚で見せる
    expect(chooseVessel(85).full).toBe(170);
    expect(chooseVessel(200).vessel.id).toBe('bath');        // 400 本 > 300 → 浴槽 1 杯
    expect(chooseVessel(38000).vessel.id).toBe('pool');      // 浴槽 190 杯 > 60 → プール 0.1 杯
  });
  it('1 年換算と世界の 1 日', () => {
    const a = PRESETS.mid;
    expect(ladderLiters('year', 100, 0, a)).toBe(36500);
    const w = ladderLiters('world', 0, 0, a);
    expect(w / 1e8).toBeGreaterThan(4);                       // 約 4.3 億 L
    expect(chooseVessel(w).vessel.id).toBe('dome');            // プール約 1,100 杯 > 60 → 東京ドーム 0.35 杯
    expect(chooseVessel(w).count).toBeGreaterThan(0.3);
  });
  it('器は大きさ順', () => {
    for (let i = 1; i < VESSELS.length; i++) expect(VESSELS[i]!.liters).toBeGreaterThan(VESSELS[i - 1]!.liters);
  });
});

import { usageWater } from '../src/data/model';
import { EXAMPLE } from '../src/data/example';
describe('内訳 → 水（water_meter.py と同じ式）と作例', () => {
  it('価格比の重みと級の Wh', () => {
    const r = usageWater({ input: 1000, cw5m: 0, cw1h: 0, cr: 100000, out: 2000 }, 'frontier', 'mid');
    expect(r.weighted).toBe(21000);
    expect(r.kWh).toBeCloseTo(0.063, 6);
    expect(r.liters).toBeCloseTo(0.063 * 4.875, 6);
  });
  it('作例: 1 応答 約 0.86 L、1 日 100 応答で約 86 L', () => {
    expect(EXAMPLE.response.weighted).toBe(58550);
    expect(EXAMPLE.response.liters).toBeCloseTo(0.856, 2);
    expect(EXAMPLE.dayMid.liters).toBeCloseTo(85.6, 0);
    expect(EXAMPLE.dayNoCache.liters).toBeGreaterThan(EXAMPLE.dayMid.liters);
    expect(EXAMPLE.dayLow.liters).toBeLessThan(EXAMPLE.dayMid.liters);
    expect(EXAMPLE.dayHigh.liters).toBeGreaterThan(EXAMPLE.dayMid.liters);
  });
});
