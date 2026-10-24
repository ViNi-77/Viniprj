/* 唯一のフレームループ。タブ非表示で止まる。reduced-motion では 1 秒ごとの setTimeout。 */
type Fn = (now: number, dt: number) => void;
const fns: Fn[] = [];
let running = false, raf = 0, timer = 0, last = 0, reduced = false;

function frame() {
  if (!running) return;
  const now = Date.now();
  const dt = last ? Math.min(100, now - last) : 16;
  last = now;
  for (const fn of fns) fn(now, dt);
  if (reduced) timer = window.setTimeout(frame, 1000);
  else raf = requestAnimationFrame(frame);
}
export const loop = {
  register(fn: Fn) { fns.push(fn); },
  start() { if (running) return; running = true; last = 0; frame(); },
  stop() { running = false; cancelAnimationFrame(raf); clearTimeout(timer); raf = 0; timer = 0; },
  setReduced(v: boolean) { reduced = v; if (running) { loop.stop(); loop.start(); } },
  get running() { return running; },
  get reduced() { return reduced; },
};
document.addEventListener('visibilitychange', () => { document.hidden ? loop.stop() : loop.start(); });
