/* 補完機 — 静的な部品。docs/02 §4 の部品表に対応する。
   各ヘルパは描いた形を記録器 R にも記録し（監査用）、put で描画順の層に入れる。
   面の上の線や文字は、その面を持つ部品と同じ項目（after）に入れ、描画順が離れないようにする。 */
export function makeParts(C) {
  const { k, A, P, R, G } = C;
  const at = (p) => k.iso(p, P);
  const S = (paths, style) => k.solidSvg(paths, style);
  const L = (d, style) => k.lineSvg(d, style);
  const Dots = (points, style) => k.dotsSvg(points, style);
  const byDepth = (points) => [...points].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
  const text = (xy, z, str, opts = {}, along = "x") => k.faceTextSvg(k.topMatrix(xy, z + 0.01, P, along), str, { size: 4, tone: "lo", ...opts });

  function put(name, ref, svg, shapes = [], extra = {}) {
    return R.put({ name, at: ref, svg, shapes, piece: "cm", ...extra });
  }
  function slab(name, plan, z, h, style = {}, { steps = 4, bevel = 0, inner = "", after = "", meta = {}, bias = 0, wrap = null } = {}) {
    let svg = S(k.slabOf(plan, z, h, P, steps, bevel), { ...style, inner }) + after;
    if (wrap) svg = wrap(svg);
    const shape = R.solid(A.slab(plan, z, h, { name, ...meta }, steps));
    return put(name, [plan.x + plan.w / 2, plan.y + plan.d / 2, z + h], svg, [shape], { bias });
  }
  function cyl(name, cx, cy, r, z, h, style = {}, { steps = 24, bevel = 0, inner = "", after = "", meta = {}, bias = 0, wrap = null } = {}) {
    let svg = S(k.cylinder(cx, cy, r, z, h, P, steps, bevel), { ...style, inner }) + after;
    if (wrap) svg = wrap(svg);
    const shape = R.solid(A.cylinder(cx, cy, r, z, h, { name, ...meta }));
    return put(name, [cx, cy, z + h], svg, [shape], { bias });
  }
  const rules = (plan, z, fracs, tone = "faint") => fracs.map((f) => L(k.lineOnTop([plan.x + 2.2, plan.y + plan.d * f], [plan.x + plan.w - 2.2, plan.y + plan.d * f], z, P), { tone, free: true })).join("");

  const W = C.W;
  const T = W.SHEET_T;

  /* ---------- 台 ---------- */
  function base() {
    const plate = W.PLATE;
    const z0 = -W.PLATE_H - W.FOOT_H;
    C.back.push(`<path class="iso-halo" d="${k.haloOf(plate, z0, W.PLATE_H, P)}"/>`);
    for (const [x, y] of byDepth(k.corners(plate, 20))) {
      cyl("stand.foot", x, y, 6, z0, 1.8, { tone: "lo" }, { steps: 24, meta: { ground: true } });
      cyl("stand.foot-neck", x, y, 4.6, z0 + 1.8, W.FOOT_H - 1.8, { tone: "mid" }, { steps: 24 });
    }
    const screws = k.corners(plate, 9);
    const top = 0;
    const plateAfter =
      L(k.planOutline(k.insetPlan(plate, 5), top, P, 8), { tone: "lo" }) +
      L(screws.map(([x, y]) => k.ring(x, y, 2, top, P, 16)).join(""), { tone: "lo" }) +
      Dots(screws.map(([x, y]) => at([x, y, top])), { size: 0.5 });
    slab("base.plate", plate, -W.PLATE_H, W.PLATE_H, { tone: "mid" }, { steps: 8, bevel: 1.6, after: plateAfter });
    const label = { x: plate.x + 14, y: plate.y + plate.d - 26, w: 46, d: 14, r: 1 };
    const lz = top + 0.8;
    slab("base.label", label, top, 0.8, { tone: "lo", crease: "none" }, {
      steps: 3,
      after: rules(label, lz, [0.5, 0.72]) + text([label.x + 4, label.y + 2.2], lz, "補完機 CM-1", { tone: "mid" }) +
        Dots(k.corners(label, 2).map(([x, y]) => at([x, y, lz])), { size: 0.4 }),
    });
    const strip = { x: plate.x + 70, y: plate.y + plate.d - 12, w: 160, d: 6, r: 0.8 };
    const ticks = k.topTicks(strip.x + 4, strip.x + strip.w - 4, 4, 5, strip.y + 0.8, top + 0.6, [1.8, 3.4], P);
    slab("base.ruler", strip, top, 0.6, { tone: "lo", crease: "none" }, {
      steps: 3,
      after: L(ticks.minor, { tone: "lo" }) + L(ticks.major, { tone: "mid" }) + Dots([at([strip.x + 2, strip.y + 3, top + 0.6]), at([strip.x + strip.w - 2, strip.y + 3, top + 0.6])], { size: 0.4 }),
    });
  }

  /* ---------- 投入口と綴じ器 ---------- */
  function intake() {
    const Tr = W.TRAY;
    slab("intake.floor", Tr, 0, 3, { tone: "mid" }, { steps: 3, bevel: 0.5, after: text([Tr.x + 3, Tr.y - 7], 0, "手紙", { tone: "lo" }) });
    const wall = 2.2;
    slab("intake.wall-back", { x: Tr.x, y: Tr.y, w: Tr.w, d: wall, r: 0.6 }, 3, 9, { tone: "mid" }, { steps: 2, after: Dots([at([Tr.x + 3, Tr.y + 1.1, 12]), at([Tr.x + Tr.w - 3, Tr.y + 1.1, 12])], { size: 0.4 }) });
    slab("intake.wall-left", { x: Tr.x, y: Tr.y + wall, w: wall, d: Tr.d - wall * 2, r: 0.6 }, 3, 9, { tone: "mid" }, { steps: 2 });
    slab("intake.wall-right", { x: Tr.x + Tr.w - wall, y: Tr.y + wall, w: wall, d: Tr.d - wall * 2, r: 0.6 }, 3, 9, { tone: "mid" }, { steps: 2 });
    slab("intake.lip", { x: Tr.x, y: Tr.y + Tr.d - wall, w: Tr.w, d: wall, r: 0.6 }, 3, 3, { tone: "mid" }, { steps: 2 });
    // 綴じ器: 支柱（頭の下まで）・頭・キャップ・アーム（動く）
    const px = Tr.x + Tr.w / 2, py = Tr.y - 7;
    const headZ = W.BINDER_TOP - 6;
    cyl("binder.post", px, py, 3, 0, headZ, { tone: "mid", crease: "none" }, { steps: 20, after: [12, 24].map((zz) => L(k.sideArc(px, py, 3, zz, P, 12), { tone: "faint" })).join("") });
    const head = { x: px - 5, y: py - 3, w: 10, d: Tr.d + 12, r: 2 };
    slab("binder.head", head, headZ, 6, { tone: "mid" }, { steps: 3, bevel: 0.5, after: Dots([at([px - 3, py, W.BINDER_TOP]), at([px + 3, py, W.BINDER_TOP])], { size: 0.4 }) });
    cyl("binder.cap", px, py, 3.8, W.BINDER_TOP, 2, { tone: "mid" }, { steps: 20, after: L(k.knurl(px, py, 3.8, W.BINDER_TOP, W.BINDER_TOP + 2, 20, P), { tone: "lo" }) });
    const press = { x: Tr.x + 4, y: Tr.y + 4, w: Tr.w - 8, d: Tr.d - 8, r: 1.5 };
    const cy = Tr.y + Tr.d / 2;
    const armZ = headZ - W.ARM_LEN;
    const armSvg = S(k.cylinder(px, cy, 2.2, 0, W.ARM_LEN, P, 16), { tone: "mid", crease: "none" }) + S(k.slabOf(press, -1.2, 1.2, P, 3, 0.4), { tone: "mid" });
    put("binder.arm", [px, cy, armZ + 2], `<g data-part="arm" transform="${k.translateAlong(P, [0, 0, armZ])}">${armSvg}</g>`,
      [R.solid(A.cylinder(px, cy, 2.2, armZ, W.ARM_LEN, { name: "binder.arm" })), R.solid(A.slab(press, armZ - 1.2, 1.2, { name: "binder.press" }, 3))]);
    // 投入口の紙束（最大13枚。表示/非表示）
    const sheet = { x: Tr.x + 5, y: Tr.y + 5, w: Tr.w - 10, d: Tr.d - 10, r: 0.8 };
    for (let i = 0; i < W.STACK_MAX; i++) {
      slab("intake.sheet#" + i, sheet, 3 + i * T, T, { tone: "hi", crease: "none" }, { steps: 2, wrap: (s) => `<g data-part="stack" data-i="${i}" style="opacity:0">${s}</g>` });
    }
  }

  /* ---------- 机、紙、受け皿、ボールペン ---------- */
  function desk() {
    const Dk = W.DESK;
    for (const [x, y] of byDepth(k.corners(Dk, 6))) cyl("desk.leg", x, y, 2.6, 0, W.DESK_Z - 2, { tone: "mid", crease: "none" }, { steps: 16 });
    const top = W.DESK_Z;
    const rim = k.insetPlan(Dk, 2.5);
    const grid = [];
    for (let c = 1; c < W.COLS; c++) { const x = rim.x + (rim.w / W.COLS) * c; grid.push(L(k.lineOnTop([x, rim.y], [x, rim.y + rim.d], top, P), { tone: "lo" })); }
    for (let r = 1; r < W.ROWS; r++) { const y = rim.y + (rim.d / W.ROWS) * r; grid.push(L(k.lineOnTop([rim.x, y], [rim.x + rim.w, y], top, P), { tone: "lo" })); }
    slab("desk.top", Dk, top - 2, 2, { tone: "hi" }, {
      steps: 6, bevel: 0.8,
      after: L(k.planOutline(rim, top, P, 4), { tone: "mid" }) + grid.join("") + Dots(k.corners(Dk, 3).map(([x, y]) => at([x, y, top])), { size: 0.4 }) + text([Dk.x + 3, Dk.y - 6], 0, "机", { tone: "lo" }),
    });
    // 机の紙（20枠）。種類ごとに印が違う
    const cw = rim.w / W.COLS, ch = rim.d / W.ROWS;
    const slotPlan = (i) => { const c = i % W.COLS, r = Math.floor(i / W.COLS); return { x: rim.x + c * cw + 1.6, y: rim.y + r * ch + 1.6, w: cw - 3.2, d: ch - 3.2, r: 0.6 }; };
    W.SLOTS.forEach((slot, i) => {
      const plan = slotPlan(i);
      const tz = top + T;
      let after = "";
      if (slot === "intro") after = rules(plan, tz, [0.3, 0.52]) + L(k.lineOnTop([plan.x + 2.2, plan.y + plan.d * 0.78], [plan.x + plan.w * 0.62, plan.y + plan.d * 0.78], tz, P), { tone: "hi", free: true });
      else if (slot === "ask") after = rules(plan, tz, [0.5]);
      else if (slot === "material") after = rules(plan, tz, [0.3, 0.5, 0.7]);
      else if (slot === "sample") after = L(k.planOutline(k.insetPlan(plan, 1.8), tz, P, 2), { tone: "lo", dotted: true });
      else after = L(k.lineOnTop([plan.x + plan.w / 2, plan.y + 1.5], [plan.x + plan.w / 2, plan.y + plan.d - 1.5], tz, P), { tone: "lo", free: true });
      slab("desk.sheet#" + i, plan, top, T, { tone: slot === "history" ? "mid" : "hi", crease: "none" }, { steps: 2, after, wrap: (s) => `<g data-part="sheet" data-i="${i}" data-kind="${slot}" style="opacity:0">${s}</g>` });
    });
    // 落ちる途中の紙（21枚目。机の奥の角に重なって現れ、受け皿へ落ちる）
    const fp = slotPlan(W.SLOTS.length - 1);
    slab("desk.falling", fp, top + T, T, { tone: "mid", crease: "none" }, { steps: 2, wrap: (s) => `<g data-part="falling" style="opacity:0">${s}</g>` });
    // 受け皿（机の奥、+y 側）
    const B = W.BIN;
    slab("bin.floor", B, 0, 2, { tone: "mid" }, { steps: 3, after: text([B.x + 3, B.y + B.d + 2], 0, "落ちた紙", { tone: "lo" }) });
    slab("bin.back", { x: B.x, y: B.y + B.d - 2, w: B.w, d: 2, r: 0.5 }, 2, 7, { tone: "mid" }, { steps: 2 });
    slab("bin.left", { x: B.x, y: B.y, w: 2, d: B.d - 2, r: 0.5 }, 2, 7, { tone: "mid" }, { steps: 2 });
    slab("bin.right", { x: B.x + B.w - 2, y: B.y, w: 2, d: B.d - 2, r: 0.5 }, 2, 7, { tone: "mid" }, { steps: 2 });
    const fallen = { x: B.x + 4, y: B.y + 4, w: B.w - 8, d: B.d - 8, r: 0.8 };
    for (let i = 0; i < W.FALLEN_MAX; i++) {
      slab("bin.sheet#" + i, fallen, 2 + i * T, T, { tone: "hi", crease: "none" }, { steps: 2, wrap: (s) => `<g data-part="fallen" data-i="${i}" style="opacity:0">${s}</g>` });
    }
    // ボールペン（机の手前に横置き。2つの受けに載る）
    const pen = W.PEN;
    for (const dx of [6, pen.len - 4]) slab("pen.rest", { x: pen.x + dx, y: pen.y - 2.2, w: 3, d: 4.4, r: 0.6 }, 0, pen.z - 1.3, { tone: "lo" }, { steps: 2 });
    const pf = G.frameOf([pen.x, pen.y, pen.z], [1, 0, 0], [0, 1, 0], [0, 0, 1]);
    const penSvg =
      S(G.disc(0, pen.len, 1.3, pf, P, { steps: 16 }), { tone: "hi", crease: "none" }) +
      S(G.disc(pen.len, pen.len + 6, 1.45, pf, P, { steps: 16 }), { tone: "mid" }) +
      S(G.disc(-3, 0, 0.6, pf, P, { steps: 12 }), { tone: "lo" }) +
      L(k.segment([pen.x + pen.len + 0.6, pen.y - 1.0, pen.z + 1.0], [pen.x + pen.len + 5.5, pen.y - 1.0, pen.z + 1.0], P), { tone: "lo", free: "end" }) +
      text([pen.x + 2, pen.y + 3], 0, "ボールペン", { tone: "lo", size: 3.2 });
    put("pen.body", [pen.x + pen.len / 2, pen.y, pen.z + 1.45], penSvg, [R.solid(A.disc(pf, -3, pen.len + 6, 1.45, { name: "pen" }))]);
  }

  /* ---------- 読み取りヘッドの門形レール ---------- */
  function gantry() {
    const g = W.GANTRY;
    for (const x of [g.x0, g.x1]) {
      slab("gantry.foot", { x: x - 5, y: g.y - 5, w: 10, d: 10, r: 1.5 }, 0, 3, { tone: "mid" }, { steps: 3, bevel: 0.4, after: Dots([at([x - 3.2, g.y - 3.2, 3]), at([x + 3.2, g.y - 3.2, 3])], { size: 0.4 }) });
      cyl("gantry.post", x, g.y, 2.4, 3, g.z - 3, { tone: "mid", crease: "none" }, { steps: 16, after: [20, 40].map((zz) => L(k.sideArc(x, g.y, 2.4, zz, P, 10), { tone: "faint" })).join("") });
    }
    const beam = { x: g.x0 - 3, y: g.y - 3, w: g.x1 - g.x0 + 6, d: 6, r: 1 };
    const ticks = k.topTicks(g.x0 + 6, g.x1 - 6, 4, 5, g.y - 2.4, g.z + 4, [1.4, 2.6], P);
    slab("gantry.beam", beam, g.z, 4, { tone: "mid" }, { steps: 3, bevel: 0.5, after: L(ticks.minor, { tone: "lo" }) + L(ticks.major, { tone: "mid" }) + Dots([at([g.x0 + 2, g.y + 2, g.z + 4]), at([g.x1 - 2, g.y + 2, g.z + 4])], { size: 0.4 }) });
    for (const x of [g.x0 - 3, g.x1]) slab("gantry.stop", { x, y: g.y - 4, w: 3, d: 8, r: 0.8 }, g.z + 4, 3, { tone: "mid" }, { steps: 2 });
    // 台車（動く: x）。初期位置は左端
    const car = { x: -7, y: g.y - 6, w: 14, d: 12, r: 1.5 };
    const carZ = g.z + 4;
    const cx = g.x0 + 10;
    const lens = { x: -3, y: g.y + 6, w: 6, d: 8, r: 1 };
    const carSvg =
      S(k.slabOf(car, carZ, 5, P, 3, 0.5), { tone: "mid" }) +
      Dots([at([car.x + 2.5, car.y + 2.5, carZ + 5]), at([car.x + car.w - 2.5, car.y + 2.5, carZ + 5])], { size: 0.4 }) +
      S(k.slabOf(lens, carZ - 6, 11, P, 2), { tone: "mid", crease: "none" }) +
      S(k.cylinder(0, g.y + 10, 2.4, carZ - 9, 3, P, 16), { tone: "hi", lit: true }) +
      L(k.ring(0, g.y + 10, 1.2, carZ - 9, P, 12), { tone: "hi" });
    put("head.car", [cx, g.y, carZ + 5], `<g data-part="head" transform="${k.translateAlong(P, [cx, 0, 0])}">${carSvg}</g>`, [
      R.solid(A.slab({ ...car, x: car.x + cx }, carZ, 5, { name: "head.car" }, 3)),
      R.solid(A.slab({ ...lens, x: lens.x + cx }, carZ - 6, 11, { name: "head.lens-tube" }, 2)),
      R.solid(A.cylinder(cx, g.y + 10, 2.4, carZ - 9, 3, { name: "head.lens" })),
    ]);
  }

  /* ---------- 候補ダイヤルと印字テープ ---------- */
  function dialAndTape() {
    const d = W.DIAL;
    cyl("dial.base", d.x, d.y, d.r + 3, 0, 3, { tone: "mid" }, { steps: 40, bevel: 0.5, after: text([d.x - d.r - 2, d.y + d.r + 5], 0, "次の一語", { tone: "lo" }) });
    const top = 3 + d.h;
    const ticks = k.radialTicks(d.x, d.y, d.r - 2, 40, 5, top, [1, 2.2], P);
    const faces = [];
    for (let i = 0; i < 4; i++) {
      const ang = (i / 4) * Math.PI * 2;
      const px = d.x + Math.sin(ang) * (d.r - 7), py = d.y - Math.cos(ang) * (d.r - 7);
      faces.push(`<g data-face="${i}">${k.faceTextSvg(k.topMatrix([px - 6.5, py - 1.6], top + 0.01, P, "x"), "　", { size: 3.4, tone: "mid" })}</g>`);
    }
    cyl("dial.drum", d.x, d.y, d.r, 3, d.h, { tone: "hi", crease: "lo" }, {
      steps: 48, bevel: 0.6,
      after:
        L(k.knurl(d.x, d.y, d.r, top - 3, top, 56, P, 0.3), { tone: "lo" }) + L(k.sideArc(d.x, d.y, d.r, top - 3, P, 30), { tone: "faint" }) +
        L(ticks.minor, { tone: "lo" }) + L(ticks.major, { tone: "mid" }) + L(k.ring(d.x, d.y, d.r - 2, top, P, 48), { tone: "lo" }) +
        `<g data-part="dial-faces">${faces.join("")}</g>` +
        L(k.lineOnTop([d.x, d.y - d.r - 4], [d.x, d.y - d.r + 1.5], top + 0.02, P), { tone: "hi" }) + Dots([at([d.x, d.y - d.r - 4, top + 0.02])], { size: 0.5, tone: "hi" }),
    });
    cyl("dial.hub", d.x, d.y, 3, top, 2.5, { tone: "mid" }, { steps: 20, after: L(k.knurl(d.x, d.y, 3, top, top + 2.5, 18, P), { tone: "lo" }) });
    // 印字テープ
    const t = W.TAPE;
    slab("tape.base", t.base, 0, t.z, { tone: "mid" }, { steps: 3, bevel: 0.5, after: text([t.base.x + 2.5, t.base.y + t.base.d - 1.5], t.z, "答え", { tone: "lo" }) });
    slab("tape.slot", { x: t.base.x + 2, y: t.base.y + 2, w: t.base.w - 4, d: 3, r: 0.5 }, t.z, 1.2, { tone: "lo", crease: "none" }, { steps: 2 });
    for (const dy of [t.base.d - 3, t.base.d - 8]) cyl("tape.roller", t.base.x + t.base.w - 4, t.base.y + dy, 2, t.z, 2.2, { tone: "mid" }, { steps: 16, after: L(k.knurl(t.base.x + t.base.w - 4, t.base.y + dy, 2, t.z, t.z + 2.2, 12, P), { tone: "lo" }) });
    const words = [];
    for (let i = 0; i < W.WORDS; i++) {
      const y = t.strip.y + 3 + i * t.pitch;
      words.push(`<g data-word="${i}" style="opacity:0">${k.faceTextSvg(k.topMatrix([t.strip.x + 2.2, y], t.z + 0.52, P, "y"), "　", { size: 4.6, tone: "hi" })}</g>`);
    }
    slab("tape.strip", t.strip, t.z, 0.5, { tone: "hi", crease: "none" }, { steps: 2, after: L(k.planOutline(k.insetPlan(t.strip, 1), t.z + 0.5, P, 2), { tone: "faint" }) + `<g data-part="words">${words.join("")}</g>` });
  }

  /* ---------- 注意力メーター、条件ピン、片付けレバー ---------- */
  function meterAndLever() {
    const m = W.METER;
    const top = m.h;
    const span = Math.PI * 1.5;
    const ticks = k.radialTicks(m.x, m.y, m.r - 1.5, 10, 5, top, [1.2, 2.4], P, -span / 2, span);
    const needle = k.lineOnTop([m.x, m.y], [m.x - Math.sin(span / 2) * (m.r - 5), m.y + Math.cos(span / 2) * (m.r - 5)], top + 0.03, P);
    cyl("meter.body", m.x, m.y, m.r, 0, m.h, { tone: "mid" }, {
      steps: 40, bevel: 0.5,
      after: L(k.ring(m.x, m.y, m.r - 1.5, top, P, 40), { tone: "lo" }) + L(ticks.minor, { tone: "lo" }) + L(ticks.major, { tone: "mid" }) +
        text([m.x - 6, m.y + 4.5], top, "注意力", { tone: "lo", size: 3 }) +
        `<path data-part="needle" class="iso-line" data-tone="hi" data-free="end" d="${needle}" style="stroke-width:0.9"/>`,
    });
    cyl("meter.hub", m.x, m.y, 1.6, top, 1.2, { tone: "hi" }, { steps: 14 });
    const pins = W.PINS;
    slab("pins.block", pins.block, 0, 4, { tone: "mid" }, { steps: 3, bevel: 0.4, after: text([pins.block.x + 1.5, pins.block.y + pins.block.d - 1.8], 4, "条件", { tone: "lo", size: 3 }) });
    for (let i = 0; i < pins.count; i++) {
      const x = pins.block.x + 4 + i * pins.pitch, y = pins.block.y + 3.5;
      // 下がった姿（キャップだけ）と上がった姿（軸＋キャップ）を重ね、live が不透明度で切り替える
      const down = S(k.cylinder(x, y, 1.4, 4, 1, P, 12), { tone: "lo" });
      const up = S(k.cylinder(x, y, 1, 4, pins.up, P, 12), { tone: "hi", crease: "none" }) + S(k.cylinder(x, y, 1.4, 4 + pins.up, 1, P, 12), { tone: "hi" });
      put("pins.pin#" + i, [x, y, 5], `<g data-part="pin" data-i="${i}"><g data-pin-down>${down}</g><g data-pin-up style="opacity:0">${up}</g></g>`,
        [R.solid(A.cylinder(x, y, 1, 4, pins.up, { name: "pins.pin#" + i })), R.solid(A.cylinder(x, y, 1.4, 4 + pins.up, 1, { name: "pins.cap#" + i }))]);
    }
    const lv = W.LEVER;
    slab("lever.bracket", { x: lv.x - 4, y: lv.y - 3, w: 8, d: 6, r: 1 }, 0, lv.z, { tone: "mid" }, { steps: 3, bevel: 0.4, after: text([lv.x - 7, lv.y + 6], 0, "片付け", { tone: "lo" }) });
    const pf = G.frameOf([lv.x - 4.5, lv.y, lv.z + 1.2], [1, 0, 0], [0, 1, 0], [0, 0, 1]);
    put("lever.pivot", [lv.x, lv.y, lv.z + 1.2], S(G.disc(0, 9, 1.2, pf, P, { steps: 12 }), { tone: "lo", crease: "none" }), [R.solid(A.disc(pf, 0, 9, 1.2, { name: "lever.pivot" }))]);
    const h0 = lv.z + 2.4;
    const handle = S(k.cylinder(0, 0, 1.1, 0, lv.len, P, 12), { tone: "mid", crease: "none" }) + S(k.cylinder(0, 0, 2.4, lv.len, 3, P, 16), { tone: "hi" }) + L(k.knurl(0, 0, 2.4, lv.len, lv.len + 3, 14, P), { tone: "lo" });
    put("lever.handle", [lv.x, lv.y, h0 + lv.len], `<g data-part="lever" transform="${k.translateAlong(P, [lv.x, lv.y, h0])}">${handle}</g>`,
      [R.solid(A.cylinder(lv.x, lv.y, 1.1, h0, lv.len, { name: "lever.handle" })), R.solid(A.cylinder(lv.x, lv.y, 2.4, h0 + lv.len, 3, { name: "lever.knob" }))]);
  }

  return { base, intake, desk, gantry, dialAndTape, meterAndLever };
}
