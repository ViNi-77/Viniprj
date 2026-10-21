/* 幕 1: 開いた瞬間から増え続ける世界累計と、画面下端の水面。 */
window.AW = window.AW || {};

AW.hero = (function () {
  const D = AW.DATA;
  let els, liquid, W = 0, H = 0, waterH = 0;
  const drops = [], rings = [];
  const MAX_DROPS = 24, MAX_RINGS = 12;
  let lastText = '', lastUnit = '', lastRate = '', lastElapsed = '';

  function q(id) { return document.getElementById(id); }

  function init() {
    els = {
      act: q('act-hero'), value: q('hero-value'), unit: q('hero-unit'), rate: q('hero-rate'), per: q('hero-per'),
      src: q('hero-src'), elapsed: q('hero-elapsed'), water: q('hero-water'), drops: q('hero-drops'),
      front: q('hero-wave'), back: q('hero-wave-back'),
    };
    liquid = AW.Liquid.make({ front: els.front, back: els.back, w: 1000, h: 400, yTop: 0, yBottom: 400, amp: 9, lerp: 0.05 });
    liquid.jump(0);
    resize();
    window.addEventListener('resize', resize);
  }

  function resize() {
    W = els.act.clientWidth; H = els.act.clientHeight; waterH = els.water.clientHeight;
    els.drops.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  }

  /** 累計 L → 水面の高さ 0..1（log）。線形だと高シナリオで数秒で画面が埋まる。 */
  function frac(L) {
    return Math.min(1, Math.log10(1 + Math.max(0, L)) / Math.log10(1 + D.heroMaxLiters)) * 0.96;
  }

  function surfaceY() { return H - waterH + (liquid.levelY / 400) * waterH; }

  function spawnDrop() {
    let c;
    if (drops.length < MAX_DROPS) {
      c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      els.drops.appendChild(c);
      drops.push({ el: c, free: true });
    }
    const d = drops.find((x) => x.free);
    if (!d) return;
    d.free = false; d.x = 20 + Math.random() * (W - 40); d.y = -10; d.vy = 60 + Math.random() * 120; d.r = 1.6 + Math.random() * 2.2;
    d.el.setAttribute('r', d.r.toFixed(1)); d.el.style.display = '';
  }

  function spawnRing(x, y) {
    let r;
    if (rings.length < MAX_RINGS) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      el.setAttribute('class', 'ring'); els.drops.appendChild(el);
      rings.push({ el, free: true });
    }
    r = rings.find((x) => x.free);
    if (!r) return;
    r.free = false; r.x = x; r.y = y; r.t = 0; r.el.style.display = '';
  }

  function tickParticles(now, dt, rateLps) {
    const sy = surfaceY();
    const perSec = Math.max(1, Math.min(18, 1.5 + Math.log10(Math.max(1, rateLps)) * 3.5));
    if (Math.random() < perSec * dt / 1000) spawnDrop();
    for (const d of drops) {
      if (d.free) continue;
      d.vy += 1500 * dt / 1000; d.y += d.vy * dt / 1000;
      if (d.y >= sy) { d.free = true; d.el.style.display = 'none'; spawnRing(d.x, sy); liquid.splash(0.15); continue; }
      d.el.setAttribute('cx', d.x.toFixed(1)); d.el.setAttribute('cy', d.y.toFixed(1));
    }
    for (const r of rings) {
      if (r.free) continue;
      r.t += dt / 550;
      if (r.t >= 1) { r.free = true; r.el.style.display = 'none'; continue; }
      r.el.setAttribute('cx', r.x.toFixed(1)); r.el.setAttribute('cy', r.y.toFixed(1));
      r.el.setAttribute('r', (3 + r.t * 12).toFixed(1));
      r.el.setAttribute('opacity', ((1 - r.t) * 0.7).toFixed(2));
    }
  }

  function render(state, now, dt) {
    const L = AW.worldLiters(now);
    const sc = AW.scenario();
    const v = AW.fmt.volume(L * 1000, { minDecimals: 1 });
    if (v.value !== lastText) { els.value.textContent = v.value; els.value.dataset.value = String(L); lastText = v.value; }
    if (v.unit !== lastUnit) { els.unit.textContent = v.unit; lastUnit = v.unit; }
    const rate = AW.worldRateLps();
    const rateText = AW.fmt.volume(rate * 1000).text;
    if (rateText !== lastRate) {
      els.rate.textContent = rateText; lastRate = rateText;
      els.per.textContent = AW.fmt.perPrompt(sc.mlPerPrompt) + ' / ' + sc.unit;
      els.src.textContent = sc.source.short; els.src.href = sc.source.url;
    }
    const el = AW.fmt.duration(now - state.t0);
    if (el !== lastElapsed) { els.elapsed.textContent = el; lastElapsed = el; }

    liquid.set(frac(L));
    liquid.tick(now, dt, state.reduced);
    if (!state.reduced) tickParticles(now, dt, rate);
  }

  return { init, render };
})();
