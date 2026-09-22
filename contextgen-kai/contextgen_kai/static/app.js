/* contextgen 改 — 画面操作とローカル API の接続。
 * 資料名・本文など外部由来の値は textContent/value で描画し、HTML として実行しない。
 * タイマーはサーバーの状態を取得するだけ。進捗率は実際の処理件数から算出する。
 */
"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {token: "", view: "home", libraries: [], collections: [], jobs: [], schedules: [], exports: [], documents: [], documentTotal: 0, offset: 0, limit: 50, selected: new Map(), currentDocument: null, collectionId: null, collectionIds: [], scheduleId: null, refreshing: false, stopped: false, documentRequest: 0, libraryId: null, rendered: {}};
const stateLabels = {ok: "読み取り済み", partial: "一部読み取り", empty: "本文なし", error: "読み取りエラー", protected: "保護された資料", needs_conversion: "変換が必要", needs_ocr: "OCRの確認が必要", needs_download: "ダウンロードが必要", pending: "読み取り待ち", deleted: "原本削除", missing: "原本が見つかりません", conflict: "修正の確認待ち", excluded: "収録対象外", queued: "実行待ち", scanning: "資料を探しています", extracting: "読み取り中", exporting: "生成中", completed: "完了", held: "確認待ち", failed: "失敗", stopped: "停止", stopping: "停止しています", ready: "生成済み", published: "生成済み", active: "使用中", running: "実行中", disabled: "停止中", success: "完了", restored_disabled: "復元済み・停止中"};
const purposeLabels = {overview: "概要把握", compare: "資料比較", questions: "確認事項の洗い出し"};
const viewLabels = {home: "ホーム", documents: "資料の確認", exports: "Copilotへ渡す", schedules: "定期更新・設定"};
const terminalStates = new Set(["completed", "held", "failed", "stopped"]);

/** DOM 要素を作り、安全に文字列を設定する。 */
function node(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}
function button(text, className, handler) {
  const element = node("button", `button ${className}`, text);
  element.type = "button";
  element.addEventListener("click", () => action(element, handler));
  return element;
}
function emptyState(symbol, title, description) {
  const result = node("div", "empty-state");
  const icon = node("span", "", symbol); icon.setAttribute("aria-hidden", "true");
  result.append(icon, node("strong", "", title), node("p", "", description));
  return result;
}
function badge(status, label) {
  let color = "neutral";
  if (["ok", "completed", "ready", "published", "active", "success"].includes(status)) color = "good";
  else if (["error", "failed", "protected"].includes(status)) color = "error";
  else if (["partial", "empty", "needs_conversion", "needs_ocr", "needs_download", "held", "conflict", "missing", "deleted"].includes(status)) color = "warning";
  else if (["scanning", "extracting", "exporting", "queued", "running", "stopping"].includes(status)) color = "blue";
  return node("span", `badge ${color}`, label || stateLabels[status] || status || "未確認");
}
function dateText(value) {
  if (!value) return "未実行";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ja-JP", {year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"});
}
function countText(value) { return Number(value || 0).toLocaleString("ja-JP"); }
function libraryName(id) { return state.libraries.find(item => String(item.id) === String(id))?.name || "資料フォルダ"; }
function collectionName(id) { return state.collections.find(item => String(item.id) === String(id))?.name || "資料セット"; }
function idValue(value) { return value === "" || value === null || value === undefined ? null : value; }

/** 全更新 API にセッショントークンを付与する。失敗は日本語の画面へ返す。 */
async function api(path, options = {}) {
  const method = options.method || "GET";
  const headers = {...options.headers};
  if (method !== "GET") {
    if (!state.token) throw new Error("アプリ本体への接続が完了してから、もう一度操作してください。");
    headers["X-Contextgen-Token"] = state.token;
  }
  if (options.body && !(options.body instanceof FormData)) { headers["Content-Type"] = "application/json"; options.body = JSON.stringify(options.body); }
  let response;
  try { response = await fetch(`/api${path}`, {...options, method, headers, credentials: "same-origin"}); }
  catch { throw new Error("アプリ本体に接続できません。アプリが起動しているか確認してください。"); }
  if (!response.ok) {
    let message = `処理を完了できませんでした（${response.status}）。`;
    try { const result = await response.json(); if (typeof result.detail === "string") message = result.detail; else if (Array.isArray(result.detail)) message = result.detail.map(item => `${item.loc?.slice(1).join(" / ") || "入力"}: ${item.msg}`).join("\n"); } catch { /* JSON 以外のサーバー応答では状態コードを使う。 */ }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}
function toast(message, isError = false) {
  const element = node("div", `toast${isError ? " error" : ""}`, message);
  if (isError) element.setAttribute("role", "alert");
  $("#toast-region").append(element);
  while ($("#toast-region").childElementCount > 2) $("#toast-region").firstElementChild.remove();
  setTimeout(() => element.remove(), isError ? 12000 : 6000);
}
/** 二重クリックを防ぎ、ダイアログ内の失敗はその場に残す。 */
async function action(element, callback) {
  if (element?.disabled) return;
  const dialog = element?.closest("dialog");
  const error = dialog && $(".form-error", dialog);
  if (error) error.textContent = "";
  if (element) element.disabled = true;
  try { await callback(); }
  catch (cause) { if (error && dialog.open) error.textContent = cause.message; else toast(cause.message, true); }
  finally { if (element?.isConnected) element.disabled = false; }
}
function openDialog(selector) {
  const dialog = $(selector);
  const error = $(".form-error", dialog); if (error) error.textContent = "";
  if (!dialog.open) dialog.showModal();
}
function updateIfChanged(key, data, renderer) {
  const serialized = JSON.stringify(data);
  if (state.rendered[key] !== serialized) { state.rendered[key] = serialized; renderer(); }
}

async function switchView(name) {
  if (!viewLabels[name]) name = "home";
  state.view = name;
  $$(".view").forEach(view => { view.hidden = view.id !== `view-${name}`; });
  $$(".nav-item").forEach(item => { item.classList.toggle("active", item.dataset.view === name); if (item.dataset.view === name) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current"); });
  $("#breadcrumb-current").textContent = viewLabels[name];
  history.replaceState(null, "", `#${name}`);
  if (name === "documents") await loadDocuments();
  if (name === "exports") await loadExports();
}
async function refresh() {
  if (state.refreshing || state.stopped) return;
  state.refreshing = true;
  try {
    const previousJobs = JSON.stringify(state.jobs);
    const data = await api("/status");
    state.token = data.token; state.libraries = data.libraries || []; state.collections = data.collections || []; state.jobs = data.jobs || []; state.schedules = data.schedules || [];
    $("#version").textContent = data.version || "0.1.0";
    $("#connection").classList.remove("offline"); $("#connection").replaceChildren(node("i"), document.createTextNode("ローカル接続中"));
    $("#global-error").hidden = true;
    for (const key of ["total", "ok", "attention", "excluded"]) { const target = $(`#stat-${key}`); target.replaceChildren(document.createTextNode(countText(data.counts?.[key])), node("small", "", "件")); }
    $("#nav-count").textContent = countText(data.counts?.total);
    updateIfChanged("libraries", state.libraries, renderLibraries);
    updateIfChanged("jobs", [state.jobs, state.libraries], renderJobs);
    updateIfChanged("collections", [state.collections, state.libraries], renderCollections);
    updateIfChanged("schedules", [state.schedules, state.libraries], renderSchedules);
    if (state.view === "exports") await loadExports();
    if (state.view === "documents" && previousJobs !== JSON.stringify(state.jobs)) await loadDocuments();
  } catch (cause) {
    $("#connection").classList.add("offline"); $("#connection").replaceChildren(node("i"), document.createTextNode("接続を確認してください"));
    $("#global-error").textContent = cause.message; $("#global-error").hidden = false;
  } finally { state.refreshing = false; }
}

function renderLibraries() {
  const root = $("#libraries"); root.replaceChildren();
  $("#library-count").textContent = `${state.libraries.length} フォルダ`;
  if (!state.libraries.length) root.append(emptyState("▱", "最初の資料を登録しましょう", "資料のあるフォルダを登録すると、ここからいつでも更新できます。"));
  for (const library of state.libraries) {
    const row = node("div", "library-row");
    const info = node("div", "library-info");
    const label = node("div", "min-zero"); label.append(node("strong", "", library.name), node("p", "help", library.path));
    info.append(node("span", "folder-icon", library.kind === "upload" ? "↥" : "▱"), label);
    const actions = node("div", "button-row");
    actions.append(button("読み取る", "secondary small", () => startJob(library.id)), button("変更", "subtle small", () => openLibrary(library)));
    const remove = button("×", "subtle small", async () => {
      if (!confirm(`「${library.name}」の登録を解除しますか？\n原本ファイルは削除しません。関連する設定・履歴への影響を確認してください。`)) return;
      await api(`/libraries/${encodeURIComponent(library.id)}`, {method: "DELETE"}); await refresh(); toast("フォルダの登録を解除しました。");
    }); remove.setAttribute("aria-label", `${library.name} の登録を解除`); actions.append(remove);
    row.append(info, actions); root.append(row);
  }
  const select = $("#document-library"); const current = select.value;
  fillLibraries(select, true); select.value = current;
}
function openLibrary(library = null) {
  state.libraryId = library?.id || null;
  $("#library-form").reset();
  $("#library-title").textContent = library ? "資料フォルダを変更" : "資料フォルダを登録";
  $("#library-name").value = library?.name || "";
  $("#library-path").value = library?.path || "";
  $("#library-form [type=submit]").textContent = library ? "保存して読み取る" : "登録して読み取る";
  openDialog("#library-dialog");
}
function fillLibraries(select, includeAll = false) {
  select.replaceChildren();
  if (includeAll) { const option = node("option", "", "すべてのフォルダ"); option.value = ""; select.append(option); }
  for (const item of state.libraries) { const option = node("option", "", item.name); option.value = item.id; select.append(option); }
  if (!state.libraries.length && !includeAll) { const option = node("option", "", "先に資料フォルダを登録してください"); option.value = ""; select.append(option); }
}
async function startJob(libraryId) {
  await api("/jobs", {method: "POST", body: {library_id: libraryId, collection_id: null, export_after: false}});
  await refresh(); toast("資料の読み取りを開始しました。");
}
function renderJobs() {
  const root = $("#jobs"); root.replaceChildren();
  if (!state.jobs.length) { root.append(emptyState("◷", "まだ処理はありません", "資料を登録すると、読み取りの進捗と結果をここで確認できます。")); return; }
  for (const job of state.jobs.slice(0, 10)) {
    const row = node("div", "job-row"), content = node("div", "job-content"), title = node("div", "job-topline");
    title.append(node("strong", "", libraryName(job.library_id)), badge(job.state)); content.append(title);
    if (!terminalStates.has(job.state)) {
      const progress = node("div", "job-progress"); const fill = node("span");
      if (job.total > 0) { progress.setAttribute("role", "progressbar"); progress.setAttribute("aria-label", "資料の処理進捗"); progress.setAttribute("aria-valuenow", String(job.processed || 0)); progress.setAttribute("aria-valuemin", "0"); progress.setAttribute("aria-valuemax", String(job.total)); fill.style.width = `${Math.min(100, (job.processed || 0) / job.total * 100)}%`; }
      progress.append(fill); content.append(progress);
    }
    const details = node("div", "job-meta");
    details.append(node("span", "", job.message || stateLabels[job.stage] || job.stage || ""), node("span", "", `${countText(job.processed)}${job.total ? ` / ${countText(job.total)}` : ""} 件${job.errors ? ` · エラー ${countText(job.errors)} 件` : ""}`));
    content.append(details, node("p", "help", dateText(job.updated_at || job.created_at)));
    const actions = node("div", "button-row");
    if (!terminalStates.has(job.state)) actions.append(button("停止", "subtle small", async () => { await api(`/jobs/${encodeURIComponent(job.id)}/stop`, {method: "POST", body: {}}); await refresh(); toast("停止を要求しました。処理中のファイルが完了するまでお待ちください。"); }));
    if (["stopped", "failed"].includes(job.state)) actions.append(button("再開", "secondary small", async () => { await api(`/jobs/${encodeURIComponent(job.id)}/resume`, {method: "POST", body: {}}); await refresh(); toast("処理を再開しました。"); }));
    if (job.state === "held") actions.append(button("確認する", "secondary small", () => switchView("exports")));
    row.append(content, actions); root.append(row);
  }
}
async function upload(files) {
  if (!files.length) return;
  const form = new FormData(); for (const file of files) form.append("files", file, file.name);
  form.append("name", files.length === 1 ? files[0].name : `${files[0].name} ほか${files.length - 1}件`);
  $("#upload-state").textContent = `${files.length} 件の資料を取り込んでいます…`;
  $("#dropzone").setAttribute("aria-busy", "true");
  try { const library = await api("/uploads", {method: "POST", body: form}); await startJob(library.id); $("#upload-state").textContent = `${files.length} 件を取り込みました。読み取り状況をご確認ください。`; }
  catch (cause) { $("#upload-state").textContent = cause.message; throw cause; }
  finally { $("#dropzone").removeAttribute("aria-busy"); $("#upload-files").value = ""; }
}

async function loadDocuments() {
  const request = ++state.documentRequest;
  const params = new URLSearchParams({q: $("#document-query").value.trim(), library_id: $("#document-library").value, status: $("#document-status").value, offset: state.offset, limit: state.limit});
  const data = await api(`/documents?${params}`);
  if (request !== state.documentRequest) return;
  state.documents = data.items || []; state.documentTotal = data.total || 0;
  renderDocuments();
}
function renderDocuments() {
  const root = $("#documents"); root.replaceChildren();
  $("#document-result-count").textContent = `${countText(state.documentTotal)} 件の資料`;
  $("#documents-empty").hidden = !!state.documents.length;
  for (const doc of state.documents) {
    const row = node("tr"), checkCell = node("td"), input = document.createElement("input"); input.type = "checkbox"; input.checked = state.selected.has(doc.id); input.setAttribute("aria-label", `${doc.relative_path} を選択`);
    input.addEventListener("change", () => { if (input.checked) state.selected.set(doc.id, doc); else state.selected.delete(doc.id); updateSelection(); }); checkCell.append(input);
    const nameCell = node("td"); const title = button(doc.relative_path, "", () => showDocument(doc.id)); title.className = "doc-title-button";
    nameCell.append(title, node("p", "help", libraryName(doc.library_id)));
    const statusCell = node("td"); statusCell.append(badge(doc.status));
    if (doc.excluded) statusCell.append(document.createTextNode(" "), badge("excluded"));
    if (doc.conflict) statusCell.append(document.createTextNode(" "), badge("conflict"));
    if (doc.warning_count) statusCell.append(node("p", "help", `注意事項 ${doc.warning_count} 件`));
    const dateCell = node("td", "help", dateText(doc.updated_at)), actionCell = node("td"); actionCell.append(button("確認", "subtle small", () => showDocument(doc.id)));
    row.append(checkCell, nameCell, statusCell, dateCell, actionCell); root.append(row);
  }
  $("#previous-page").disabled = state.offset === 0; $("#next-page").disabled = state.offset + state.limit >= state.documentTotal;
  $("#page-info").textContent = state.documentTotal ? `${Math.floor(state.offset / state.limit) + 1} / ${Math.ceil(state.documentTotal / state.limit)} ページ` : "0 / 0";
  updateSelection();
}
function updateSelection() {
  $("#selection-count").textContent = state.selected.size ? `${state.selected.size} 件選択中` : "";
  $("#collection-from-selection").disabled = !state.selected.size;
  $("#select-page").checked = !!state.documents.length && state.documents.every(item => state.selected.has(item.id));
  $("#select-page").indeterminate = state.documents.some(item => state.selected.has(item.id)) && !$("#select-page").checked;
}
async function showDocument(id) {
  const doc = await api(`/documents/${encodeURIComponent(id)}`); state.currentDocument = doc;
  $("#document-title").textContent = doc.relative_path;
  $("#document-meta").textContent = `${libraryName(doc.library_id)} · ${stateLabels[doc.status] || doc.status} · ${dateText(doc.updated_at)}`;
  $("#document-excluded").checked = !!doc.excluded;
  $("#original-text").value = doc.original_text || ""; $("#edited-text").value = doc.edited_text ?? doc.effective_text ?? doc.original_text ?? "";
  $("#document-conflict").hidden = !doc.conflict;
  const warnings = $("#document-warnings"); warnings.replaceChildren();
  for (const warning of doc.warnings || []) warnings.append(node("div", "", typeof warning === "string" ? warning : JSON.stringify(warning)));
  const units = $("#document-units"); units.replaceChildren();
  for (const unit of (doc.units || [])) { const item = node("div", "source-unit"); item.append(node("strong", "", `${unit.locator || "本文"} · ${stateLabels[unit.status] || unit.status || "読み取り結果"}`), node("p", "", unit.text || "本文なし")); units.append(item); }
  if (!doc.units?.length) units.append(node("p", "help", "ページ単位の出典情報はありません。"));
  const fileName = doc.relative_path || ""; const preview = $("#document-preview"); preview.replaceChildren(); $("#preview-details").open = false;
  const isPdf = /\.pdf$/i.test(fileName), isImage = /\.(png|jpe?g|gif|webp|bmp|tiff?)$/i.test(fileName);
  $("#preview-details").hidden = !isPdf && !isImage;
  $("#preview-details").ontoggle = () => {
    if (!$("#preview-details").open || preview.childElementCount) return;
    const media = document.createElement(isPdf ? "iframe" : "img"); media.src = `/api/documents/${encodeURIComponent(doc.id)}/preview`;
    if (isPdf) media.title = "原本PDFのプレビュー";
    else {
      media.alt = fileName;
      media.addEventListener("error", () => {
        if (media.isConnected && state.currentDocument?.id === doc.id) preview.replaceChildren(node("p", "help", "画像をプレビューできませんでした。原本の場所を確認し、「原本を開く」から確認してください。"));
      });
    }
    preview.append(media);
  };
  openDialog("#document-dialog");
}
async function saveDocument(discard = false) {
  const doc = state.currentDocument; if (!doc) return;
  if (discard && !confirm("保存した修正を破棄し、最新の読み取り原文に戻しますか？")) return;
  const body = {excluded: $("#document-excluded").checked, text: discard ? null : $("#edited-text").value, expected_hash: doc.source_hash};
  await api(`/documents/${encodeURIComponent(doc.id)}`, {method: "PUT", body});
  $("#document-dialog").close(); await loadDocuments(); await refresh(); toast(discard ? "修正を破棄し、原文に戻しました。" : "修正を保存しました。原本は変更していません。");
}

function renderCollections() {
  const root = $("#collections"); root.replaceChildren();
  if (!state.collections.length) { root.append(emptyState("▧", "用途に合わせて、資料をまとめる", "まず資料セットを作成してください。対象のフォルダ、検索条件、Copilotにしてほしいことを保存できます。")); return; }
  for (const collection of state.collections) {
    const card = node("article", "collection-card"); card.append(node("div", "collection-type", `▧  ${purposeLabels[collection.purpose] || "資料セット"}`), node("h3", "", collection.name));
    card.append(node("p", "", `${libraryName(collection.library_id)}${collection.folder ? ` / ${collection.folder}` : ""}`));
    const conditions = []; if (collection.query) conditions.push(`検索：${collection.query}`); if (collection.document_ids?.length) conditions.push(`個別選択：${collection.document_ids.length} 件`);
    card.append(node("p", "", conditions.join(" · ") || "フォルダ内の収録対象資料すべて"));
    const actions = node("div", "button-row"); actions.append(button("ナレッジを生成", "primary", async () => { await api("/exports", {method: "POST", body: {collection_id: collection.id, force: false}}); await refresh(); await loadExports(); toast("ナレッジの生成を開始しました。生成結果は下の一覧に表示されます。"); }), button("編集", "subtle", () => openCollection(collection)));
    card.append(actions); root.append(card);
  }
}
function openCollection(collection = null, fromSelection = false) {
  if (!state.libraries.length) { toast("先にホームで資料フォルダを登録してください。", true); return; }
  state.collectionId = collection?.id || null; state.collectionIds = collection?.document_ids ? [...collection.document_ids] : fromSelection ? [...state.selected.keys()] : [];
  let selectedLibrary = collection?.library_id || $("#document-library").value || state.libraries[0].id;
  if (fromSelection) {
    const libraries = new Set([...state.selected.values()].map(doc => String(doc.library_id)));
    if (libraries.size > 1) { toast("資料セットはフォルダごとに作成します。選択する資料をひとつの登録フォルダに揃えてください。", true); return; }
    selectedLibrary = [...libraries][0];
  }
  $("#collection-title").textContent = collection ? "資料セットを編集" : "資料セットを作成";
  $("#collection-name").value = collection?.name || ""; fillLibraries($("#collection-library")); $("#collection-library").value = selectedLibrary;
  $("#collection-folder").value = collection?.folder || ""; $("#collection-query").value = collection?.query || ""; $("#collection-purpose").value = collection?.purpose || "overview"; $("#collection-instructions").value = collection?.instructions || "";
  updateCollectionSelection(); openDialog("#collection-dialog");
}
function updateCollectionSelection() {
  $("#collection-selection").value = state.collectionIds.length ? `${state.collectionIds.length} 件を個別に指定` : "指定なし：条件に合う資料すべて";
  $("#clear-collection-selection").hidden = !state.collectionIds.length;
}
async function loadExports() {
  state.exports = await api("/exports"); updateIfChanged("exports", [state.exports, state.collections], renderExports);
}
function renderExports() {
  const root = $("#exports"); root.replaceChildren();
  if (!state.exports.length) { root.append(emptyState("↗", "生成したナレッジはここに表示されます", "資料セットの「ナレッジを生成」から出力を作成できます。")); return; }
  for (const item of state.exports) {
    const row = node("div", "export-row"), info = node("div", "export-info"), title = node("div", "export-title");
    title.append(node("strong", "", collectionName(item.collection_id)), badge(item.state)); if (item.is_active) title.append(badge("active", "現在の出力"));
    info.append(title, node("p", "help", `${dateText(item.created_at)} · ${countText(item.document_count)} 資料 · 本文 ${countText(item.chunk_count)} ファイル`));
    if (item.reason) info.append(node("p", "export-reason", item.reason));
    const actions = node("div", "button-row");
    if (!["failed", "building", "generating"].includes(item.state)) {
      const download = node("a", "button secondary small", "一式をダウンロード"); download.href = `/api/exports/${encodeURIComponent(item.id)}/download`; download.setAttribute("download", ""); actions.append(download);
      actions.append(button("指示文", "subtle small", async () => { const data = await api(`/exports/${encodeURIComponent(item.id)}/prompt`); $("#prompt-text").value = data.text; openDialog("#prompt-dialog"); }));
      actions.append(button("保存先を開く", "subtle small", async () => { await api(`/exports/${encodeURIComponent(item.id)}/open`, {method: "POST", body: {}}); toast("保存先を開きました。"); }));
      if (!item.is_active) actions.append(button(item.state === "held" ? "確認して使用する" : "この世代を使用", "secondary small", async () => {
        if (!confirm(`この世代を現在の出力として使用しますか？${item.reason ? `\n\n確認事項：${item.reason}` : ""}\n読み取り結果と未収録資料を確認したうえで確定してください。`)) return;
        await api(`/exports/${encodeURIComponent(item.id)}/activate`, {method: "POST", body: {}}); await loadExports(); toast("この世代を現在の出力に設定しました。");
      }));
    }
    row.append(info, actions); root.append(row);
  }
}

function renderSchedules() {
  const root = $("#schedules"); root.replaceChildren();
  if (!state.schedules.length) { root.append(emptyState("◷", "定期更新はまだ設定されていません", "曜日・時刻・実行間隔を決めて、資料をいつも新しい状態に保てます。")); return; }
  for (const schedule of state.schedules) {
    const row = node("div", "schedule-row"), info = node("div", "schedule-info"), badges = node("div", "button-row");
    badges.append(badge(schedule.enabled ? "ok" : "disabled", schedule.enabled ? "有効" : "停止中"), badge("neutral", schedule.mode === "background" ? "アプリ終了後も実行" : "アプリ起動中のみ"));
    const frequency = schedule.frequency === "interval" ? `${schedule.interval_minutes} 分ごと` : `${schedule.frequency === "weekly" ? (schedule.weekdays || []).map(index => ["月", "火", "水", "木", "金", "土", "日"][index]).join("・") : "毎日"} ${schedule.time || ""}`;
    info.append(badges, node("h3", "", schedule.name), node("p", "schedule-time", `${libraryName(schedule.library_id)} · ${frequency}${schedule.collection_id ? ` · ${collectionName(schedule.collection_id)} を生成` : ""}`), node("p", "schedule-time", `次回：${schedule.enabled ? dateText(schedule.next_run) : "停止中"}`), node("p", "schedule-result", `前回：${dateText(schedule.last_run)}${schedule.last_result ? ` · ${stateLabels[schedule.last_result] || schedule.last_result}` : ""}`));
    if (schedule.last_error) info.append(node("p", "export-reason", schedule.last_error));
    const actions = node("div", "button-row");
    actions.append(button("今すぐ実行", "secondary small", async () => { await api(`/schedules/${encodeURIComponent(schedule.id)}/run`, {method: "POST", body: {}}); await refresh(); toast("定期更新の処理を開始しました。ホームで進捗を確認できます。"); }), button("編集", "subtle small", () => openSchedule(schedule)), button(schedule.enabled ? "停止" : "有効にする", "subtle small", async () => { await api(`/schedules/${encodeURIComponent(schedule.id)}`, {method: "PUT", body: {...schedule, enabled: !schedule.enabled}}); await refresh(); toast(schedule.enabled ? "定期更新を停止しました。" : "定期更新を有効にしました。"); }), button("削除", "subtle small", async () => { if (!confirm(`「${schedule.name}」の定期更新を削除しますか？\nWindowsの予約がある場合は登録を解除します。`)) return; await api(`/schedules/${encodeURIComponent(schedule.id)}`, {method: "DELETE"}); await refresh(); toast("定期更新を削除しました。"); }));
    row.append(info, actions); root.append(row);
  }
}
function fillScheduleCollections(selected = "") {
  const select = $("#schedule-collection"); select.replaceChildren(); const blank = node("option", "", "読み取りのみ"); blank.value = ""; select.append(blank);
  for (const collection of state.collections.filter(item => String(item.library_id) === $("#schedule-library").value)) { const option = node("option", "", collection.name); option.value = collection.id; select.append(option); }
  select.value = selected || "";
}
function frequencyChanged() {
  const frequency = $("#schedule-frequency").value;
  $("#schedule-weekdays").hidden = frequency !== "weekly"; $("#schedule-time-label").hidden = frequency === "interval"; $("#schedule-interval-label").hidden = frequency !== "interval";
  $("#schedule-time").required = frequency !== "interval"; $("#schedule-interval").required = frequency === "interval";
}
function openSchedule(schedule = null) {
  if (!state.libraries.length) { toast("先にホームで資料フォルダを登録してください。", true); return; }
  state.scheduleId = schedule?.id || null; $("#schedule-form").reset(); $("#schedule-title").textContent = schedule ? "定期更新を編集" : "定期更新を追加";
  $("#schedule-name").value = schedule?.name || ""; fillLibraries($("#schedule-library")); $("#schedule-library").value = schedule?.library_id || state.libraries[0].id; fillScheduleCollections(schedule?.collection_id);
  $(`input[name="schedule-mode"][value="${schedule?.mode === "background" ? "background" : "app"}"]`).checked = true;
  $("#schedule-frequency").value = schedule?.frequency || "daily"; $("#schedule-time").value = schedule?.time || "09:00"; $("#schedule-interval").value = schedule?.interval_minutes || 60; $("#schedule-enabled").checked = schedule?.enabled ?? true;
  $$("#schedule-weekdays input").forEach(input => { input.checked = (schedule?.weekdays || [0, 1, 2, 3, 4]).includes(Number(input.value)); });
  frequencyChanged(); openDialog("#schedule-dialog");
}

// 静的な操作部の接続。フォームの値はポーリングで上書きしない。
function documentIsDirty() {
  const doc = state.currentDocument;
  return doc && ($("#edited-text").value !== (doc.edited_text ?? doc.effective_text ?? doc.original_text ?? "") || $("#document-excluded").checked !== !!doc.excluded);
}
$$("[data-close]").forEach(element => element.addEventListener("click", () => {
  const dialog = element.closest("dialog");
  if (dialog.id === "document-dialog" && documentIsDirty() && !confirm("保存していない変更があります。変更を破棄して閉じますか？")) return;
  dialog.close();
}));
$("#document-dialog").addEventListener("cancel", event => { if (documentIsDirty() && !confirm("保存していない変更があります。変更を破棄して閉じますか？")) event.preventDefault(); });
$$(".nav-item").forEach(element => element.addEventListener("click", () => action(null, () => switchView(element.dataset.view))));
$(".brand").addEventListener("click", event => { event.preventDefault(); action(null, () => switchView("home")); });
$("#add-library").addEventListener("click", () => openLibrary());
$("#pick-folder").addEventListener("click", event => action(event.currentTarget, async () => { const result = await api("/pick-folder", {method: "POST", body: {}}); if (result.path) { $("#library-path").value = result.path; if (!$("#library-name").value) $("#library-name").value = result.path.replace(/[\\/]+$/, "").split(/[\\/]/).pop(); } }));
$("#library-form").addEventListener("submit", event => { event.preventDefault(); action($("#library-form [type=submit]"), async () => { const library = await api(state.libraryId ? `/libraries/${encodeURIComponent(state.libraryId)}` : "/libraries", {method: state.libraryId ? "PUT" : "POST", body: {name: $("#library-name").value.trim(), path: $("#library-path").value.trim()}}); $("#library-dialog").close(); await startJob(library.id); }); });
$("#refresh-status").addEventListener("click", event => action(event.currentTarget, refresh));
$("#refresh-exports").addEventListener("click", event => action(event.currentTarget, async () => { await refresh(); await loadExports(); }));
$("#dropzone").addEventListener("click", () => { if (!$("#dropzone").hasAttribute("aria-busy")) $("#upload-files").click(); });
$("#dropzone").addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); $("#dropzone").click(); } });
$("#upload-files").addEventListener("change", event => action(null, () => upload([...event.target.files])));
for (const type of ["dragenter", "dragover"]) $("#dropzone").addEventListener(type, event => { event.preventDefault(); $("#dropzone").classList.add("dragging"); });
for (const type of ["dragleave", "drop"]) $("#dropzone").addEventListener(type, event => { event.preventDefault(); $("#dropzone").classList.remove("dragging"); });
$("#dropzone").addEventListener("drop", event => { if (!$("#dropzone").hasAttribute("aria-busy")) action(null, () => upload([...event.dataTransfer.files])); });
document.addEventListener("dragover", event => event.preventDefault()); document.addEventListener("drop", event => event.preventDefault());
$("#search-form").addEventListener("submit", event => { event.preventDefault(); state.offset = 0; action($("#search-form [type=submit]"), loadDocuments); });
for (const selector of ["#document-library", "#document-status"]) $(selector).addEventListener("change", () => { state.offset = 0; action(null, loadDocuments); });
$("#previous-page").addEventListener("click", event => { state.offset = Math.max(0, state.offset - state.limit); action(null, loadDocuments); });
$("#next-page").addEventListener("click", event => { state.offset += state.limit; action(null, loadDocuments); });
$("#select-page").addEventListener("change", event => { for (const doc of state.documents) { if (event.target.checked) state.selected.set(doc.id, doc); else state.selected.delete(doc.id); } renderDocuments(); });
$("#save-document").addEventListener("click", event => action(event.currentTarget, () => saveDocument(false)));
$("#discard-edits").addEventListener("click", event => action(event.currentTarget, () => saveDocument(true)));
$("#open-original").addEventListener("click", event => action(event.currentTarget, async () => { await api(`/documents/${encodeURIComponent(state.currentDocument.id)}/open`, {method: "POST", body: {}}); toast("原本を開きました。"); }));
$("#add-collection").addEventListener("click", () => openCollection());
$("#collection-from-selection").addEventListener("click", () => openCollection(null, true));
$("#clear-collection-selection").addEventListener("click", () => { state.collectionIds = []; updateCollectionSelection(); });
$("#collection-library").addEventListener("change", () => { state.collectionIds = []; updateCollectionSelection(); });
$("#collection-form").addEventListener("submit", event => { event.preventDefault(); action($("#collection-form [type=submit]"), async () => { const body = {name: $("#collection-name").value.trim(), library_id: $("#collection-library").value, folder: $("#collection-folder").value.trim(), query: $("#collection-query").value.trim(), document_ids: state.collectionIds, purpose: $("#collection-purpose").value, instructions: $("#collection-instructions").value}; await api(state.collectionId ? `/collections/${encodeURIComponent(state.collectionId)}` : "/collections", {method: state.collectionId ? "PUT" : "POST", body}); $("#collection-dialog").close(); await refresh(); await switchView("exports"); toast("資料セットを保存しました。"); }); });
$("#copy-prompt").addEventListener("click", event => action(event.currentTarget, async () => { const text = $("#prompt-text").value; if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text); else { $("#prompt-text").select(); if (!document.execCommand("copy")) throw new Error("自動コピーできませんでした。本文を選択してコピーしてください。"); } toast("指示文をコピーしました。"); }));
$("#add-schedule").addEventListener("click", () => openSchedule());
$("#schedule-frequency").addEventListener("change", frequencyChanged);
$("#schedule-library").addEventListener("change", () => fillScheduleCollections());
$("#schedule-form").addEventListener("submit", event => { event.preventDefault(); action($("#schedule-form [type=submit]"), async () => { const body = {name: $("#schedule-name").value.trim(), library_id: $("#schedule-library").value, collection_id: idValue($("#schedule-collection").value), enabled: $("#schedule-enabled").checked, mode: $("input[name=schedule-mode]:checked").value, frequency: $("#schedule-frequency").value, time: $("#schedule-time").value || "09:00", interval_minutes: Number($("#schedule-interval").value), weekdays: $$("#schedule-weekdays input:checked").map(item => Number(item.value))}; if (body.frequency === "weekly" && !body.weekdays.length) throw new Error("実行する曜日を1つ以上選択してください。"); if (!body.weekdays.length) body.weekdays = [0, 1, 2, 3, 4, 5, 6]; await api(state.scheduleId ? `/schedules/${encodeURIComponent(state.scheduleId)}` : "/schedules", {method: state.scheduleId ? "PUT" : "POST", body}); $("#schedule-dialog").close(); await refresh(); toast("定期更新の設定を保存しました。"); }); });
$("#restore-button").addEventListener("click", () => $("#restore-file").click());
$("#restore-file").addEventListener("change", event => action($("#restore-button"), async () => { const file = event.target.files[0]; if (!file) return; try { if (!confirm("バックアップから設定・資料の参照情報・修正内容を復元しますか？\n空のワークスペースでのみ実行できます。原本ファイルは復元されません。定期更新は停止状態になります。")) return; const form = new FormData(); form.append("file", file); await api("/restore", {method: "POST", body: form}); state.rendered = {}; await refresh(); toast("バックアップを復元しました。原本の場所を確認し、資料を再読み取りしてください。定期更新は停止しています。"); } finally { event.target.value = ""; } }));
$("#shutdown-button").addEventListener("click", event => action(event.currentTarget, async () => { if (!confirm("アプリ本体を終了しますか？\n実行中の処理は安全に停止します。「アプリ起動中のみ」の定期更新は停止します。")) return; await api("/shutdown", {method: "POST", body: {}}); state.stopped = true; $("#connection").classList.add("offline"); $("#connection").replaceChildren(node("i"), document.createTextNode("アプリは終了しました")); $("#global-error").className = "notice info"; $("#global-error").textContent = "アプリを終了しました。このブラウザ画面は閉じて構いません。もう一度使うときはアプリを起動してください。"; $("#global-error").hidden = false; }));

// 初期取得が終わるまで、トークンを使う操作を開始しない。
(async () => { await refresh(); await action(null, () => switchView(location.hash.slice(1) || "home")); setInterval(() => { if (!document.hidden) refresh(); }, 3000); })();
