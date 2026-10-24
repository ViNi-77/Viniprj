/* 作例（仮の利用パターン）から映像とボトル画面の数字を計算する。特定の人の利用記録は使わない。 */
import ex from './example-usage.json';
import { usageWater, BOTTLE_LITERS, type ModelClass, type UsageTokens } from './model';

const cls = ex.modelClass as ModelClass;
const per = ex.perResponse as UsageTokens;
const n = ex.responsesPerDay;
const day: UsageTokens = { input: per.input * n, cw5m: per.cw5m * n, cw1h: per.cw1h * n, cr: per.cr * n, out: per.out * n };

export const EXAMPLE = {
  label: ex.label,
  modelClass: cls,
  responsesPerDay: n,
  perResponse: per,
  /** 1 応答 */
  response: usageWater(per, cls, 'mid'),
  /** 1 日 */
  dayMid: usageWater(day, cls, 'mid'),
  dayLow: usageWater(day, cls, 'low'),
  dayHigh: usageWater(day, cls, 'high'),
  dayNoCache: usageWater(day, cls, 'mid', { noCache: true }),
  get bottlesPerDay() { return Math.floor(this.dayMid.liters / BOTTLE_LITERS); },
};
