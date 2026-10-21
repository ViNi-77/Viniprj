/* 液面。clipPath の中で波形 path を毎フレーム更新する。 */
window.AW = window.AW || {};

AW.Liquid = (function () {
  /** 水面の波形。levelY が液面、w×h が座標系。下端まで閉じる。 */
  function wavePath(levelY, t, amp, w, h, phase) {
    const step = Math.max(4, w / 40);
    let d = 'M0 ' + h + ' L0 ' + levelY.toFixed(2);
    for (let x = 0; x <= w + step; x += step) {
      const y = levelY + amp * Math.sin(x / (w * 0.11) + t * 2.2 + (phase || 0)) + amp * 0.45 * Math.sin(x / (w * 0.045) - t * 1.3 + (phase || 0));
      d += ' L' + x.toFixed(1) + ' ' + y.toFixed(2);
    }
    return d + ' L' + w + ' ' + h + ' Z';
  }

  /** 開いた線（閉じない）。水面のハイライト用。 */
  function surfacePath(levelY, t, amp, w, phase) {
    const step = Math.max(4, w / 40);
    let d = '';
    for (let x = 0; x <= w + step; x += step) {
      const y = levelY + amp * Math.sin(x / (w * 0.11) + t * 2.2 + (phase || 0)) + amp * 0.45 * Math.sin(x / (w * 0.045) - t * 1.3 + (phase || 0));
      d += (x === 0 ? 'M' : ' L') + x.toFixed(1) + ' ' + y.toFixed(2);
    }
    return d;
  }

  /**
   * 液面オブジェクト。
   * opts: { front, back, surface (path 要素), w, h, yTop, yBottom, amp }
   * set(frac) で目標、tick(now, dt, reduced) で追従、splash() で一時的に波を大きくする。
   */
  function make(opts) {
    const o = Object.assign({ amp: 3, lerp: 0.08 }, opts);
    const yOf = (f) => o.yBottom - Math.max(0, Math.min(1, f)) * (o.yBottom - o.yTop);
    let target = 0, cur = o.yBottom, boost = 0, t = 0;
    const hidden = o.h + o.amp * 4; // 完全に空のときは画面外に逃がす

    function tick(now, dt, reduced) {
      t += dt / 1000;
      const ty = yOf(target);
      if (reduced) cur = ty; else cur += (ty - cur) * o.lerp * (dt / 16);
      boost = Math.max(0, boost - dt / 600);
      const amp = reduced ? 0 : o.amp * (1 + boost * 2.5);
      const empty = target <= 0 && Math.abs(cur - o.yBottom) < 0.5;
      const y = empty ? hidden : cur;
      if (o.front) o.front.setAttribute('d', wavePath(y, t, amp, o.w, o.h, 0));
      if (o.back) o.back.setAttribute('d', wavePath(y - amp * 0.8, t * 0.9, amp * 1.2, o.w, o.h, 1.7));
      if (o.surface) o.surface.setAttribute('d', empty ? '' : surfacePath(y, t, amp, o.w, 0));
    }

    return {
      set(frac) { target = frac; },
      jump(frac) { target = frac; cur = yOf(frac); },
      splash(k) { boost = Math.max(boost, k || 1); },
      tick,
      get levelY() { return cur; },
      yOf,
    };
  }

  return { wavePath, surfacePath, make };
})();
