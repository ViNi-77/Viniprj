/**
 * 「PPTX からテンプレート作成」モーダル。
 * 1. PowerPoint（表紙・中身・最終ページ）を /api/templates/from-pptx に送り、部品の提案（proposal）とプレビュー断片を受け取る
 * 2. 表紙 / 中身 / 最終 のタブでプレビューを表示し、canvas.js（テンプレート用アダプタ）で番号付きの枠をドラッグして座標を直す
 * 3. 直すたびに /api/templates/preview で描き直し、保存は PUT /api/templates/{id}
 */
window.PWB = window.PWB || {};
PWB.templateEditor = (function () {
  "use strict";
  var modal = null, canvas = null;
  var st = { file: null, proposal: null, parts: [], slides: [], previews: {}, thumbs: [], canvas: { width_pt: 960, height_pt: 540 }, themeCss: "", tab: "cover", warnings: [], previousId: null, roles: {} };
  var previewTimer = null;
  var ROLE_LABELS = [["cover", "表紙"], ["content", "中身"], ["closing", "最終ページ"], ["skip", "使わない"]];
  var TAB_LABELS = { cover: "表紙", content: "中身", closing: "最終ページ" };
  var $ = function (id) { return document.getElementById(id); };
  var core = function () { return PWB.core; };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };

  function partId(p) { return p.part + ":" + p.key; }
  function currentParts() { return st.parts.filter(function (p) { return p.part === st.tab; }); }

  /** 提案の中の部品（key = "logo" / "images.0" / "title" …）を返す。 */
  function partSpec(kind, key) {
    var part = st.proposal && st.proposal[kind];
    if (!part) return null;
    if (key.indexOf(".") >= 0) { var k = key.split("."); return (part[k[0]] || [])[parseInt(k[1], 10)] || null; }
    return part[key] || null;
  }
  function setPartBox(kind, key, box) {
    var spec = partSpec(kind, key);
    if (!spec) return;
    ["x", "y", "w", "h"].forEach(function (c) { if (box[c] == null) return; if (key === "logo" && c === "h") return; spec[c] = Math.round(box[c] * 10) / 10; });
    st.parts.forEach(function (p) { if (p.part === kind && p.key === key && p.box) ["x", "y", "w", "h"].forEach(function (c) { if (box[c] != null) p.box[c] = Math.round(box[c] * 10) / 10; }); });
  }
  function removePart(kind, key) {
    var part = st.proposal && st.proposal[kind];
    if (!part) return;
    if (key.indexOf(".") >= 0) { var k = key.split("."); if (part[k[0]]) part[k[0]].splice(parseInt(k[1], 10), 1); }
    else { delete part[key]; if (key === "background_image") delete part.background_source; }
  }

  var adapter = {
    items: function () { return currentParts().filter(function (p) { return p.box; }).map(function (p) { return { id: partId(p), bbox: p.box, no: p.no, label: p.label, type: p.type }; }); },
    snapshot: function () { return null; },
    commit: function (boxes) {
      Object.keys(boxes).forEach(function (id) { var key = id.split(":").slice(1).join(":"); setPartBox(st.tab, key, boxes[id]); });
      renderParts();
      schedulePreview();
    },
    onSelectionChanged: function (ids) { modal.querySelectorAll(".tpl-part").forEach(function (li) { li.classList.toggle("selected", ids.indexOf(li.getAttribute("data-part")) >= 0); }); },
    onDelete: function (ids) {
      if (!ids.length) return;
      ids.forEach(function (id) { removePart(st.tab, id.split(":").slice(1).join(":")); });
      canvas.setSelection([]);
      refreshPreview();
    },
    margin: function () { return 36; },
    isActive: function () { return modal && !modal.hidden; },
    showAll: true,
    labelOf: function (it) { return it.no + " " + it.label; }
  };

  function init(el) {
    modal = el;
    canvas = PWB.canvas.create(adapter);
    canvas.init($("tpl-canvas"));
    modal.addEventListener("click", onClick);
    modal.addEventListener("change", onChange);
    document.addEventListener("keydown", function (e) { if (!modal.hidden && e.key === "Escape" && !canvas.getSelection().length) close(); });
  }

  function open() {
    modal.hidden = false;
    if (!st.proposal) { $("tpl-slides").innerHTML = ""; $("tpl-parts").innerHTML = ""; setStatus("PowerPoint ファイルを選んでください。"); }
    setTimeout(function () { canvas.fit(); }, 0);
  }
  function close() { modal.hidden = true; }
  function setStatus(msg, isErr) { var s = $("tpl-status"); s.textContent = msg || ""; s.classList.toggle("err", !!isErr); if (isErr) core().log("テンプレート作成: " + msg, "ERROR"); }

  // ---------------------------------------------------------------- 解析
  function analyze(file) {
    st.file = file;
    var fd = new FormData();
    fd.append("file", file);
    if (Object.keys(st.roles).length) fd.append("roles", JSON.stringify(st.roles));
    if (st.proposal && st.proposal.id) fd.append("template_id", st.proposal.id);
    if ($("tpl-name").value.trim()) fd.append("name", $("tpl-name").value.trim());
    fd.append("thumbs", st.thumbs.length ? "false" : "true");
    setStatus("解析中: " + file.name + " …");
    core().api("/api/templates/from-pptx", { method: "POST", body: fd }).then(function (r) { return r.json(); }).then(function (r) {
      st.proposal = r.proposal; st.parts = r.parts; st.slides = r.slides; st.previews = r.previews; st.canvas = r.canvas; st.themeCss = r.theme_css; st.warnings = r.warnings || [];
      if (r.thumbs && r.thumbs.length) st.thumbs = r.thumbs;
      st.previousId = r.proposal.id;
      $("tpl-name").value = r.proposal.name || "";
      $("tpl-id").value = r.proposal.id || "";
      renderSlides(); renderSwatches(); renderWarnings(); renderTab();
      setStatus("解釈を確認してください（" + st.parts.length + " 個の部品）");
    }).catch(function (e) { setStatus("解析失敗: " + e.message, true); });
  }

  function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(refreshPreview, 250); }
  function refreshPreview() {
    if (!st.proposal) return;
    var sel = canvas.getSelection();
    core().apiJson("/api/templates/preview", { template: st.proposal }).then(function (r) {
      st.previews = r.previews; st.parts = r.parts; st.themeCss = r.theme_css;
      renderTab(sel);
    }).catch(function (e) { setStatus("プレビュー失敗: " + e.message, true); });
  }

  // ---------------------------------------------------------------- 描画
  function renderSlides() {
    var box = $("tpl-slides");
    box.innerHTML = "";
    var ch = st.canvas.height_pt || 540, cw = st.canvas.width_pt || 960;
    var scale = 96 / cw;
    st.slides.forEach(function (s) {
      var div = document.createElement("div");
      div.className = "tpl-slide";
      var thumb = st.thumbs[s.index] || "";
      var opts = ROLE_LABELS.map(function (r) { return '<option value="' + r[0] + '"' + (r[0] === s.role ? " selected" : "") + ">" + r[1] + "</option>"; }).join("");
      div.innerHTML = '<div class="thumb" style="height:' + Math.round(ch * scale) + 'px"><div class="thumb-inner" style="transform:scale(' + scale + ')">' + thumb + "</div></div>" +
        '<div class="col"><span>' + (s.index + 1) + '. ' + esc(s.title || "（文字なし）") + '</span><select data-tpl-role="' + s.index + '">' + opts + "</select></div>";
      box.appendChild(div);
    });
  }
  function renderSwatches() {
    var box = $("tpl-swatches");
    box.innerHTML = "";
    var colors = (st.proposal && st.proposal.colors) || {};
    Object.keys(colors).forEach(function (k) { var d = document.createElement("span"); d.className = "swatch"; d.style.background = colors[k]; d.title = k + " " + colors[k]; box.appendChild(d); });
  }
  function renderWarnings() {
    var ul = $("tpl-warnings");
    ul.innerHTML = "";
    st.warnings.forEach(function (w) { var li = document.createElement("li"); li.textContent = w; ul.appendChild(li); });
  }
  function renderTab(keepSelection) {
    modal.querySelectorAll("[data-tpl-tab]").forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-tpl-tab") === st.tab); });
    var html = st.previews[st.tab];
    if (html) canvas.mount(html, st.canvas.width_pt, st.canvas.height_pt, st.themeCss);
    else { canvas.clear(); }
    renderParts();
    canvas.setSelection(keepSelection || []);
  }
  function renderParts() {
    var box = $("tpl-parts");
    var parts = currentParts();
    if (!st.proposal) { box.innerHTML = ""; return; }
    if (!st.proposal[st.tab]) { box.innerHTML = '<p class="muted">' + TAB_LABELS[st.tab] + 'に該当するスライドがありません。左の役割を変えると作れます。</p>'; return; }
    var sel = canvas.getSelection();
    var html = "";
    parts.forEach(function (p) {
      var id = partId(p);
      var src = p.source === "slide" ? "スライド" : (p.source === "layout" ? "レイアウト" : (p.source === "master" ? "マスター" : p.source));
      var detail = p.type === "text" && p.text ? ' 「' + esc(p.text) + '」' : "";
      if (p.type === "text" && p.size_pt) detail += " " + p.size_pt + "pt";
      html += '<div class="tpl-part' + (sel.indexOf(id) >= 0 ? " selected" : "") + '" data-part="' + esc(id) + '"><span class="no">' + p.no + '</span><span>' + esc(p.label) + detail + ' <span class="src">(' + src + (p.color ? " " + esc(p.color) : "") + ')</span></span><button class="small secondary" data-tpl-remove="' + esc(id) + '" title="この部品を使わない">✕</button></div>';
      if (p.box && sel.indexOf(id) >= 0) {
        html += '<div class="tpl-part-edit">' + ["x", "y", "w", "h"].map(function (c) { return '<label class="f"><span>' + c + '</span><input type="number" step="1" data-tpl-box="' + c + '" data-part="' + esc(id) + '" value="' + Math.round(p.box[c]) + '"' + (p.key === "logo" && c === "h" ? " disabled" : "") + "></label>"; }).join("") + "</div>";
      }
    });
    box.innerHTML = html || '<p class="muted">部品はありません。</p>';
  }

  // ---------------------------------------------------------------- 操作
  function onClick(e) {
    var t = e.target;
    var act = t.closest("[data-tpl-act]");
    if (act) { var a = act.getAttribute("data-tpl-act"); if (a === "close") close(); else if (a === "save") save(); return; }
    var tab = t.closest("[data-tpl-tab]");
    if (tab) { st.tab = tab.getAttribute("data-tpl-tab"); canvas.setSelection([]); renderTab(); return; }
    var rm = t.closest("[data-tpl-remove]");
    if (rm) { var id = rm.getAttribute("data-tpl-remove"); removePart(st.tab, id.split(":").slice(1).join(":")); canvas.setSelection([]); refreshPreview(); return; }
    var row = t.closest(".tpl-part");
    if (row) { canvas.setSelection([row.getAttribute("data-part")]); renderParts(); return; }
    if (t === modal) close();
  }
  function onChange(e) {
    var t = e.target;
    if (t.id === "tpl-file") { if (t.files[0]) { st.roles = {}; st.thumbs = []; st.proposal = null; analyze(t.files[0]); } return; }
    if (t.hasAttribute("data-tpl-role")) { st.roles[t.getAttribute("data-tpl-role")] = t.value; if (st.file) analyze(st.file); return; }
    if (t.hasAttribute("data-tpl-box")) {
      var id = t.getAttribute("data-part"), c = t.getAttribute("data-tpl-box");
      var box = {}; box[c] = parseFloat(t.value);
      if (isNaN(box[c])) return;
      setPartBox(st.tab, id.split(":").slice(1).join(":"), box);
      canvas.refreshSelection();
      schedulePreview();
      return;
    }
    if (t.id === "tpl-name" && st.proposal) { st.proposal.name = t.value.trim(); return; }
  }

  function save() {
    if (!st.proposal) { setStatus("先に PowerPoint ファイルを選んでください。", true); return; }
    var id = ($("tpl-id").value || st.proposal.id || "").trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
    if (!id) { setStatus("ID を入力してください。", true); return; }
    st.proposal.name = $("tpl-name").value.trim() || st.proposal.name || id;
    var body = { template: st.proposal, previous_id: st.previousId !== id ? st.previousId : null };
    setStatus("保存中 …");
    core().api("/api/templates/" + encodeURIComponent(id), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(function (r) { return r.json(); }).then(function (r) {
      st.previousId = r.template.id; st.proposal.id = r.template.id; $("tpl-id").value = r.template.id;
      core().setTemplates(r.templates, r.template.id);
      core().setStatus("テンプレートを保存しました: " + r.template.name);
      close();
      PWB.slidelist.clearThumbs();
      core().scheduleRender();
    }).catch(function (e) { setStatus("保存失敗: " + e.message, true); });
  }

  return { init: init, open: open, close: close, state: function () { return st; }, analyzeFile: analyze, canvas: function () { return canvas; } };
})();
