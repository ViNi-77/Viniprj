/* 幕 2: 「送信した」を押すたびにボトルへ一滴。 */
window.AW = window.AW || {};

AW.session = (function () {
  const D = AW.DATA, B = D.bottle;
  let els, liquid, dropAnim = null, lastBottles = 0, lastKey = '';

  function q(id) { return document.getElementById(id); }

  function init() {
    els = {
      btn: q('send-btn'), reset: q('reset-btn'), auto: q('auto-chk'), every: q('auto-every'),
      count: q('session-count'), total: q('session-total'), totalUnit: q('session-total-unit'), elapsed: q('session-elapsed'),
      remain: q('session-remain'), bottles: q('session-bottles'), equiv: q('session-equiv'), per: q('session-per'),
      front: q('bottle-wave'), back: q('bottle-wave-back'), surface: q('bottle-surface'), drop: q('bottle-drop'), bubble: q('bottle-bubble'),
    };
    liquid = AW.Liquid.make({ front: els.front, back: els.back, surface: els.surface, w: 200, h: 520, yTop: B.yTop, yBottom: B.yBottom, amp: 3, lerp: 0.1 });
    liquid.jump(0);

    els.btn.addEventListener('click', send);
    els.reset.addEventListener('click', reset);
    els.auto.addEventListener('change', () => {
      const s = AW.state.session; s.auto = els.auto.checked; s.lastAutoAt = Date.now(); AW.setState({ session: s });
    });
    els.every.addEventListener('change', () => {
      const s = AW.state.session; s.autoEverySec = Number(els.every.value) || 30; s.lastAutoAt = Date.now(); AW.setState({ session: s });
    });
    document.addEventListener('keydown', (e) => {
      if (e.code !== 'Space' && e.key !== 'Enter') return;
      const t = e.target;
      const tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || tag === 'BUTTON' || tag === 'A') return;
      e.preventDefault(); send();
    });
  }

  function add(n) {
    const s = AW.state.session;
    if (!s.startedAt) s.startedAt = Date.now();
    s.count += n;
    AW.setState({ session: s });
  }

  function send() {
    add(1);
    dropAnim = { t0: performance.now(), dur: 420 };
    els.drop.setAttribute('opacity', '1');
    els.btn.classList.add('is-pressed');
    setTimeout(() => els.btn.classList.remove('is-pressed'), 120);
    if (els.bubble) { els.bubble.setAttribute('opacity', '1'); els.bubble.setAttribute('r', '2'); els.bubble.dataset.t = String(performance.now()); }
  }

  function reset() {
    AW.setState({ session: { count: 0, startedAt: null, auto: false, autoEverySec: AW.state.session.autoEverySec, lastAutoAt: 0 } });
    els.auto.checked = false; lastBottles = 0; liquid.jump(0); liquid.splash(0.5);
  }

  /** いちばん伝わる換算を 1 つ選ぶ。 */
  function equivalent(mL) {
    const cs = D.comparisons.filter((c) => c.id !== 'dome' && c.id !== 'pool');
    let pick = cs[0];
    for (const c of cs) if (mL / c.mL >= 1) pick = c;
    const x = mL / pick.mL;
    return pick.name + ' <b>' + AW.fmt.times(x) + '</b> ' + pick.unit + '分' + (pick.verified ? '' : '（目安）');
  }

  function tickDrop(now, dt) {
    if (!dropAnim) return;
    const p = Math.min(1, (performance.now() - dropAnim.t0) / dropAnim.dur);
    const toY = liquid.levelY - 2;
    const y = 10 + (toY - 10) * p * p;
    els.drop.setAttribute('cy', y.toFixed(1));
    if (p >= 1) { dropAnim = null; els.drop.setAttribute('opacity', '0'); els.drop.setAttribute('cy', '-10'); liquid.splash(1); }
    if (els.bubble && els.bubble.dataset.t) {
      const bp = Math.min(1, (performance.now() - Number(els.bubble.dataset.t)) / 500);
      els.bubble.setAttribute('r', (2 + bp * 16).toFixed(1)); els.bubble.setAttribute('opacity', (1 - bp).toFixed(2));
      if (bp >= 1) delete els.bubble.dataset.t;
    }
  }

  function render(state, now, dt) {
    const s = state.session, u = AW.scenario().mlPerPrompt;
    // 自動加算: 非表示中は進まず、復帰時に経過分をまとめて足す
    if (s.auto) {
      const every = s.autoEverySec * 1000;
      if (!s.lastAutoAt) s.lastAutoAt = now;
      const n = Math.floor((now - s.lastAutoAt) / every);
      if (n > 0) { s.lastAutoAt += n * every; add(n); if (n === 1) { dropAnim = { t0: performance.now(), dur: 420 }; els.drop.setAttribute('opacity', '1'); } }
    }
    const mL = s.count * u;
    const bottles = Math.floor(mL / B.capacityML);
    const frac = (mL - bottles * B.capacityML) / B.capacityML;
    if (bottles !== lastBottles) { if (bottles > lastBottles) { liquid.jump(0); liquid.splash(1.5); } lastBottles = bottles; }
    liquid.set(frac);
    liquid.tick(now, dt, state.reduced);
    tickDrop(now, dt);

    const key = s.count + ':' + u + ':' + (s.startedAt ? Math.floor((now - s.startedAt) / 1000) : 0);
    if (key === lastKey) return;
    lastKey = key;
    els.count.textContent = AW.fmt.count(s.count); els.count.dataset.value = String(s.count);
    const v = AW.fmt.volume(mL); els.total.textContent = v.value; els.totalUnit.textContent = v.unit; els.total.dataset.value = String(mL);
    els.elapsed.textContent = s.startedAt ? AW.fmt.duration(now - s.startedAt) : '--:--';
    const remain = Math.max(1, Math.ceil((B.capacityML - (mL - bottles * B.capacityML)) / u));
    els.remain.textContent = AW.fmt.count(remain);
    els.bottles.textContent = bottles > 0 ? AW.fmt.count(bottles) + ' 本' : '0 本';
    els.equiv.innerHTML = s.count === 0 ? '押すと、ここに換算が出ます。' : '= ' + equivalent(mL);
    els.per.textContent = AW.fmt.perPrompt(u);
  }

  return { init, render, send };
})();
