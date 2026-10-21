/* 状態は 1 つ。各幕は render(state, now) を公開する。 */
window.AW = window.AW || {};

AW.state = {
  scenarioId: AW.DATA.defaultScenario,
  t0: Date.now(),
  litersOffset: 0,
  session: { count: 0, startedAt: null, auto: false, autoEverySec: 30, lastAutoAt: 0 },
  ladder: Object.assign({}, AW.DATA.ladderDefault),
  reduced: !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches),
};

AW._subs = [];
AW.subscribe = function (fn) { AW._subs.push(fn); };
AW.setState = function (patch) {
  const prev = Object.assign({}, AW.state);
  Object.assign(AW.state, patch);
  AW._subs.forEach((fn) => fn(AW.state, prev));
};

AW.scenario = function () { return AW.DATA.scenarios[AW.state.scenarioId]; };

/** 世界の毎秒の水量 [L/s] */
AW.worldRateLps = function (scenarioId) {
  const u = AW.DATA.scenarios[scenarioId || AW.state.scenarioId].mlPerPrompt;
  return AW.DATA.world.promptsPerDay * u / 1000 / 86400;
};

/** 開いてからの世界累計 [L]。蓄積せず t0 から計算する。 */
AW.worldLiters = function (now) {
  const s = AW.state;
  return ((now || Date.now()) - s.t0) / 1000 * AW.worldRateLps() + s.litersOffset;
};

/** シナリオ切替。累計を連続させる。 */
AW.setScenario = function (id) {
  if (!AW.DATA.scenarios[id] || id === AW.state.scenarioId) return;
  const now = Date.now();
  const current = AW.worldLiters(now);
  const newRate = AW.worldRateLps(id);
  const litersOffset = current - (now - AW.state.t0) / 1000 * newRate;
  AW.setState({ scenarioId: id, litersOffset });
  try { localStorage.setItem('aw.scenario', id); } catch (e) { /* file:// 等で失敗しても動く */ }
};

AW.loadPrefs = function () {
  try {
    const id = localStorage.getItem('aw.scenario');
    if (id && AW.DATA.scenarios[id]) AW.state.scenarioId = id;
    const theme = localStorage.getItem('aw.theme');
    if (theme) document.documentElement.setAttribute('data-theme', theme);
  } catch (e) { /* 無視 */ }
};
