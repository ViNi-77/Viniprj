/* 日本語の数値整形。Intl は 万/億 を出さないので手書き。 */
window.AW = window.AW || {};

AW.fmt = (function () {
  const nf = (d) => new Intl.NumberFormat('ja-JP', { minimumFractionDigits: d, maximumFractionDigits: d });
  const cache = {};
  const fixed = (v, d) => (cache[d] || (cache[d] = nf(d))).format(v);

  /** 桁に応じた小数桁。minD で最低桁数を指定できる（ライブ表示で動きを見せるため）。 */
  function decimals(v, minD) {
    const a = Math.abs(v);
    let d = a < 10 ? 2 : a < 100 ? 1 : 0;
    if (Math.abs(a - Math.round(a)) < 1e-9) d = 0; // 整数は小数を出さない（2.00 L → 2 L）
    return Math.max(d, minD || 0);
  }

  /** mL → { value, unit, text }。単位は mL / L / 万 L / 億 L / 兆 L。 */
  function volume(mL, opts) {
    const minD = (opts && opts.minDecimals) || 0;
    let v, unit;
    if (mL < 1000) { v = mL; unit = 'mL'; }
    else {
      const L = mL / 1000;
      if (L < 1e4) { v = L; unit = 'L'; }
      else if (L < 1e8) { v = L / 1e4; unit = '万 L'; }
      else if (L < 1e12) { v = L / 1e8; unit = '億 L'; }
      else { v = L / 1e12; unit = '兆 L'; }
    }
    const value = fixed(v, decimals(v, minD));
    return { value, unit, text: value + ' ' + unit };
  }

  /** 個数。1 万以上は 万、1 億以上は 億。 */
  function count(n) {
    const a = Math.abs(n);
    if (a < 1e4) return fixed(n, Number.isInteger(n) ? 0 : decimals(n));
    const big = (v, u) => fixed(v, v < 100 && Math.abs(v - Math.round(v)) > 1e-9 ? 1 : 0) + u;
    if (a < 1e8) return big(n / 1e4, '万');
    if (a < 1e12) return big(n / 1e8, '億');
    return big(n / 1e12, '兆');
  }

  /** 「◯杯分」のような換算値。小さい値は小数を残す。 */
  function times(x) {
    if (x >= 100) return count(Math.round(x));
    if (Math.abs(x - Math.round(x)) < 1e-9) return fixed(x, 0);
    if (x >= 10) return fixed(x, 1);
    if (x >= 0.01) return fixed(x, 2);
    return fixed(x, 3);
  }

  function duration(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    const mm = String(m).padStart(2, '0'), ss = String(r).padStart(2, '0');
    return h > 0 ? h + ':' + mm + ':' + ss : mm + ':' + ss;
  }

  /** 1 回あたりの単価の表示（0.26 → "0.26 mL"、45 → "45 mL"） */
  function perPrompt(mL) {
    return (mL < 1 ? fixed(mL, 2) : mL < 10 ? fixed(mL, 1) : fixed(mL, 0)) + ' mL';
  }

  return { volume, count, times, duration, perPrompt, fixed };
})();
