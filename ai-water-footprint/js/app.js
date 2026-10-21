/* 配線と起動。 */
window.AW = window.AW || {};

AW.boot = function () {
  const D = AW.DATA;
  AW.loadPrefs();

  // シナリオ切替（上部バー）
  const segButtons = Array.from(document.querySelectorAll('.seg button[data-scenario]'));
  const scValue = document.getElementById('sc-value'), scUnit = document.getElementById('sc-unit'),
        scName = document.getElementById('sc-name'), scSrc = document.getElementById('sc-src');
  function renderScenario(state) {
    const sc = D.scenarios[state.scenarioId];
    segButtons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.scenario === sc.id)));
    scValue.textContent = AW.fmt.perPrompt(sc.mlPerPrompt); scValue.dataset.value = String(sc.mlPerPrompt);
    scUnit.textContent = ' / ' + sc.unit;
    scName.textContent = sc.name;
    scSrc.textContent = sc.source.short; scSrc.href = sc.source.url;
    document.querySelectorAll('#src-scenarios tr[data-id]').forEach((tr) => tr.classList.toggle('is-current', tr.dataset.id === sc.id));
  }
  segButtons.forEach((b) => b.addEventListener('click', () => AW.setScenario(b.dataset.scenario)));

  // 配色
  const themeBtn = document.getElementById('theme-btn');
  themeBtn.addEventListener('click', () => {
    const root = document.documentElement;
    const dark = root.getAttribute('data-theme') === 'dark' || (!root.getAttribute('data-theme') && window.matchMedia('(prefers-color-scheme: dark)').matches);
    const next = dark ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('aw.theme', next); } catch (e) { /* 無視 */ }
  });

  // 幕 4 の表（data.js から描く。手書きしない）
  const tb = document.querySelector('#src-scenarios tbody');
  D.scenarioOrder.forEach((id) => {
    const sc = D.scenarios[id];
    const tr = document.createElement('tr'); tr.dataset.id = id;
    tr.innerHTML =
      '<th scope="row" data-h="シナリオ">' + sc.label + '・' + sc.name + '</th>' +
      '<td class="n" data-h="1 回あたり">' + AW.fmt.perPrompt(sc.mlPerPrompt) + ' / ' + sc.unit + '</td>' +
      '<td data-h="出典"><a href="' + sc.source.url + '" target="_blank" rel="noopener">' + sc.source.title + '</a></td>' +
      '<td class="scope" data-h="含むもの">' + sc.scope + '</td>' +
      '<td class="scope" data-h="注意">' + sc.note + '</td>';
    tb.appendChild(tr);
  });
  const cb = document.querySelector('#src-comparisons tbody');
  D.comparisons.forEach((c) => {
    const tr = document.createElement('tr');
    const vol = AW.fmt.volume(c.mL);
    tr.innerHTML =
      '<th scope="row" data-h="対象">' + c.name + (c.verified ? '' : '<span class="tag">目安</span>') + '</th>' +
      '<td class="n" data-h="容量">' + vol.text + '</td>' +
      '<td class="scope" data-h="出典">' + (c.url ? '<a href="' + c.url + '" target="_blank" rel="noopener">' + c.src + '</a>' : c.src) + '</td>';
    cb.appendChild(tr);
  });
  const w = document.getElementById('world-src');
  if (w) { w.textContent = D.world.source.short; w.href = D.world.source.url; }

  AW.hero.init(); AW.session.init(); AW.ladder.init();
  renderScenario(AW.state);
  AW.subscribe(renderScenario);

  const scenes = [AW.hero, AW.session, AW.ladder];
  AW.loop.register((now, dt) => { for (const s of scenes) s.render(AW.state, now, dt); });
  AW.loop.start();
};

document.addEventListener('DOMContentLoaded', AW.boot);
