/* 補完機 — 実行時。時計は1つ、補間は閉形式、数値はすべて CM.model から。
   ?render ではrAFを起動せず window.seek(t) で任意の時刻を描く（動画用）。 */
const CMD = __DATA__;
const { P, W } = CMD;
const DATA = CM.DATA;
const M = CM.model;
const render = new URLSearchParams(location.search).has("render");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const calm = () => still.matches && !render;

/* ---------- DOM ---------- */
const app = document.getElementById("cm-app");
const stage = app.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const q = (sel) => svg.querySelector(sel);
const qa = (sel) => [...svg.querySelectorAll(sel)];
const el = {
  stack: qa('[data-part="stack"]'), arm: q('[data-part="arm"]'), sheets: qa('[data-part="sheet"]'), falling: q('[data-part="falling"]'), fallen: qa('[data-part="fallen"]'),
  head: q('[data-part="head"]'), faces: qa('[data-part="dial-faces"] [data-face]'), dialGroup: q('[data-part="dial-faces"]'), words: qa('[data-part="words"] [data-word]'),
  needle: q('[data-part="needle"]'), pins: qa('[data-part="pin"]'), lever: q('[data-part="lever"]'),
  readout: app.querySelector("[data-readout]"), status: app.querySelector("[data-status]"), hint: app.querySelector("[data-hint]"), sound: app.querySelector("[data-sound]"),
  buttons: [...app.querySelectorAll(".cm-step")], modes: [...app.querySelectorAll(".cm-mode button")], restart: app.querySelector(".cm-restart"), cursor: app.querySelector("[data-cursor]"),
};

/* ---------- 時間 ---------- */
const DUR = { 1: 2.2, 2: 2.4, 3: 3.0, 4: 3.0, 5: 5.2, 6: 6.5, 7: 3.0, 8: 3.0 };          // 各工程の動きの長さ（秒）
const SLOT = { 1: 4, 2: 4, 3: 4, 4: 5, 5: 7, 6: 9, 7: 5, 8: 4 };                          // 自動のときの工程の間隔
const INTRO = 1.5, OUTRO = 2.5;
const SCHEDULE = {};
{ let t = INTRO; for (let n = 1; n <= 8; n++) { SCHEDULE[n] = t; t += SLOT[n]; } SCHEDULE.end = t + OUTRO; }
const clock = { t: 0, now: () => clock.t };
const ease = (u) => { u = Math.min(1, Math.max(0, u)); return 1 - Math.pow(1 - u, 3); };
const easeIO = (u) => { u = Math.min(1, Math.max(0, u)); return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; };
const clamp01 = (u) => Math.min(1, Math.max(0, u));
const lerp = (a, b, u) => a + (b - a) * u;

/* ---------- 状態 ---------- */
let mode = "manual";
let trig = Array(9).fill(null);   // 工程 n が始まった時刻
let autoStart = null;
let raf = 0, origin = 0, visible = true, lastDrawn = "";
try { if (localStorage.getItem("cm-mode") === "auto" && !calm()) mode = "auto"; } catch (e) { /* 使えなくてもよい */ }
if (render) mode = "auto";

const states = Array.from({ length: 9 }, (_, n) => M.stateAfter(n));

/* 時刻 t での工程と進み具合 */
function phaseAt(t) {
  let n = 0;
  for (let i = 1; i <= 8; i++) if (trig[i] !== null && trig[i] <= t) n = i;
  if (n === 0) return { n: 0, p: 1, before: states[0], after: states[0] };
  const p = calm() ? 1 : ease((t - trig[n]) / DUR[n]);
  return { n, p, before: states[n - 1], after: states[n] };
}

/* ---------- 描画 ---------- */
const setOpacity = (node, v) => { const s = v <= 0 ? "0" : v >= 1 ? "1" : v.toFixed(2); if (node.style.opacity !== s) node.style.opacity = s; };
const setTransform = (node, value) => { if (node.getAttribute("transform") !== value) node.setAttribute("transform", value); };

/* 紙の枚数（投入口の束） */
function stackCount(ph) {
  const { n, p } = ph;
  const d = DATA.letter;
  const letter = d.ask + d.material + d.sample;           // 7
  const bundle = DATA.priorRounds * DATA.roundSheets;     // 6
  if (n === 0 || n >= 4) return 0;
  if (n === 1) return Math.round(lerp(0, letter, p));
  if (n === 2) return Math.round(lerp(letter, letter + bundle, p));
  return Math.round(lerp(letter + bundle, 0, p));       // 3: 机へ
}
/* 机の枠 i に紙があるか（0..1） */
function sheetAlpha(ph, i) {
  const kind = W.SLOTS[i];
  if (kind === "intro") return 1;
  const { n, p, before, after } = ph;
  const countOf = (s, kk) => s.letter[kk] || 0;
  // 枠 i は、その種類の何枚目か
  const rank = W.SLOTS.slice(0, i).filter((x) => x === kind).length;
  const b = countOf(before, kind), a = countOf(after, kind);
  if (n === 3) { // 投入口から順に並ぶ（全体の順番で）
    const total = M.onDesk(after) - 2;
    const globalRank = W.SLOTS.slice(0, i).filter((x) => x !== "intro" && countOf(after, x) > W.SLOTS.slice(0, W.SLOTS.indexOf(x)).filter((y) => y === x).length).length;
    return rank < a ? clamp01(p * total - globalRank + 0.5) : 0;
  }
  if (n === 6 && kind === "history") return rank < b ? 1 : rank < a ? clamp01(p * 2.2 * (a - b) - (rank - b) + 0.5) : 0;
  if (n === 8) return rank < b ? 1 - p : 0;
  return rank < a ? 1 : 0;
}

function draw() {
  const t = clock.now();
  const ph = phaseAt(t);
  const { n, p, before, after } = ph;
  // 投入口の束と綴じ器のアーム
  const sc = stackCount(ph);
  el.stack.forEach((node, i) => setOpacity(node, i < sc ? 1 : 0));
  const armZ = W.BINDER_TOP - 6 - W.ARM_LEN;
  const dip = n === 2 ? Math.sin(Math.PI * p) * 7 : 0;
  setTransform(el.arm, translateAlong(P, [0, 0, armZ - dip]));
  // 机の紙
  el.sheets.forEach((node, i) => setOpacity(node, sheetAlpha(ph, i)));
  // 落ちる紙と受け皿
  let fallingAlpha = 0, fallingOffset = [0, 0, 0];
  if (n === 6 && p > 0.55) {
    const u = clamp01((p - 0.55) / 0.45);
    fallingAlpha = u < 0.95 ? 1 : 1 - (u - 0.95) / 0.05;
    const dy = u * (W.BIN.y + 6 - (W.DESK.y + W.DESK.d - 14));
    const dz = u < 0.5 ? 0 : -(W.DESK_Z - 2) * easeIO((u - 0.5) / 0.5);
    fallingOffset = [0, dy, dz];
  }
  setOpacity(el.falling, fallingAlpha);
  setTransform(el.falling, translateAlong(P, fallingOffset));
  const fallenCount = n < 6 ? 0 : n === 6 ? (p >= 0.99 ? after.dropped : 0) : after.dropped || before.dropped;
  el.fallen.forEach((node, i) => setOpacity(node, i < Math.min(W.FALLEN_MAX, n === 8 ? before.dropped : fallenCount) ? 1 : 0));
  // 読み取りヘッド
  const g = W.GANTRY;
  const left = g.x0 + 10, right = g.x1 - 10;
  let hx = left;
  if (n === 4) hx = lerp(left, right, easeIO(p));
  else if (n === 5) hx = lerp(left, right, 0.5 - 0.5 * Math.cos(Math.PI * 2 * p));
  else if (n > 5 && n < 8) hx = right;
  setTransform(el.head, translateAlong(P, [hx, 0, 0]));
  // 候補ダイヤル: 語 k の候補を札に出し、回す
  let k = -1, spin = 0;
  if (n === 4) { k = 0; spin = p; }
  else if (n === 5) { const u = p * W.WORDS; k = Math.min(W.WORDS - 1, Math.floor(u)); spin = u - k; }
  else if (n > 5 && n < 8) { k = W.WORDS - 1; spin = 1; }
  if (k >= 0) {
    const cands = M.candidatesOf(before, k);
    el.faces.forEach((node, i) => { const text = node.querySelector("text"); const word = cands[i] ? cands[i].word : "　"; if (text.textContent !== word) text.textContent = word; });
  } else el.faces.forEach((node) => { const text = node.querySelector("text"); if (text.textContent !== "　") text.textContent = "　"; });
  setTransform(el.dialGroup, rotateTop([W.DIAL.x, W.DIAL.y], 3 + W.DIAL.h, Math.PI * 2 * ease(spin)));
  // 印字テープの語
  const words = n >= 4 && n < 8 ? after.words : [];
  el.words.forEach((node, i) => {
    const text = node.querySelector("text");
    const word = words[i] || "　";
    if (text.textContent !== word) text.textContent = word;
    let a = 0;
    if (n === 4) a = i === 0 && p > 0.85 ? 1 : 0;
    else if (n === 5) a = p * W.WORDS > i + 0.9 ? 1 : 0;
    else if (n > 5 && n < 8) a = 1;
    setOpacity(node, a);
  });
  // 注意力メーターと条件ピン
  const shareBefore = M.share(before) / 100, shareAfter = M.share(after) / 100;
  const v = n === 7 || n === 8 ? lerp(shareBefore, shareAfter, p) : shareAfter;
  el.needle.setAttribute("d", needleAt(v));
  el.pins.forEach((node, i) => {
    let up = 0;
    if (i < before.conditions) up = 1;
    if (n === 7) up = i < after.conditions ? clamp01(p * after.conditions - i) : 0;
    if (n === 8) up = i < before.conditions ? (i === 0 ? 1 : 1 - p) : 0;
    setOpacity(node.querySelector("[data-pin-up]"), up);
    setOpacity(node.querySelector("[data-pin-down]"), 1 - up);
  });
  // 片付けレバー
  const pull = n === 8 ? Math.sin(Math.PI * p) : 0;
  setTransform(el.lever, translateAlong(P, [W.LEVER.x, W.LEVER.y - 7 * pull, W.LEVER.z + 2.4 - 2.5 * pull]));
  // 読み出し・ヒント・ボタン
  const text = p >= 1 ? M.readout(after) : M.readout(before) + " …";
  if (el.readout.textContent !== text) el.readout.textContent = text;
  const key = n + ":" + (p >= 1 ? "done" : "busy") + ":" + mode;
  if (key !== lastDrawn) {
    lastDrawn = key;
    const step = DATA.steps[n - 1];
    el.hint.textContent = step ? step.hint : "①を押すと、手紙を書くところから始まります。";
    el.sound.textContent = step && p < 1 ? "（" + step.sound + "）" : "";
    el.buttons.forEach((b, i) => {
      const s = i + 1;
      const state = s <= n ? (s === n && p < 1 ? "busy" : "done") : s === n + 1 && p >= 1 ? "next" : "locked";
      b.dataset.state = state;
      b.disabled = !(state === "next" && mode === "manual");
    });
    el.status.textContent = step ? "工程" + n + " " + step.name + "。" + M.readout(after) : M.readout(states[0]);
  }
  drawCursor(t, ph);
}

/* 水平面上の回転（天面の札を回す）。スクリーン変換 = A·R(θ)·A⁻¹ */
function rotateTop([cx, cy], z, theta) {
  const o = iso([cx, cy, z], P);
  const ax = axisVector(P, [1, 0, 0]), ay = axisVector(P, [0, 1, 0]);
  const [a, b, c, d] = [ax[0], ax[1], ay[0], ay[1]];
  const det = a * d - b * c;
  const inv = [d / det, -b / det, -c / det, a / det];
  const cs = Math.cos(theta), sn = Math.sin(theta);
  const r = [cs, sn, -sn, cs];
  const mul = (m, n) => [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3]];
  const T = mul(mul([a, b, c, d], r), inv);
  const e = o[0] - (T[0] * o[0] + T[2] * o[1]);
  const f = o[1] - (T[1] * o[0] + T[3] * o[1]);
  return `matrix(${T.map((x) => x.toFixed(4)).join(" ")} ${e.toFixed(2)} ${f.toFixed(2)})`;
}
function needleAt(v) {
  const m = W.METER, span = Math.PI * 1.5;
  const ang = -span / 2 + v * span;
  return lineOnTop([m.x, m.y], [m.x + Math.sin(ang) * (m.r - 5), m.y - Math.cos(ang) * (m.r - 5)], m.h + 0.03, P);
}

/* ---------- 動画用のカーソル（自動モードのときだけ） ---------- */
function drawCursor(t, ph) {
  if (mode !== "auto" || autoStart === null) { el.cursor.removeAttribute("data-on"); return; }
  let next = null;
  for (let n = 1; n <= 8; n++) if (trig[n] !== null && t < trig[n] + 0.35) { next = n; break; }
  const prev = next ? next - 1 : null;
  if (!next || t < trig[next] - 0.9) { el.cursor.removeAttribute("data-on"); el.cursor.removeAttribute("data-press"); return; }
  const box = app.getBoundingClientRect();
  const center = (n) => { const r = el.buttons[n - 1].getBoundingClientRect(); return [r.left - box.left + r.width * 0.5, r.top - box.top + r.height * 0.5]; };
  const to = center(next), from = prev ? center(prev) : [to[0], to[1] - 40];
  const u = easeIO(clamp01((t - (trig[next] - 0.9)) / 0.75));
  el.cursor.style.left = lerp(from[0], to[0], u) + "px";
  el.cursor.style.top = lerp(from[1], to[1], u) + "px";
  el.cursor.setAttribute("data-on", "");
  if (t >= trig[next] - 0.05 && t < trig[next] + 0.25) el.cursor.setAttribute("data-press", ""); else el.cursor.removeAttribute("data-press");
}

/* ---------- 進め方 ---------- */
function scheduleAuto(from) {
  // from: 次に始める工程。その工程を 1 秒後に置き、以降はスケジュール通り
  const now = clock.now();
  autoStart = now + 1 - SCHEDULE[from];
  for (let n = from; n <= 8; n++) trig[n] = autoStart + SCHEDULE[n];
}
function nextStep() {
  const ph = phaseAt(clock.now());
  if (ph.p < 1 || ph.n >= 8) return;
  trig[ph.n + 1] = clock.now();
  run();
}
function restart() {
  trig = Array(9).fill(null);
  autoStart = null;
  lastDrawn = "";
  if (mode === "auto") scheduleAuto(1);
  run();
}
function setMode(next) {
  if (next === "auto" && calm()) return;
  mode = next;
  el.modes.forEach((b) => b.setAttribute("aria-pressed", b.dataset.mode === mode ? "true" : "false"));
  try { localStorage.setItem("cm-mode", mode); } catch (e) { /* 使えなくてもよい */ }
  const ph = phaseAt(clock.now());
  if (mode === "auto") { if (ph.n < 8) scheduleAuto(ph.n + 1); }
  else { for (let n = ph.n + 1; n <= 8; n++) trig[n] = null; autoStart = null; }
  lastDrawn = "";
  run();
}

/* ---------- 時計 ---------- */
function tick(now) {
  if (!origin) origin = now;
  clock.t = (now - origin) / 1000;
  draw();
  const ph = phaseAt(clock.t);
  const moving = ph.p < 1 || (mode === "auto" && ph.n < 8) || (mode === "auto" && autoStart !== null && clock.t < autoStart + SCHEDULE.end);
  raf = visible && moving ? requestAnimationFrame(tick) : 0;
}
function run() { if (render) { draw(); return; } if (!raf && visible) raf = requestAnimationFrame(tick); else if (!raf) draw(); }

if (render) {
  document.body.classList.add("cm-render");
  autoStart = 0;
  for (let n = 1; n <= 8; n++) trig[n] = SCHEDULE[n];
  window.seek = (t) => { clock.t = t; draw(); return t; };
  window.CM.duration = SCHEDULE.end;
  window.CM.schedule = SCHEDULE;
  draw();
} else {
  new IntersectionObserver((entries) => { visible = entries[entries.length - 1].isIntersecting; if (visible) run(); }, { rootMargin: "120px 0px" }).observe(stage);
  el.buttons.forEach((b, i) => b.addEventListener("click", () => { if (mode === "manual" && b.dataset.state === "next") nextStep(); }));
  el.modes.forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  el.restart.addEventListener("click", restart);
  stage.addEventListener("keydown", (event) => {
    if (event.target.closest("button")) return;
    if (event.key === " " || event.key === "Enter") { event.preventDefault(); if (mode === "manual") nextStep(); }
    if (event.key === "Home") { event.preventDefault(); restart(); }
  });
  if (calm()) { el.modes.find((b) => b.dataset.mode === "auto").disabled = true; el.modes.find((b) => b.dataset.mode === "auto").title = "視覚効果を減らす設定のため、自動は使えません"; }
  el.modes.forEach((b) => b.setAttribute("aria-pressed", b.dataset.mode === mode ? "true" : "false"));
  if (mode === "auto") scheduleAuto(1);
  run();
}
window.CM.live = { phaseAt, clock, trig: () => trig, mode: () => mode };
