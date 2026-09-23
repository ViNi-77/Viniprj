/* contextgen 改 — 画面操作とローカル API の接続。
 * 資料名・本文など外部由来の値は textContent/value で描画し、HTML として実行しない。
 * タイマーはサーバーの状態を取得するだけ。進捗率は実際の処理件数から算出する。
 */
"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {token: "", view: "home", libraries: [], collections: [], jobs: [], schedules: [], exports: [], documents: [], documentTotal: 0, offset: 0, limit: 50, selected: new Map(), currentDocument: null, collectionId: null, collectionIds: [], scheduleId: null, refreshing: false, stopped: false, documentRequest: 0, libraryId: null, documentOpener: null, collectionDraft: null, cleanupDocumentId: null, handoffId: null, preflightId: null, rendered: {}};
const stateLabels = {ok: "読み取り済み", partial: "一部読み取り", empty: "本文なし", error: "読み取りエラー", protected: "保護された資料", needs_conversion: "変換が必要", needs_ocr: "OCRの確認が必要", needs_download: "ダウンロードが必要", pending: "読み取り待ち", deleted: "原本削除", missing: "原本が見つかりません", conflict: "修正の確認待ち", excluded: "収録対象外", queued: "実行待ち", scanning: "資料を探しています", extracting: "読み取り中", exporting: "生成中", completed: "完了", held: "確認待ち", failed: "失敗", stopped: "停止", stopping: "停止しています", ready: "生成済み", published: "生成済み", active: "使用中", running: "実行中", disabled: "停止中", success: "完了", restored_disabled: "復元済み・停止中"};
const purposeLabels = {overview: "概要把握", compare: "資料比較", questions: "確認事項の洗い出し", procedure: "手順案内", reference: "規程・仕様の照会"};
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
  const hadFocus = document.activeElement === element; let failed = false;
  if (element) element.disabled = true;
  try { await callback(); }
  catch (cause) { failed = true; if (error && dialog.open) error.textContent = cause.message; else toast(cause.message, true); }
  finally { if (element?.isConnected) { element.disabled = element.dataset.page === "previous" ? state.offset === 0 : element.dataset.page === "next" ? state.offset + state.limit >= state.documentTotal : false; if (failed && hadFocus && !element.disabled && document.activeElement === document.body) element.focus({preventScroll: true}); } }
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
    $("#version").textContent = data.version || "0.3.0";
    $("#connection").classList.remove("offline"); $("#connection").replaceChildren(node("i"), document.createTextNode("ローカル接続中"));
    $("#global-error").hidden = true;
    for (const key of ["total", "ok", "attention", "excluded"]) { const target = $(`#stat-${key}`); target.replaceChildren(document.createTextNode(countText(data.counts?.[key])), node("small", "", "件")); }
    $("#nav-count").textContent = countText(data.counts?.total);
    updateIfChanged("libraries", state.libraries, renderLibraries);
    updateIfChanged("jobs", [state.jobs, state.libraries], renderJobs);
    updateIfChanged("collections", [state.collections, state.libraries], renderCollections);
    updateIfChanged("schedules", [state.schedules, state.libraries], renderSchedules);
    if (state.view === "exports") await loadExports();
    if (state.view === "documents" && previousJobs !== JSON.stringify(state.jobs)) await loadDocuments({passive: true});
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

async function loadDocuments({offset = state.offset, limit = state.limit, focus = false, passive = false} = {}) {
  if (passive && ($("#document-dialog").open || state.documentNavigationRequest)) return;
  const request = ++state.documentRequest;
  if (focus) state.documentNavigationRequest = request;
  try {
  const params = new URLSearchParams({q: $("#document-query").value.trim(), library_id: $("#document-library").value, status: $("#document-status").value, extension: $("#document-extension").value, offset, limit});
  const data = await api(`/documents?${params}`);
  if (request !== state.documentRequest) return;
  const total = data.total || 0;
  if (offset && offset >= total) return await loadDocuments({offset: Math.max(0, Math.ceil(total / limit) - 1) * limit, limit, focus, passive});
  state.offset = offset; state.limit = limit; state.documents = data.items || []; state.documentTotal = total;
  updateIfChanged("documents", [state.documents, total, offset, limit], renderDocuments);
  if (focus) {
    const heading = $("#document-result-count"); heading.focus({preventScroll: true}); heading.scrollIntoView({block: "start", behavior: "auto"});
    $("#document-announcement").textContent = total ? `${countText(total)}件中 ${offset + 1}から${Math.min(offset + limit, total)}件を表示しました。` : "条件に合う資料はありません。";
  }
  } finally { if (state.documentNavigationRequest === request) state.documentNavigationRequest = null; }
}
function renderDocuments() {
  const root = $("#documents"), active = document.activeElement, activeRow = active?.closest("tr[data-document-id]");
  const focusKey = activeRow ? [activeRow.dataset.documentId, active.dataset.documentAction] : null;
  const scroll = window.scrollY;
  root.replaceChildren();
  $("#document-result-count").textContent = `${countText(state.documentTotal)} 件の資料`;
  $("#documents-empty").hidden = !!state.documents.length;
  for (const doc of state.documents) {
    const row = node("tr"), checkCell = node("td"), input = document.createElement("input"); row.dataset.documentId = doc.id;
    input.type = "checkbox"; input.checked = state.selected.has(doc.id); input.dataset.documentAction = "select"; input.setAttribute("aria-label", `${doc.relative_path} を選択`);
    input.addEventListener("change", () => { if (input.checked) state.selected.set(doc.id, doc); else state.selected.delete(doc.id); updateSelection(); }); checkCell.append(input);
    const nameCell = node("td"), title = button(doc.relative_path, "", () => showDocument(doc.id, title)); title.className = "doc-title-button"; title.dataset.documentAction = "title";
    nameCell.append(title, node("p", "help", libraryName(doc.library_id)));
    if (doc.snippet) nameCell.append(node("p", "document-snippet", doc.snippet));
    const statusCell = node("td"); statusCell.append(badge(doc.status));
    if (doc.excluded) statusCell.append(document.createTextNode(" "), badge("excluded"));
    if (doc.conflict) statusCell.append(document.createTextNode(" "), badge("conflict"));
    if (doc.warning_count) statusCell.append(node("p", "help", `注意事項 ${doc.warning_count} 件`));
    const dateCell = node("td", "help", dateText(doc.updated_at)), actionCell = node("td"), review = button("確認", "subtle small", () => showDocument(doc.id, review)); review.dataset.documentAction = "review"; actionCell.append(review);
    row.append(checkCell, nameCell, statusCell, dateCell, actionCell); root.append(row);
  }
  const pages = Math.max(1, Math.ceil(state.documentTotal / state.limit));
  $$('[data-page="previous"]').forEach(el => { el.disabled = state.offset === 0; });
  $$('[data-page="next"]').forEach(el => { el.disabled = state.offset + state.limit >= state.documentTotal; });
  $$(".page-info").forEach(el => { el.textContent = state.documentTotal ? `${Math.floor(state.offset / state.limit) + 1} / ${pages} ページ` : "0 / 0"; });
  $$(".page-size").forEach(el => { el.value = state.limit; });
  $$(".page-number").forEach(el => { el.max = pages; el.value = Math.floor(state.offset / state.limit) + 1; });
  updateSelection();
  if (focusKey) documentControl(...focusKey)?.focus({preventScroll: true});
  window.scrollTo({top: scroll, behavior: "instant"});
}
function documentControl(id, kind = "title") {
  return $$("#documents tr").find(row => row.dataset.documentId === String(id))?.querySelector(`[data-document-action="${kind}"]`);
}
function restoreDocumentFocus() {
  const opener = state.documentOpener;
  if (opener) (documentControl(opener.id, opener.kind) || $("#document-result-count")).focus({preventScroll: true});
}
function updateSelection() {
  $("#selection-count").textContent = state.selected.size ? `${state.selected.size} 件選択中` : "";
  $("#collection-from-selection").disabled = !state.selected.size;
  $("#select-page").checked = !!state.documents.length && state.documents.every(item => state.selected.has(item.id));
  $("#select-page").indeterminate = state.documents.some(item => state.selected.has(item.id)) && !$("#select-page").checked;
}
async function showDocument(id, opener = null) {
  if (opener) state.documentOpener = {id, kind: opener.dataset.documentAction || "title"};
  const doc = await api(`/documents/${encodeURIComponent(id)}`); state.currentDocument = doc;
  $("#document-title").textContent = doc.relative_path;
  $("#document-meta").textContent = `${libraryName(doc.library_id)} · ${stateLabels[doc.status] || doc.status} · ${dateText(doc.updated_at)}`;
  $("#document-excluded").checked = !!doc.excluded;
  $("#original-text").value = doc.original_text || ""; $("#edited-text").value = doc.edited_text ?? doc.effective_text ?? doc.original_text ?? "";
  $("#document-conflict").hidden = !doc.conflict;
  $("#history-details").open = false; $("#document-history").replaceChildren(node("p", "help", "開くと履歴を読み込みます。"));
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
  const body = {excluded: $("#document-excluded").checked, text: discard ? null : $("#edited-text").value, expected_hash: doc.source_hash, expected_revision: doc.revision};
  await api(`/documents/${encodeURIComponent(doc.id)}`, {method: "PUT", body});
  $("#document-dialog").close(); await loadDocuments(); await refresh(); restoreDocumentFocus(); toast(discard ? "修正を破棄し、原文に戻しました。" : "修正を保存しました。原本は変更していません。");
}

function collectionLibraries(collection) { return collection.library_ids?.length ? collection.library_ids : [collection.library_id].filter(Boolean); }
function renderCollections() {
  const root = $("#collections"); root.replaceChildren();
  if (!state.collections.length) { root.append(emptyState("▧", "用途に合わせて、資料をまとめる", "資料セットに対象資料・登録先・Copilotにしてほしいことを保存できます。")); return; }
  for (const collection of state.collections) {
    const card = node("article", "collection-card"); card.append(node("div", "collection-type", `${collection.target === "studio" ? "Copilot Studio" : "Agent Builder"} · ${purposeLabels[collection.purpose] || "資料セット"}`), node("h3", "", collection.name));
    card.append(node("p", "", collectionLibraries(collection).map(libraryName).join(" / ")));
    const conditions = []; if (collection.query) conditions.push(`検索：${collection.query}`); if (collection.selection_mode === "fixed" || collection.document_ids?.length) conditions.push(`個別選択：${collection.document_ids.length} 件`);
    card.append(node("p", "", conditions.join(" · ") || "条件に合う収録対象資料"));
    const actions = node("div", "button-row"); actions.append(button("ナレッジを生成", "primary", () => preflight(collection)), button("編集", "subtle", () => openCollection(collection)));
    card.append(actions); root.append(card);
  }
}
function openCollection(collection = null, fromSelection = false) {
  if (!state.libraries.length) { toast("先にホームで資料フォルダを登録してください。", true); return; }
  state.collectionId = collection?.id || null; state.collectionDraft = {...(collection || {}), excluded_document_ids: [...(collection?.excluded_document_ids || [])], unit_overrides: {...(collection?.unit_overrides || {})}, unit_override_bases: {...(collection?.unit_override_bases || {})}};
  state.collectionIds = collection?.document_ids ? [...collection.document_ids] : fromSelection ? [...state.selected.keys()] : [];
  const selectedLibraries = collection ? collectionLibraries(collection) : fromSelection ? [...new Set([...state.selected.values()].map(doc => doc.library_id))] : [$("#document-library").value || state.libraries[0].id];
  state.collectionLibraryIds = [...selectedLibraries]; state.collectionPreviewScope = null;
  $("#collection-form").reset(); $("#collection-preview").replaceChildren(); $("#collection-advanced").open = false;
  $("#collection-title").textContent = collection ? "資料セットを編集" : "資料セットを作成";
  $("#collection-name").value = collection?.name || "";
  const choices = $("#collection-libraries"); choices.replaceChildren();
  for (const lib of state.libraries) { const label = node("label", "check-label"), input = document.createElement("input"); input.type = "checkbox"; input.value = lib.id; input.checked = selectedLibraries.includes(lib.id); label.append(input, document.createTextNode(lib.name)); choices.append(label); }
  $("#collection-mode").value = collection?.selection_mode || (state.collectionIds.length ? "fixed" : "dynamic");
  $("#collection-target").value = collection?.target || (collection ? "builder" : "studio");
  $("#collection-cleanup").value = collection?.cleanup || (collection ? "none" : "standard");
  for (const key of ["folder", "query", "instructions", "description", "audience"]) $(`#collection-${key}`).value = collection?.[key] || "";
  $("#collection-answer-scope").value = collection?.answer_scope || ""; $("#collection-out-of-scope").value = collection?.out_of_scope || "";
  $("#collection-purpose").value = collection?.purpose || "overview";
  for (const key of ["hidden", "notes", "embedded"]) $(`#collection-${key}`).checked = collection?.[`include_${key}`] ?? true;
  $("#evaluation-questions").replaceChildren(); for (const item of collection?.evaluation_questions || []) addEvaluation(item);
  updateCollectionSelection(); openDialog("#collection-dialog");
}
function addEvaluation(item = {}) {
  const row = node("div", "evaluation-row");
  for (const [key, title] of [["question", "質問"], ["expected_response", "期待する回答・判定基準"], ["source", "確認する出典"]]) { const label = node("label", "", title), input = document.createElement("textarea"); input.rows = 2; input.dataset.evaluation = key; input.value = item[key] || ""; label.append(input); row.append(label); }
  row.append(button("この質問を削除", "subtle small", () => row.remove())); $("#evaluation-questions").append(row);
}
function collectionBody() {
  const ids = $$("#collection-libraries input:checked").map(el => el.value);
  if (!ids.length) throw new Error("資料フォルダを1つ以上選択してください。");
  return {...state.collectionDraft, name: $("#collection-name").value.trim(), library_id: ids[0], library_ids: ids, folder: $("#collection-folder").value.trim(), query: $("#collection-query").value.trim(), document_ids: $("#collection-mode").value === "fixed" ? [...state.collectionIds] : [], selection_mode: $("#collection-mode").value, target: $("#collection-target").value, cleanup: $("#collection-cleanup").value, purpose: $("#collection-purpose").value, instructions: $("#collection-instructions").value, include_hidden: $("#collection-hidden").checked, include_notes: $("#collection-notes").checked, include_embedded: $("#collection-embedded").checked, description: $("#collection-description").value, audience: $("#collection-audience").value, answer_scope: $("#collection-answer-scope").value, out_of_scope: $("#collection-out-of-scope").value, evaluation_questions: $$("#evaluation-questions .evaluation-row").map(row => Object.fromEntries($$("textarea", row).map(el => [el.dataset.evaluation, el.value]))).filter(item => item.question.trim())};
}
function updateCollectionSelection() {
  $("#collection-selection").value = $("#collection-mode").value === "fixed" ? `${state.collectionIds.length} 件を個別に指定` : `条件に合う資料（このセットで除外 ${state.collectionDraft?.excluded_document_ids?.length || 0} 件）`;
  $("#clear-collection-selection").hidden = !state.collectionIds.length;
}
async function previewCollection(offset = 0, scope = null) {
  const body = collectionBody(), fixed = body.selection_mode === "fixed";
  body.name ||= "対象資料の確認";
  scope ||= state.collectionPreviewScope || (fixed && state.collectionIds.length ? "selected" : "candidates");
  if (scope === "selected" && !state.collectionIds.length) scope = "candidates";
  state.collectionPreviewScope = scope;
  const previewBody = scope === "selected" ? body : {...body, selection_mode: "dynamic", document_ids: []};
  const data = await api(`/collections/preview?offset=${offset}&limit=100`, {method: "POST", body: previewBody});
  const root = $("#collection-preview"); root.replaceChildren();
  if (fixed) {
    const modes = node("div", "button-row");
    const selected = button("選択済み（削除済みを含む）", scope === "selected" ? "secondary small" : "subtle small", () => previewCollection(0, "selected")); selected.disabled = !state.collectionIds.length;
    modes.append(selected, button("追加候補を探す", scope === "candidates" ? "secondary small" : "subtle small", () => previewCollection(0, "candidates"))); root.append(modes);
  }
  root.append(node("p", "help", `${scope === "selected" ? "選択済み" : "候補"} ${countText(data.total)} 件 · 注意 ${countText(data.warning_count)} 件${data.missing ? ` · 原本削除 ${countText(data.missing)} 件` : ""}`));
  for (const doc of data.items || []) {
    const row = node("div", "candidate-row"), label = node("label", "check-label"), input = document.createElement("input"); input.type = "checkbox";
    input.checked = fixed ? state.collectionIds.includes(doc.id) : !doc.excluded && !state.collectionDraft.excluded_document_ids.includes(doc.id); input.disabled = !!doc.excluded && !fixed;
    input.addEventListener("change", () => { if ($("#collection-mode").value === "fixed") { state.collectionIds = state.collectionIds.filter(id => id !== doc.id); if (input.checked) { state.collectionIds.push(doc.id); state.collectionDraft.excluded_document_ids = state.collectionDraft.excluded_document_ids.filter(id => id !== doc.id); } } else { state.collectionDraft.excluded_document_ids = state.collectionDraft.excluded_document_ids.filter(id => id !== doc.id); if (!input.checked) state.collectionDraft.excluded_document_ids.push(doc.id); } updateCollectionSelection(); });
    const info = node("span"); info.append(node("strong", "", doc.relative_path), node("span", "help", ` ${libraryName(doc.library_id)} · ${stateLabels[doc.status] || doc.status || ""}`));
    if (doc.reason) info.append(node("span", "help", doc.reason)); if (doc.snippet) info.append(node("span", "document-snippet", doc.snippet));
    label.append(input, info); row.append(label);
    if (doc.excluded) row.append(badge("excluded", "全セットから除外中"));
    if (state.collectionId && !doc.missing) row.append(button("整理前後", "subtle small", () => showCleanup(doc.id)));
    root.append(row);
  }
  if (data.total > 100 || offset) {
    const pages = node("div", "button-row"), previous = button("← 前へ", "subtle small", () => previewCollection(Math.max(0, offset - 100), scope)), next = button("次へ →", "subtle small", () => previewCollection(offset + 100, scope));
    previous.disabled = offset === 0; next.disabled = offset + 100 >= data.total;
    pages.append(previous, node("span", "help", `${Math.floor(offset / 100) + 1} / ${Math.max(1, Math.ceil(data.total / 100))} ページ`), next); root.append(pages);
  }
  if (!state.collectionId) root.append(node("p", "help", "保存後にセットを編集すると、各資料の整理前後を確認できます。"));
}
async function changeCollectionLibraries() {
  const inputs = $$("#collection-libraries input"), before = state.collectionLibraryIds, selected = inputs.filter(el => el.checked).map(el => el.value);
  const refs = [...new Set([...state.collectionIds, ...state.collectionDraft.excluded_document_ids])];
  const submit = $("#collection-form [type=submit]"); submit.disabled = true;
  inputs.forEach(el => { el.disabled = true; });
  try {
    const discarded = new Set();
    if (refs.length) {
      const body = {...collectionBodyForLibraries(before), selection_mode: "fixed", document_ids: refs, excluded_document_ids: []};
      for (let offset = 0; ; offset += 200) {
        const data = await api(`/collections/preview?offset=${offset}&limit=200`, {method: "POST", body});
        for (const doc of data.items) if (!selected.includes(doc.library_id)) discarded.add(doc.id);
        if (offset + 200 >= data.total) break;
      }
    }
    state.collectionIds = state.collectionIds.filter(id => !discarded.has(id));
    state.collectionDraft.excluded_document_ids = state.collectionDraft.excluded_document_ids.filter(id => !discarded.has(id));
    state.collectionLibraryIds = selected; state.collectionPreviewScope = null;
    $("#collection-preview").replaceChildren(); updateCollectionSelection();
    if (discarded.size) toast(`対象から外したフォルダの ${discarded.size} 件について、個別選択・このセットでの除外指定を解除しました。`);
  } catch (error) {
    inputs.forEach(el => { el.checked = before.includes(el.value); }); throw error;
  } finally { inputs.forEach(el => { el.disabled = false; }); submit.disabled = false; }
}
function collectionBodyForLibraries(ids) {
  // 解除前の登録元で参照IDを調べる。プレビューだけなので設定は保存しない。
  return {...state.collectionDraft, name: $("#collection-name").value.trim() || "対象資料の確認", library_id: ids[0], library_ids: ids, purpose: $("#collection-purpose").value};
}
async function showCleanup(documentId) {
  state.cleanupDocumentId = documentId;
  const data = await api(`/collections/${encodeURIComponent(state.collectionId)}/preview-document`, {method: "POST", body: {document_id: documentId, options: collectionBody()}});
  $("#cleanup-before").value = data.original_text || ""; $("#cleanup-after").value = data.text || "";
  $("#cleanup-summary").textContent = `${countText(data.before_chars)} 文字 → ${countText(data.after_chars)} 文字。設定の変更は資料セットを保存すると反映されます。`;
  const changes = $("#cleanup-changes"); changes.replaceChildren(); for (const change of data.changes || []) changes.append(node("div", "", typeof change === "string" ? change : change.detail || change.kind));
  const root = $("#cleanup-units"); root.replaceChildren(); const available = new Set();
  for (const unit of data.raw_units || data.units || []) {
    const key = unit.key || unit.unit_key || `${documentId}:${unit.unit_id}`, row = node("div", "unit-choice"), label = node("label", "", unit.locator || "本文"), select = document.createElement("select"); select.dataset.unitKey = key; available.add(key);
    select.overrideBasis = unit.override_basis;
    for (const [value, text] of [["", "設定に従う"], ["include", "必ず含める"], ["exclude", "このセットから除外"]]) { const option = node("option", "", text); option.value = value; select.append(option); }
    select.value = state.collectionDraft.unit_overrides[key] || "";
    select.addEventListener("change", () => { select.dataset.confirmed = "true"; });
    label.append(select); row.append(label, node("p", "document-snippet", unit.text || "本文なし"));
    if (unit.confirmation_pending) {
      const message = node("p", "help", "原本更新のため確認が必要です。現在は原文を保持しています。");
      row.append(message, button("採否を再確認", "secondary small", () => { select.dataset.confirmed = "true"; message.textContent = "再確認しました。資料セットを保存すると反映されます。"; }));
    }
    root.append(row);
  }
  const missing = new Set((data.changes || []).filter(change => change.kind === "override_confirmation_required").flatMap(change => change.unit_ids || []).filter(key => !available.has(key)));
  for (const key of missing) {
    const row = node("div", "unit-choice"), message = node("p", "help", `原本から見つからない指定：${key}`), remove = button("旧指定を解除", "subtle small", () => { remove.dataset.remove = "true"; message.textContent = "この旧指定は資料セットの保存時に解除します。"; });
    remove.dataset.overrideKey = key; row.append(message, remove); root.append(row);
  }
  openDialog("#cleanup-dialog");
}
async function preflight(collection) {
  const data = await api(`/collections/${encodeURIComponent(collection.id)}/preflight`); state.preflightId = collection.id;
  $("#preflight-summary").textContent = `${collection.name} · 対象 ${countText(data.total)} 件 · 収録候補 ${countText(data.included)} 件 · 注意 ${countText(data.issues)} 件 · 原本更新 ${countText(data.stale)} 件`;
  const root = $("#preflight-files"); root.replaceChildren();
  for (const file of data.files || []) { const row = node("div", "candidate-row"); row.append(node("strong", "", file.relative_path || file.name || file.source || file.path || "資料"), node("span", "help", file.reason || stateLabels[file.status] || file.status || "")); root.append(row); }
  openDialog("#preflight-dialog");
}
async function showHandoff(id) {
  const data = await api(`/exports/${encodeURIComponent(id)}/handoff`); state.handoffId = id;
  $("#handoff-summary").textContent = `${data.target === "studio" ? "Copilot Studio" : "Agent Builder"} · ナレッジ ${countText(data.knowledge_files?.length)} ファイル · 追加・変更 ${countText(data.changed?.length)} 件`;
  const root = $("#handoff-files"); root.replaceChildren();
  for (const file of data.knowledge_files || []) { const path = typeof file === "string" ? file : file.path, label = node("label", "check-label"), input = document.createElement("input"); input.type = "checkbox"; input.value = path; label.append(input, document.createTextNode(path), badge((data.changed || []).includes(path) ? "partial" : "ok", (data.changed || []).includes(path) ? "追加・変更" : "登録記録と一致")); root.append(label); }
  const removed = $("#handoff-removed"); removed.replaceChildren();
  if (data.removed?.length) removed.append(node("h3", "", "Copilot側で削除を確認した旧ファイル"));
  for (const file of data.removed || []) { const path = typeof file === "string" ? file : file.path, label = node("label", "check-label"), input = document.createElement("input"); input.type = "checkbox"; input.value = path; label.append(input, document.createTextNode(path)); removed.append(label); }
  openDialog("#handoff-dialog");
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
    info.append(title, node("p", "help", `${dateText(item.created_at)} · ${countText(item.document_count)} 資料 · ${item.file_count != null ? `ナレッジ ${countText(item.file_count)} ファイル` : `${countText(item.chunk_count)} 分割`}`));
    if (item.reason) info.append(node("p", "export-reason", item.reason));
    const actions = node("div", "button-row");
    if (!["failed", "building", "generating"].includes(item.state)) {
      const download = node("a", "button secondary small", "一式をダウンロード"); download.href = `/api/exports/${encodeURIComponent(item.id)}/download`; download.setAttribute("download", ""); actions.append(download);
      actions.append(button("登録状況", "secondary small", () => showHandoff(item.id)));
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
  for (const collection of state.collections.filter(item => collectionLibraries(item).length === 1 && String(collectionLibraries(item)[0]) === $("#schedule-library").value)) { const option = node("option", "", collection.name); option.value = collection.id; select.append(option); }
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
$("#search-form").addEventListener("submit", event => { event.preventDefault(); action($("#search-form [type=submit]"), () => loadDocuments({offset: 0, focus: true})); });
for (const selector of ["#document-library", "#document-status", "#document-extension"]) $(selector).addEventListener("change", () => action(null, () => loadDocuments({offset: 0, focus: true})));
$$("[data-page]").forEach(element => element.addEventListener("click", () => action(element, () => loadDocuments({offset: Math.max(0, state.offset + (element.dataset.page === "next" ? state.limit : -state.limit)), focus: true}))));
$$(".page-size").forEach(element => element.addEventListener("change", () => action(null, async () => { const limit = Number(element.value); try { await loadDocuments({offset: 0, limit, focus: true}); } catch (error) { element.value = state.limit; throw error; } })));
$$(".page-jump").forEach(form => form.addEventListener("submit", event => { event.preventDefault(); action($("button", form), () => loadDocuments({offset: (Number($("input", form).value) - 1) * state.limit, focus: true})); }));
$("#select-page").addEventListener("change", event => { for (const doc of state.documents) { if (event.target.checked) state.selected.set(doc.id, doc); else state.selected.delete(doc.id); } $$("#documents input[type=checkbox]").forEach(input => { input.checked = event.target.checked; }); updateSelection(); });
$("#document-dialog").addEventListener("close", restoreDocumentFocus);
window.addEventListener("beforeunload", event => { if ($("#document-dialog").open && documentIsDirty()) { event.preventDefault(); event.returnValue = ""; } });
$("#reextract-document").addEventListener("click", event => action(event.currentTarget, async () => {
  if (documentIsDirty() && !confirm("未保存の変更があります。変更を破棄して再読み取りしますか？")) return;
  await api(`/documents/${encodeURIComponent(state.currentDocument.id)}/reextract`, {method: "POST", body: {}}); $("#document-dialog").close(); await refresh(); toast("この資料の再読み取りを開始しました。完了後にもう一度開いてください。");
}));
$("#history-details").addEventListener("toggle", () => { if (!$("#history-details").open) return; action(null, async () => {
  const id = state.currentDocument.id, data = await api(`/documents/${encodeURIComponent(id)}/history`); if (state.currentDocument?.id !== id) return;
  const root = $("#document-history"); root.replaceChildren();
  for (const item of data) { const row = node("div", "history-row"); row.append(node("strong", "", `${dateText(item.created_at)} · 修正版 ${item.revision}`), node("p", "document-snippet", item.edited_text ?? "読み取り原文を使用")); row.append(button("この本文を復元", "subtle small", async () => {
    if (!confirm("この履歴の本文を現在の修正として保存しますか？未保存の入力は置き換わります。")) return;
    await api(`/documents/${encodeURIComponent(id)}`, {method: "PUT", body: {text: item.edited_text, expected_hash: state.currentDocument.source_hash, expected_revision: state.currentDocument.revision}}); await showDocument(id); toast("履歴の本文を復元しました。");
  })); root.append(row); }
  if (!data.length) root.append(node("p", "help", "本文修正の履歴はまだありません。"));
}); });
function setFontSize(value) { document.documentElement.dataset.fontSize = value === "large" ? "large" : "standard"; $("#font-size").value = document.documentElement.dataset.fontSize; }
try { setFontSize(localStorage.getItem("contextgen-font-size") || "standard"); } catch { setFontSize("standard"); }
$("#font-size").addEventListener("change", event => { setFontSize(event.target.value); try { localStorage.setItem("contextgen-font-size", event.target.value); } catch { /* 保存不可でも現在の表示には反映する。 */ } });
$("#save-document").addEventListener("click", event => action(event.currentTarget, () => saveDocument(false)));
$("#discard-edits").addEventListener("click", event => action(event.currentTarget, () => saveDocument(true)));
$("#open-original").addEventListener("click", event => action(event.currentTarget, async () => { await api(`/documents/${encodeURIComponent(state.currentDocument.id)}/open`, {method: "POST", body: {}}); toast("原本を開きました。"); }));
$("#add-collection").addEventListener("click", () => openCollection());
$("#collection-from-selection").addEventListener("click", () => openCollection(null, true));
$("#clear-collection-selection").addEventListener("click", () => { state.collectionIds = []; updateCollectionSelection(); });
$("#collection-mode").addEventListener("change", () => { state.collectionPreviewScope = null; updateCollectionSelection(); $("#collection-preview").replaceChildren(); });
$("#collection-libraries").addEventListener("change", () => action($("#preview-collection"), changeCollectionLibraries));
$("#preview-collection").addEventListener("click", event => action(event.currentTarget, () => previewCollection()));
$("#add-evaluation").addEventListener("click", () => addEvaluation());
$("#collection-form").addEventListener("submit", event => { event.preventDefault(); action($("#collection-form [type=submit]"), async () => {
  const body = collectionBody(); if (body.selection_mode === "fixed" && !body.document_ids.length) throw new Error("固定する資料を1件以上選んでください。『対象資料を確認』から選べます。");
  await api(state.collectionId ? `/collections/${encodeURIComponent(state.collectionId)}` : "/collections", {method: state.collectionId ? "PUT" : "POST", body}); $("#collection-dialog").close(); await refresh(); await switchView("exports"); toast("資料セットを保存しました。");
}); });
$("#save-unit-overrides").addEventListener("click", event => action(event.currentTarget, async () => {
  for (const select of $$("#cleanup-units select")) {
    const key = select.dataset.unitKey;
    if (select.value) { state.collectionDraft.unit_overrides[key] = select.value; if (select.dataset.confirmed === "true" && select.overrideBasis) state.collectionDraft.unit_override_bases[key] = select.overrideBasis; }
    else { delete state.collectionDraft.unit_overrides[key]; delete state.collectionDraft.unit_override_bases[key]; }
  }
  for (const item of $$('#cleanup-units [data-remove="true"]')) { delete state.collectionDraft.unit_overrides[item.dataset.overrideKey]; delete state.collectionDraft.unit_override_bases[item.dataset.overrideKey]; }
  await api(`/collections/${encodeURIComponent(state.collectionId)}`, {method: "PUT", body: collectionBody()}); await showCleanup(state.cleanupDocumentId); toast("ページ・シートごとの採否を資料セットに保存しました。");
}));
$("#confirm-export").addEventListener("click", event => action(event.currentTarget, async () => {
  await api("/exports", {method: "POST", body: {collection_id: state.preflightId, force: false, refresh_sources: true}}); $("#preflight-dialog").close(); await refresh(); await loadExports(); toast("原本の確認とナレッジの生成を開始しました。");
}));
$("#handoff-select-all").addEventListener("click", () => $$("#handoff-files input").forEach(input => { input.checked = true; }));
$("#handoff-select-none").addEventListener("click", () => $$("#handoff-files input").forEach(input => { input.checked = false; }));
$("#save-handoff").addEventListener("click", event => action(event.currentTarget, async () => {
  const files = $$("#handoff-files input:checked").map(input => input.value), removed = $$("#handoff-removed input:checked").map(input => input.value);
  if (!files.length && !removed.length) throw new Error("実際に登録・削除したファイルを選んでください。");
  await api(`/exports/${encodeURIComponent(state.handoffId)}/handoff`, {method: "POST", body: {files, removed}}); $("#handoff-dialog").close(); toast("Copilot側で実施した登録・削除を記録しました。");
}));
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
