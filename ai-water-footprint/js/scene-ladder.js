/* 幕 3: 回数 × 人数 × 日数 を器の梯子で見せる。viewBox を補間してカメラが引く。 */
window.AW = window.AW || {};

AW.ladder = (function () {
  const D = AW.DATA, NS = 'http://www.w3.org/2000/svg';
  let els, vb = null, vbTarget = null, lastVb = '', lastKey = '', partialRect = null, partialIdx = -1, copies = [];

  function q(id) { return document.getElementById(id); }

  /** 人数スライダー: 0..100 → 1..10,000（log） */
  function peopleFrom(v) { return Math.max(1, Math.round(Math.pow(10, v / 25))); }
  function peopleTo(p) { return Math.round(Math.log10(Math.max(1, p)) * 25); }

  function init() {
    els = {
      perDay: q('sl-perday'), people: q('sl-people'), days: q('sl-days'),
      oPerDay: q('o-perday'), oPeople: q('o-people'), oDays: q('o-days'),
      total: q('ladder-total'), totalUnit: q('ladder-total-unit'), eq: q('ladder-eq'), daily: q('ladder-daily'),
      svg: q('stage'), g: q('stage-g'), ref: q('stage-ref'), label: q('stage-label'), refLabel: q('stage-ref-label'), more: q('stage-more'),
    };
    const l = AW.state.ladder;
    els.perDay.value = l.perDay; els.people.value = peopleTo(l.people); els.days.value = l.days;
    const onInput = () => {
      AW.setState({ ladder: { perDay: Number(els.perDay.value), people: peopleFrom(Number(els.people.value)), days: Number(els.days.value) } });
    };
    [els.perDay, els.people, els.days].forEach((s) => s.addEventListener('input', onInput));
    // 単位正方形の clipPath を器ごとに用意
    const defs = els.svg.querySelector('defs');
    for (const id in D.shapes) {
      const cp = document.createElementNS(NS, 'clipPath');
      cp.setAttribute('id', 'clip-' + id); cp.setAttribute('clipPathUnits', 'userSpaceOnUse');
      const p = document.createElementNS(NS, 'path'); p.setAttribute('d', D.shapes[id]);
      cp.appendChild(p); defs.appendChild(cp);
    }
    window.addEventListener('resize', () => { lastKey = ''; });
  }

  function totalML(state) {
    const l = state.ladder; return l.perDay * l.people * l.days * AW.scenario().mlPerPrompt;
  }

  function chooseStage(mL) {
    for (let i = 0; i < D.vessels.length; i++) {
      const v = D.vessels[i];
      if (Math.ceil(mL / v.mL) <= v.maxCopies) return i;
    }
    return D.vessels.length - 1;
  }

  function vesselGroup(v, x, f, cls) {
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('transform', 'translate(' + x + ' ' + (-v.h) + ') scale(' + v.w + ' ' + v.h + ')');
    if (cls) g.setAttribute('class', cls);
    const outline = document.createElementNS(NS, 'path');
    outline.setAttribute('d', D.shapes[v.id]); outline.setAttribute('class', 'vessel-outline');
    let rect = null;
    if (f > 0) {
      rect = document.createElementNS(NS, 'rect');
      rect.setAttribute('class', 'vessel-fill'); rect.setAttribute('clip-path', 'url(#clip-' + v.id + ')');
      rect.setAttribute('x', '0'); rect.setAttribute('width', '1');
      setFill(rect, f);
      g.appendChild(rect);
    }
    g.appendChild(outline);
    return { g, rect };
  }
  function setFill(rect, f) {
    const ff = Math.max(0, Math.min(1, f));
    rect.setAttribute('y', (1 - ff).toFixed(4)); rect.setAttribute('height', ff.toFixed(4));
  }

  function build(state, mL) {
    const idx = chooseStage(mL), v = D.vessels[idx];
    const n = mL / v.mL, full = Math.floor(n), partial = n - full;
    const shown = Math.max(1, Math.min(Math.ceil(n), v.maxCopies));
    const gapX = v.w * 0.22, gapY = v.h * 0.3;
    // 舞台の縦横比に合うように列数を決める（細長いプールは縦に積む、ボトルは横に並べる）
    const A = Math.max(0.2, els.svg.clientWidth / Math.max(1, els.svg.clientHeight));
    const cols = Math.max(1, Math.min(shown, Math.round(Math.sqrt(shown * A * (v.h + gapY) / (v.w + gapX))) || 1));
    const rows = Math.ceil(shown / cols);
    const key = v.id + ':' + shown + ':' + full;
    if (key !== lastKey) {
      lastKey = key;
      els.g.textContent = ''; els.ref.textContent = ''; copies = []; partialRect = null; partialIdx = -1;
      for (let i = 0; i < shown; i++) {
        const c = i % cols, r = Math.floor(i / cols);
        const f = i < full ? 1 : i === full ? Math.max(partial, 0.0001) : 0;
        const x = c * (v.w + gapX), yShift = -(rows - 1 - r) * (v.h + gapY);
        const { g, rect } = vesselGroup(v, x, f);
        g.setAttribute('transform', 'translate(0 ' + yShift + ') ' + g.getAttribute('transform'));
        els.g.appendChild(g); copies.push(g);
        if (i === full && rect) { partialRect = rect; partialIdx = i; }
      }
      // ひとつ前の器を左に置いて、縮尺の実感を作る
      const refV = idx > 0 ? D.vessels[idx - 1] : null;
      let refX = 0;
      if (refV) {
        refX = -(refV.w + v.w * 0.35);
        const { g } = vesselGroup(refV, refX, 1, 'vessel-ref');
        els.ref.appendChild(g);
        els.refLabel.textContent = '左端の小さいものが、ひとつ前の器（' + refV.name + '）。';
      } else {
        els.refLabel.textContent = '';
      }
      // 地面の線
      const ground = document.createElementNS(NS, 'line');
      ground.setAttribute('class', 'ground');
      const x0 = Math.min(refX, 0) - v.w * 0.6, x1 = cols * (v.w + gapX) + v.w * 0.4;
      ground.setAttribute('x1', x0); ground.setAttribute('x2', x1); ground.setAttribute('y1', 0); ground.setAttribute('y2', 0);
      els.ref.appendChild(ground);
      // viewBox の目標（下端を基準に、svg の縦横比に合わせる）
      const contentW = x1 - x0, contentH = rows * (v.h + gapY) + v.h * 0.15;
      const pad = contentW * 0.04;
      let bw = contentW + pad * 2, bh = contentH + pad * 2, bx = x0 - pad, by = -contentH - pad;
      if (bw / bh < A) { const nw = bh * A; bx -= (nw - bw) / 2; bw = nw; }
      else { const nh = bw / A; by -= (nh - bh); bh = nh; }
      vbTarget = { x: bx, y: by, w: bw, h: bh };
      if (!vb || state.reduced) vb = Object.assign({}, vbTarget);
    } else if (partialRect) {
      setFill(partialRect, Math.max(partial, 0.0001));
    }
    // 文字（HTML 側）
    const unitLabel = AW.fmt.volume(v.mL);
    const rest = n - full;
    els.label.innerHTML = '描いているのは <b>' + v.name + '</b>（1 ' + v.unit + ' = ' + unitLabel.text + '）。'
      + (full > 0 ? '満タン <b>' + AW.fmt.count(full) + '</b> ' + v.unit : '')
      + (rest > 0.005 ? (full > 0 ? ' と、' : '') + '<b>' + AW.fmt.times(rest) + '</b> ' + v.unit + '分' : '') + '。';
    const hiddenCount = Math.ceil(n) - shown;
    els.more.textContent = hiddenCount > 0 ? '…ほか ' + AW.fmt.count(hiddenCount) + ' ' + v.unit + '（描き切れません）' : '';
    return { v, n };
  }

  let lastTotalKey = '';
  function render(state, now, dt) {
    const mL = totalML(state);
    const l = state.ladder, u = AW.scenario().mlPerPrompt;
    const tk = mL + ':' + l.perDay + ':' + l.people + ':' + l.days;
    if (tk !== lastTotalKey) {
      lastTotalKey = tk;
      els.oPerDay.textContent = AW.fmt.count(l.perDay) + ' 回';
      els.oPeople.textContent = AW.fmt.count(l.people) + ' 人';
      els.oDays.textContent = AW.fmt.count(l.days) + ' 日';
      const v = AW.fmt.volume(mL); els.total.textContent = v.value; els.totalUnit.textContent = v.unit; els.total.dataset.value = String(mL);
      const { v: ves, n } = build(state, mL);
      els.eq.innerHTML = ves.name + ' <b>' + AW.fmt.times(n) + '</b> ' + ves.unit + '分';
      const dailyML = l.perDay * u;
      const dv = AW.fmt.volume(dailyML);
      els.daily.textContent = '1 人 1 日 ' + AW.fmt.count(l.perDay) + ' 回なら ' + dv.text + '（1 回 ' + AW.fmt.perPrompt(u) + '）。';
    }
    // カメラ
    if (vb && vbTarget) {
      const k = state.reduced ? 1 : Math.min(1, 0.1 * (dt / 16));
      let moved = false;
      for (const key of ['x', 'y', 'w', 'h']) {
        const d = vbTarget[key] - vb[key];
        if (Math.abs(d) > Math.abs(vbTarget[key]) * 1e-4 + 1e-6) { vb[key] += d * k; moved = true; } else vb[key] = vbTarget[key];
      }
      const str = vb.x.toFixed(3) + ' ' + vb.y.toFixed(3) + ' ' + vb.w.toFixed(3) + ' ' + vb.h.toFixed(3);
      if (moved || str !== lastVb) { els.svg.setAttribute('viewBox', str); lastVb = str; }
    }
  }

  return { init, render, peopleFrom, peopleTo };
})();
