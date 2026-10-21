/* 唯一のフレームループ。タブ非表示で止まる。reduced-motion では 2 fps の setInterval に落とす。 */
window.AW = window.AW || {};

AW.loop = (function () {
  const fns = [];
  let running = false, raf = 0, timer = 0, last = 0;

  function frame() {
    if (!running) return;
    const now = Date.now();
    const dt = last ? Math.min(100, now - last) : 16;
    last = now;
    for (let i = 0; i < fns.length; i++) fns[i](now, dt);
    if (AW.state.reduced) timer = setTimeout(frame, 500);
    else raf = requestAnimationFrame(frame);
  }

  function start() {
    if (running) return;
    running = true; last = 0;
    frame();
  }
  function stop() {
    running = false;
    if (raf) cancelAnimationFrame(raf);
    if (timer) clearTimeout(timer);
    raf = 0; timer = 0;
  }

  document.addEventListener('visibilitychange', () => { document.hidden ? stop() : start(); });

  return { register(fn) { fns.push(fn); }, start, stop, get running() { return running; } };
})();
