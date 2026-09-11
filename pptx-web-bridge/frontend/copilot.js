/**
 * 「Copilot に頼む」モーダル（API は使わない）。
 * 1. 渡す: 用途プリセットを選び、/api/copilot/handoff で指示と資料の内容（Markdown / JSON）を受け取り、コピー・Word 保存・ZIP 保存・Copilot を開く
 * 2. 回答を反映: Copilot の回答（Markdown / 簡易 JSON）を貼り付け、/api/copilot/import で新しい資料にするか、ノートへ入れる
 */
window.PWB = window.PWB || {};
PWB.copilot = (function () {
  "use strict";
  var modal = null;
  var st = { purposes: [], chatUrl: "", built: null, tab: "ask", agent: null };
  var $ = function (id) { return document.getElementById(id); };
  var core = function () { return PWB.core; };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var OPTION_LABELS = { count: "枚数", language: "言語" };

  function init(el) {
    modal = el;
    modal.addEventListener("click", onClick);
    modal.addEventListener("change", onChange);
    modal.addEventListener("input", function (e) { if (e.target.id === "copilot-instruction" && st.built) st.built.instruction = e.target.value; });
    document.addEventListener("keydown", function (e) { if (!modal.hidden && e.key === "Escape") close(); });
    core().apiJson("/api/copilot/prompts").then(function (r) {
      st.purposes = r.purposes || []; st.chatUrl = r.chat_url || "";
      var sel = $("copilot-purpose");
      sel.innerHTML = "";
      st.purposes.forEach(function (p) { var o = document.createElement("option"); o.value = p.id; o.textContent = p.name; sel.appendChild(o); });
    }).catch(function (e) { core().log("Copilot プリセット取得失敗: " + e.message, "ERROR"); });
  }

  function open(tab) {
    modal.hidden = false;
    setTab(tab || "ask");
    if (st.tab === "ask") build();
  }
  function close() { modal.hidden = true; }
  function setStatus(msg, isErr) { var s = $("copilot-status"); s.textContent = msg || ""; s.classList.toggle("err", !!isErr); if (isErr) core().log("Copilot 連携: " + msg, "ERROR"); }
  function setTab(tab) {
    st.tab = tab;
    modal.querySelectorAll("[data-copilot-tab]").forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-copilot-tab") === tab); });
    $("copilot-ask-side").hidden = tab !== "ask"; $("copilot-ask-main").hidden = tab !== "ask";
    $("copilot-reply-side").hidden = tab !== "reply"; $("copilot-reply-main").hidden = tab !== "reply";
    $("copilot-agent-side").hidden = tab !== "agent"; $("copilot-agent-main").hidden = tab !== "agent";
    if (tab === "reply") setTimeout(function () { $("copilot-reply").focus(); }, 0);
    if (tab === "agent" && !st.agent) loadAgent();
  }
  function currentPurpose() { var id = $("copilot-purpose").value; for (var i = 0; i < st.purposes.length; i++) if (st.purposes[i].id === id) return st.purposes[i]; return st.purposes[0] || null; }
  function options() {
    var out = {};
    modal.querySelectorAll("#copilot-options [data-copilot-opt]").forEach(function (inp) { var v = inp.value; out[inp.getAttribute("data-copilot-opt")] = inp.type === "number" ? parseInt(v, 10) || 0 : v; });
    return out;
  }
  function renderOptions() {
    var p = currentPurpose();
    var box = $("copilot-options");
    box.innerHTML = "";
    $("copilot-purpose-desc").textContent = p ? (p.description || "") : "";
    $("copilot-attach-hint").textContent = p && p.attach_hint ? p.attach_hint : "";
    if (!p || !p.options) return;
    Object.keys(p.options).forEach(function (k) {
      var v = p.options[k];
      var lab = document.createElement("label");
      lab.className = "f";
      lab.innerHTML = "<span>" + esc(OPTION_LABELS[k] || k) + "</span>" + (typeof v === "number" ? '<input type="number" min="1" max="60" data-copilot-opt="' + esc(k) + '" value="' + v + '">' : '<input type="text" data-copilot-opt="' + esc(k) + '" value="' + esc(v) + '">');
      box.appendChild(lab);
    });
  }

  function build() {
    var pres = core().state.presentation;
    if (!pres) { setStatus("先にファイルを投入してください。", true); return; }
    if (!$("copilot-options").children.length && !$("copilot-purpose-desc").textContent) renderOptions();
    var p = currentPurpose();
    setStatus("作成中 …");
    core().apiJson("/api/copilot/handoff", core().currentBody({ purpose: p ? p.id : null, options: options() })).then(function (r) {
      st.built = r;
      $("copilot-instruction").value = r.instruction;
      $("copilot-content").value = r.content;
      $("copilot-chars").textContent = r.chars.toLocaleString() + " 文字" + (r.truncated ? "、長いため省略あり: Word 文書を添付してください" : "");
      $("copilot-attach-hint").textContent = r.attach_hint || "";
      setStatus("「全部コピー」で Copilot に貼れます。");
    }).catch(function (e) { setStatus("作成失敗: " + e.message, true); });
  }

  function copyText(text, label) {
    var done = function () { setStatus(label + "をコピーしました。Copilot に貼り付けてください。"); };
    var fail = function () {
      // クリップボード API が使えない環境: textarea を選択状態にして execCommand
      try { var ta = $("copilot-content"); ta.value = text; ta.select(); document.execCommand("copy"); done(); } catch (e) { setStatus("コピーできませんでした。テキストを選択して手動でコピーしてください。", true); }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fail); else fail();
  }
  function fullPrompt() { if (!st.built) return ""; return $("copilot-instruction").value.replace(/\n+$/, "") + "\n" + st.built.content; }

  function download(path, filename) {
    var p = currentPurpose();
    core().api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(core().currentBody({ purpose: p ? p.id : null, options: options(), name: document.getElementById("project-name").value })) })
      .then(function (r) { return r.blob(); })
      .then(function (blob) { var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click(); a.remove(); setStatus(filename + " を保存しました。"); })
      .catch(function (e) { setStatus("保存失敗: " + e.message, true); });
  }

  function templateId() { var el = document.getElementById("template-select"); return el ? el.value : null; }

  function loadAgent() {
    setStatus("エージェント一式を作成中 …");
    core().apiJson("/api/copilot/agent-kit/preview?template_id=" + encodeURIComponent(templateId() || "")).then(function (r) {
      st.agent = r;
      $("copilot-agent-instructions").value = r.instructions || "";
      if (!$("copilot-agent-name").value) $("copilot-agent-name").value = r.agent.name || "";
      if (!$("copilot-agent-desc").value) $("copilot-agent-desc").value = r.agent.description || "";
      var box = $("copilot-agent-files");
      box.innerHTML = "<p class=\"muted\">ナレッジ " + r.files.length + " ファイル</p>" + r.files.map(function (f) { return '<p class="muted">' + esc(f.name) + "（" + f.chars.toLocaleString() + " 文字）</p>"; }).join("");
      setStatus("「一式を ZIP で保存」で書き出せます。");
    }).catch(function (e) { setStatus("作成失敗: " + e.message, true); });
  }

  function downloadAgent() {
    var body = { template_id: templateId(), agent_name: $("copilot-agent-name").value || null, description: $("copilot-agent-desc").value || null };
    core().api("/api/copilot/agent-kit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.blob(); })
      .then(function (blob) { var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "copilot_agent.zip"; document.body.appendChild(a); a.click(); a.remove(); setStatus("copilot_agent.zip を保存しました。"); })
      .catch(function (e) { setStatus("保存失敗: " + e.message, true); });
  }

  function applyReply() {
    var text = $("copilot-reply").value;
    if (!text.trim()) { setStatus("回答を貼り付けてください。", true); return; }
    var mode = $("copilot-apply").value;
    var body = { text: text, apply: mode, template_id: document.getElementById("template-select").value };
    if (mode === "notes") { if (!core().state.presentation) { setStatus("ノートを入れる資料がありません。", true); return; } body.presentation = core().state.presentation; }
    setStatus("反映中 …");
    core().apiJson("/api/copilot/import", body).then(function (r) {
      var before = core().state.presentation ? core().snapshot() : null;
      if (mode === "notes") {
        if (before) PWB.history.push(before);
        core().applyImport(r, "Copilot の回答（ノート " + r.applied + " 件）", true);
      } else {
        core().applyImport(r, "Copilot の回答");
      }
      setStatus(mode === "notes" ? "ノートを " + r.applied + " 件入れました。" : "新しい資料として取り込みました（" + r.presentation.slides.length + " 枚）。");
      close();
    }).catch(function (e) { setStatus("反映失敗: " + e.message, true); });
  }

  function onClick(e) {
    var t = e.target;
    var act = t.closest("[data-copilot-act]");
    if (act) {
      var a = act.getAttribute("data-copilot-act");
      if (a === "close") close();
      else if (a === "copy-all") copyText(fullPrompt(), "指示と内容");
      else if (a === "copy-instruction") copyText($("copilot-instruction").value, "指示");
      else if (a === "copy-content") copyText(st.built ? st.built.content : "", "内容");
      else if (a === "download-docx") download("/api/copilot/docx", "outline.docx");
      else if (a === "download-zip") download("/api/copilot/handoff.zip", "copilot.zip");
      else if (a === "open-chat") { if (st.chatUrl) window.open(st.chatUrl, "_blank", "noopener"); }
      else if (a === "download-agent") downloadAgent();
      else if (a === "copy-instructions") copyText($("copilot-agent-instructions").value, "指示文");
      else if (a === "apply") applyReply();
      else if (a === "clear-reply") $("copilot-reply").value = "";
      return;
    }
    var tab = t.closest("[data-copilot-tab]");
    if (tab) { setTab(tab.getAttribute("data-copilot-tab")); if (st.tab === "ask" && !st.built) build(); return; }
    if (t === modal) close();
  }
  function onChange(e) {
    if (e.target.id === "copilot-purpose") { renderOptions(); build(); return; }
    if (e.target.hasAttribute("data-copilot-opt")) build();
  }

  return { init: init, open: open, close: close, state: function () { return st; }, build: build, fullPrompt: fullPrompt, loadAgent: loadAgent };
})();
