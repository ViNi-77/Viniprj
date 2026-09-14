/* 図解プロンプト作成 — 画面。
 *
 * このアプリは図解を描かないので、画面も「投入 → 確かめる → 見た目 → 渡す」の 1 本道。
 * キャンバスもテンプレート編集も持たない。
 *
 * 寸法は px 固定にしない（CSS 側で rem / clamp を使う）。ノート PC の 125〜150% 表示で
 * 文字やボタンが切れないことが受入条件（CLAUDE.md 6 章）。
 */
'use strict';

const PWB = {};
window.PWB = PWB;

const state = {
  sessionId: null,
  filename: '',
  kind: '',
  spec: null,
  specYaml: '',
  sourceTheme: null,
  themeId: null,
  uploadedTheme: null,
  themeSrc: 'source',
  direction: 'to_pptx',
  directions: [],
  kinds: [],
  kindOverrides: {},
  prompt: null,
  warnings: [],
  images: [],
};
PWB.state = () => state;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function logLine(text, level) {
  const ul = $('#log');
  const li = document.createElement('li');
  li.className = 'log-' + (level || 'info');
  const t = new Date().toLocaleTimeString('ja-JP', { hour12: false });
  li.textContent = `[${t}] ${text}`;
  ul.appendChild(li);
  while (ul.children.length > 60) ul.removeChild(ul.firstChild);
  ul.scrollTop = ul.scrollHeight;
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* JSON でない応答 */ }
    throw new Error(detail);
  }
  return res;
}

async function apiJson(path, body) {
  const res = await api(path, body === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json();
}

/* ---------- 1. 投入 ---------- */

async function uploadMain(file) {
  const fd = new FormData();
  fd.append('file', file);
  logLine(`読み込み中: ${file.name}`);
  const data = await (await api('/api/analyze', { method: 'POST', body: fd })).json();
  applyAnalyze(data);
  logLine(`読み込み完了: ${data.spec.slide_count} 枚（${data.kind === 'pptx' ? 'PowerPoint' : 'HTML 図解'}）`);
}

function applyAnalyze(data) {
  state.sessionId = data.session_id;
  state.filename = data.filename;
  state.kind = data.kind;
  state.spec = data.spec;
  state.specYaml = data.spec_yaml;
  state.sourceTheme = data.theme;
  state.warnings = data.warnings || [];
  state.images = data.images || [];
  state.direction = data.suggested_direction || state.direction;
  $('#file-note').hidden = false;
  $('#file-note').textContent = `${data.filename} — ${data.kind === 'pptx' ? 'PowerPoint' : 'HTML 図解'}として読みました（${data.spec.slide_count} 枚）`;
  $('#step-2').hidden = false;
  $('#step-3').hidden = false;
  $('#step-4').hidden = false;
  renderSpec();
  renderTheme();
  renderDirections();
  renderWarnings();
  refreshPrompt();
}

/* ---------- 2. 中身 ---------- */

function contentSummary(s) {
  const bits = [];
  if (s.items && s.items.length) bits.push(`項目 ${s.items.length}`);
  if (s.bullets && s.bullets.length) bits.push(`箇条書き ${s.bullets.length} 行`);
  if (s.table) bits.push(`表 ${(s.table.rows || []).length} 行`);
  if (s.images && s.images.length) bits.push(`画像 ${s.images.length}`);
  if (s.notes) bits.push('ノートあり');
  return bits.length ? bits.join(' / ') : '—';
}

function renderSpec() {
  const tb = $('#spec-table tbody');
  const opts = state.kinds.map((k) => `<option value="${esc(k.id)}">${esc(k.label)}</option>`).join('');
  tb.innerHTML = (state.spec.slides || []).map((s) => `
    <tr data-no="${s.no}">
      <td class="num">${s.no}</td>
      <td class="ttl" title="${esc(s.title)}">${esc(s.title)}</td>
      <td><select data-kind-for="${s.no}" aria-label="${s.no} 枚目の型">${opts}</select></td>
      <td class="reason">${esc(s.kind_reason)}</td>
      <td class="muted">${esc(contentSummary(s))}</td>
    </tr>`).join('');
  (state.spec.slides || []).forEach((s) => {
    const sel = tb.querySelector(`[data-kind-for="${s.no}"]`);
    if (sel) sel.value = s.kind;
  });
  $('#spec-yaml').textContent = state.specYaml;
}

async function changeKind(no, kind) {
  state.kindOverrides[String(no)] = kind;
  const data = await apiJson('/api/spec', { session_id: state.sessionId, kind_overrides: state.kindOverrides });
  state.spec = data.spec;
  state.specYaml = data.spec_yaml;
  state.warnings = data.warnings || [];
  renderSpec();
  renderWarnings();
  await refreshPrompt();
  logLine(`${no} 枚目の型を変えました`);
}

/* ---------- 3. 見た目 ---------- */

function activeTheme() {
  if (state.themeSrc === 'upload') return state.uploadedTheme;
  if (state.themeSrc === 'source') return state.sourceTheme;
  return null;
}

function renderTheme() {
  $('#theme-upload').hidden = state.themeSrc !== 'upload';
  const t = activeTheme();
  const box = $('#theme-preview');
  if (!t || !t.colors || !Object.keys(t.colors).length) {
    box.hidden = state.themeSrc === 'none';
    if (!box.hidden) {
      $('#theme-swatches').innerHTML = '';
      $('#theme-lines').textContent = state.themeSrc === 'upload'
        ? 'テーマをまだ読み込んでいません。'
        : 'このファイルからは配色を読み取れませんでした。見た目の指示なしで進みます。';
    }
    return;
  }
  box.hidden = false;
  $('#theme-swatches').innerHTML = Object.entries(t.colors).map(([role, hex]) =>
    `<span class="sw" title="${esc(role)} ${esc(hex)}"><i style="background:${esc(hex)}"></i>${esc(hex)}</span>`).join('');
  const lines = [];
  if (t.fonts && t.fonts.heading) lines.push(`見出しのフォント: ${t.fonts.heading}`);
  if (t.fonts && t.fonts.body) lines.push(`本文のフォント: ${t.fonts.body}`);
  const d = t.decoration || {};
  const dec = [];
  if (d.radius_px) dec.push(`角丸 ${d.radius_px}px`);
  if (d.shadow) dec.push('影あり');
  if (d.border) dec.push('枠線あり');
  if (dec.length) lines.push('装飾: ' + dec.join(' / '));
  $('#theme-lines').textContent = lines.join('\n') || '配色のみ';
}

async function uploadTheme(file) {
  const fd = new FormData();
  fd.append('file', file);
  logLine(`テーマを読み込み中: ${file.name}`);
  const data = await (await api('/api/theme', { method: 'POST', body: fd })).json();
  state.themeId = data.theme_id;
  state.uploadedTheme = data.theme;
  state.warnings = (state.warnings || []).concat(data.warnings || []);
  renderTheme();
  renderWarnings();
  await refreshPrompt();
  logLine(`テーマを読み込みました: ${data.theme.name}`);
}

/* ---------- 4. 渡す ---------- */

function renderDirections() {
  $('#direction-box').innerHTML = state.directions.map((d) => `
    <label class="direction ${d.id === state.direction ? 'on' : ''}">
      <input type="radio" name="direction" value="${esc(d.id)}" ${d.id === state.direction ? 'checked' : ''}>
      <span class="d-name">${esc(d.name)}</span>
      <span class="d-out">${esc(d.outcome)}</span>
      <span class="d-target">貼り先: ${esc(d.target)}</span>
    </label>`).join('');
}

async function refreshPrompt() {
  if (!state.sessionId) return;
  const body = {
    session_id: state.sessionId,
    direction: state.direction,
    use_source_theme: state.themeSrc === 'source',
    theme_id: state.themeSrc === 'upload' ? state.themeId : null,
  };
  const built = await apiJson('/api/prompt', body);
  state.prompt = built;
  $('#prompt').textContent = built.prompt;
  $('#prompt-chars').textContent = `${built.chars.toLocaleString('ja-JP')} 字`;
  $('#direction-how').textContent = built.how;
  const note = $('#image-note');
  if (built.has_images) {
    const names = state.images.map((i) => i.filename).filter(Boolean);
    note.hidden = false;
    note.textContent = `この資料には画像が ${state.images.length} 個あります。プロンプトはファイル名（${names.slice(0, 3).join('、')}${names.length > 3 ? ' ほか' : ''}）で参照するので、「一式をダウンロード」の画像を Copilot に添付してください。`;
  } else {
    note.hidden = true;
  }
  const extra = (built.warnings || []).filter((w) => w.code === 'PROMPT_TRUNCATED');
  if (extra.length) {
    state.warnings = state.warnings.filter((w) => w.code !== 'PROMPT_TRUNCATED').concat(extra);
    renderWarnings();
  }
}

async function copyPrompt() {
  if (!state.prompt) return;
  try {
    await navigator.clipboard.writeText(state.prompt.prompt);
    logLine('プロンプトをコピーしました。Copilot に貼り付けてください。');
  } catch (e) {
    const pre = $('#prompt');
    const r = document.createRange();
    r.selectNodeContents(pre);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(r);
    logLine('コピーできなかったので、プロンプトを選択しました。Ctrl+C でコピーしてください。', 'warn');
  }
}

async function downloadPack() {
  const body = {
    session_id: state.sessionId,
    direction: state.direction,
    use_source_theme: state.themeSrc === 'source',
    theme_id: state.themeSrc === 'upload' ? state.themeId : null,
  };
  const res = await api('/api/pack.zip', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const blob = await res.blob();
  const cd = res.headers.get('Content-Disposition') || '';
  const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
  const name = m ? decodeURIComponent(m[1]) : 'copilot.zip';
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name; document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  logLine(`一式をダウンロードしました: ${name}`);
}

/* ---------- 警告 ---------- */

function renderWarnings() {
  const seen = new Set();
  const items = (state.warnings || []).filter((w) => {
    const key = w.code + '|' + w.message;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  $('#warn-card').hidden = items.length === 0;
  $('#warn-list').innerHTML = items.map((w) =>
    `<li><code>${esc(w.code)}</code> ${esc(w.message)}${w.fallback ? `<span class="muted">（${esc(w.fallback)}）</span>` : ''}</li>`).join('');
}

/* ---------- 版 ---------- */

async function loadConfig() {
  const cfg = await apiJson('/api/config');
  state.directions = cfg.directions || [];
  state.kinds = cfg.kinds || [];
  state.direction = state.directions.length ? state.directions[0].id : 'to_pptx';
  const b = cfg.build || {};
  $('#version-badge').textContent = `版 ${b.version || cfg.version}${b.commit && b.commit !== '不明' ? ` (${b.commit}${b.dirty ? '+変更あり' : ''})` : ''}`;
  const v = await apiJson('/api/version');
  $('#version-detail').textContent = `版 ${v.version} / コミット ${v.commit} / スキーマ ${v.schema_version}`;
  $('#feature-list').innerHTML = (v.features || []).map((f) =>
    `<li><strong>${esc(f.phase)}. ${esc(f.name)}</strong><span class="muted">${esc(f.hint)}</span></li>`).join('');
  renderDirections();
}

/* ---------- 配線 ---------- */

function bindDropzone(zoneSel, inputSel, handler) {
  const zone = $(zoneSel);
  const input = $(inputSel);
  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault(); zone.classList.remove('over');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) run(handler, e.dataTransfer.files[0]);
  });
  input.addEventListener('change', () => { if (input.files[0]) run(handler, input.files[0]); });
}

async function run(fn, arg) {
  try {
    await fn(arg);
  } catch (e) {
    logLine('失敗: ' + e.message, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  bindDropzone('#dropzone', '#file-input', uploadMain);
  bindDropzone('#theme-dropzone', '#theme-input', uploadTheme);

  document.addEventListener('change', (e) => {
    const t = e.target;
    if (t.name === 'theme-src') {
      state.themeSrc = t.value;
      renderTheme();
      run(refreshPrompt);
    } else if (t.name === 'direction') {
      state.direction = t.value;
      $$('.direction').forEach((el) => el.classList.toggle('on', el.contains(t)));
      run(refreshPrompt);
    } else if (t.dataset && t.dataset.kindFor) {
      run(() => changeKind(t.dataset.kindFor, t.value));
    }
  });

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const act = btn.dataset.action;
    if (act === 'copy') run(copyPrompt);
    else if (act === 'pack') run(downloadPack);
    else if (act === 'version') $('#version-dialog').showModal();
    else if (act === 'version-close') $('#version-dialog').close();
  });

  run(loadConfig);
  logLine('準備できました。PowerPoint か HTML 図解を投入してください。');
});
