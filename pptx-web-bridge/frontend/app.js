/**
 * アプリ UI ロジック（MVP: 素の JavaScript）。
 *
 * 設計基準の反映:
 * - 状態は state.presentation（Presentation JSON）1 つに集約し、編集は必ずここを書き換えてから描画する。
 * - 座標計算・ファイル生成はすべてローカル API に任せ、ブラウザ側では行わない。
 * - ボタン操作はドキュメントレベルのイベント委譲（data-action 属性）で受ける（設計基準 3.3）。
 * - 進捗バーは大ステップ表記 + 累積％ + タイマー補間 + 完了時サクセス表示（設計基準 3.1）。
 * - デバッグ用に window.qcDebug を常備し、ログレベルを実行時に切り替えられる（設計基準 7）。
 */
(function () {
  "use strict";

  /** @type {{presentation: object|null, selectedSlide: number, config: object|null, warnings: object[], quality: object|null, report: object|null}} グローバル状態 */
  var state = { presentation: null, selectedSlide: 0, config: null, warnings: [], quality: null, report: null };
  var LS_KEY = "pptx_web_bridge.autosave";
  var LOG_LEVELS = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40 };
  var logLevel = "INFO";
  var $ = function (id) { return document.getElementById(id); };

  // ---------------------------------------------------------------------
  // ログ・状態表示
  // ---------------------------------------------------------------------
  /**
   * 画面のログタブとコンソールへ出力する。
   * @param {string} msg メッセージ
   * @param {"DEBUG"|"INFO"|"WARNING"|"ERROR"} [level] ログレベル
   */
  function log(msg, level) {
    level = (level || "INFO").toUpperCase();
    if (level === "WARN") level = "WARNING";
    if (LOG_LEVELS[level] < LOG_LEVELS[logLevel]) return;
    var line = new Date().toLocaleTimeString() + " [" + level + "] " + msg;
    var pre = $("log");
    if (pre) pre.textContent = line + "\n" + pre.textContent;
    var fn = level === "ERROR" ? console.error : (level === "WARNING" ? console.warn : (level === "DEBUG" ? console.debug : console.log));
    fn("[pptx-web-bridge] " + msg);
  }
  function setStatus(text, isError) { var s = $("status"); s.textContent = text; s.style.color = isError ? "#ffb3a7" : ""; if (isError) log(text, "ERROR"); }

  // ---------------------------------------------------------------------
  // 進捗バー（事前見積 + サブステップ累積％ + タイマー補間）
  // ---------------------------------------------------------------------
  var progress = { timer: null, start: 0, estimate: 0, base: 0, span: 0 };
  /**
   * 進捗を開始する。
   * @param {string[]} steps 大ステップ名の配列
   * @param {number} estimateMs 全体の推定時間（ミリ秒）
   */
  function progressStart(steps, estimateMs) {
    progress.steps = steps; progress.estimate = estimateMs; progress.start = Date.now(); progress.base = 0; progress.span = 100 / steps.length;
    var el = $("progress"); el.classList.remove("hidden", "success");
    progressStep(0);
    clearInterval(progress.timer);
    progress.timer = setInterval(function () {
      // AI/変換待ちの停止感を消すため、経過時間から現在ステップ内を補間する
      var elapsed = Date.now() - progress.start;
      var within = Math.min(0.9, elapsed / Math.max(1, progress.estimate / progress.steps.length));
      progressSet(progress.base + progress.span * within);
      var remain = Math.max(0, progress.estimate - elapsed);
      $("progress-eta").textContent = remain > 0 ? "（残り約 " + Math.ceil(remain / 1000) + " 秒）" : "";
    }, 200);
  }
  function progressStep(i) { progress.base = progress.span * i; $("progress-step").textContent = (i + 1) + "/" + progress.steps.length + " " + progress.steps[i]; progressSet(progress.base); }
  function progressSet(pct) { pct = Math.max(0, Math.min(100, pct)); $("progress-fill").style.width = pct + "%"; $("progress-pct").textContent = Math.round(pct) + "%"; }
  function progressDone(ok) {
    clearInterval(progress.timer);
    var el = $("progress");
    if (ok) { progressSet(100); el.classList.add("success"); $("progress-step").textContent = "完了"; $("progress-eta").textContent = ""; setTimeout(function () { el.classList.add("hidden"); }, 1500); }
    else { el.classList.add("hidden"); }
  }

  // ---------------------------------------------------------------------
  // API
  // ---------------------------------------------------------------------
  function api(path, options) {
    log("API " + (options && options.method || "GET") + " " + path, "DEBUG");
    return fetch(path, options).then(function (res) {
      if (!res.ok) {
        return res.text().then(function (t) {
          var detail = t;
          try { detail = JSON.parse(t).detail || t; } catch (e) { /* JSON でなければそのまま */ }
          throw new Error(res.status + ": " + detail);
        });
      }
      return res;
    });
  }
  function apiJson(path, body) {
    return api(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined).then(function (r) { return r.json(); });
  }
  /** 現在の状態を API へ送る本文を作る。 */
  function currentBody(extra) {
    var b = { presentation: state.presentation, template_id: $("template-select").value, mode: $("mode-select").value, write_to_output: $("write-output").checked };
    for (var k in (extra || {})) b[k] = extra[k];
    return b;
  }

  // ---------------------------------------------------------------------
  // 取込
  // ---------------------------------------------------------------------
  function applyImport(result, sourceLabel) {
    state.presentation = result.presentation;
    state.warnings = result.warnings || [];
    state.quality = result.quality || null;
    state.report = null;
    state.selectedSlide = 0;
    if (result.schema_errors && result.schema_errors.length) log("スキーマ違反が残っています: " + result.schema_errors.join(" / "), "ERROR");
    $("project-name").value = $("project-name").value || (state.presentation.meta && state.presentation.meta.title) || "";
    renderAll();
    setStatus(sourceLabel + " を取り込みました（スライド " + state.presentation.slides.length + " 枚、警告 " + state.warnings.length + " 件）");
    log(sourceLabel + " 取込完了: slides=" + state.presentation.slides.length + " warnings=" + state.warnings.length);
  }

  /** ファイル種別ごとに取込 API を切り替える（設計基準 4.1 のマトリクスに相当）。 */
  function importFile(file) {
    var name = file.name.toLowerCase();
    var fd = new FormData();
    fd.append("file", file);
    fd.append("template_id", $("template-select").value);
    var path;
    if (name.endsWith(".pptx")) path = "/api/import/pptx";
    else if (name.endsWith(".html") || name.endsWith(".htm") || name.endsWith(".zip")) path = "/api/import/html";
    else if (name.endsWith(".json")) path = "/api/import/json";
    else { setStatus("対応していない拡張子です: " + file.name, true); return; }
    setStatus("変換中: " + file.name + " …");
    // 推定時間: 1MB あたり 1.5 秒 + 基本 1.5 秒（PPTX は画像取り出し分を加味）
    progressStart(["送信", "解析・レイアウト", "プレビュー描画"], 1500 + file.size / 1e6 * 1500);
    api(path, { method: "POST", body: fd }).then(function (r) { progressStep(1); return r.json(); })
      .then(function (result) { progressStep(2); applyImport(result, file.name); progressDone(true); })
      .catch(function (e) { progressDone(false); setStatus("取込失敗: " + e.message, true); });
  }

  // ---------------------------------------------------------------------
  // 描画
  // ---------------------------------------------------------------------
  function slideTitle(s) {
    if (s.title) return s.title;
    var els = s.elements || [];
    for (var i = 0; i < els.length; i++) { var t = elementText(els[i]); if (t) return t.split("\n")[0].slice(0, 40); }
    return "スライド " + (s.index + 1);
  }
  function elementText(el) {
    if (el.type === "text" || el.type === "shape") return (el.paragraphs || []).map(function (p) { return (p.runs || []).map(function (r) { return r.text; }).join(""); }).join("\n");
    if (el.type === "table") return (el.rows || []).map(function (row) { return row.map(function (c) { return c.text; }).join("\t"); }).join("\n");
    return "";
  }
  function renderAll() {
    renderSlideList(); renderEditor(); renderWarnings(); renderQuality(); renderReport();
    $("json-editor").value = state.presentation ? JSON.stringify(state.presentation, null, 2) : "";
    refreshPreview(); autosave();
  }
  function reindex() { state.presentation.slides.forEach(function (s, i) { s.index = i; }); }

  function renderSlideList() {
    var ol = $("slide-list");
    ol.innerHTML = "";
    if (!state.presentation) { $("slide-count").textContent = ""; return; }
    var slides = state.presentation.slides;
    $("slide-count").textContent = "(" + slides.length + " 枚)";
    slides.forEach(function (s, i) {
      var li = document.createElement("li");
      li.className = "slide-item" + (i === state.selectedSlide ? " selected" : "");
      li.setAttribute("data-slide", i);
      var warnCount = (s.warnings || []).length;
      li.innerHTML = '<span class="num">' + (i + 1) + '</span>' +
        '<div><input class="title-input" type="text" data-slide-title="' + i + '" value="' + escapeAttr(slideTitle(s)) + '" title="スライド題名">' +
        '<div class="meta">' + escapeHtml(s.layout || "") + ' / 要素 ' + (s.elements || []).length + (warnCount ? ' / <span class="warn">警告 ' + warnCount + '</span>' : "") + '</div></div>' +
        '<div class="row"><button class="small secondary" data-slide-act="up" data-slide="' + i + '" title="上へ">↑</button><button class="small secondary" data-slide-act="down" data-slide="' + i + '" title="下へ">↓</button><button class="small secondary" data-slide-act="dup" data-slide="' + i + '" title="複製">⧉</button><button class="small secondary" data-slide-act="del" data-slide="' + i + '" title="削除">✕</button></div>';
      ol.appendChild(li);
    });
  }
  /** スライド一覧の操作（イベント委譲から呼ばれる）。 */
  function slideAction(act, i) {
    var slides = state.presentation.slides, s = slides[i];
    if (act === "up" && i > 0) { slides.splice(i - 1, 0, slides.splice(i, 1)[0]); state.selectedSlide = i - 1; }
    if (act === "down" && i < slides.length - 1) { slides.splice(i + 1, 0, slides.splice(i, 1)[0]); state.selectedSlide = i + 1; }
    if (act === "dup") { var copy = JSON.parse(JSON.stringify(s)); copy.id = s.id + "_copy" + Date.now().toString(36); copy.elements.forEach(function (el, k) { el.id = copy.id + "_e" + (k + 1); }); slides.splice(i + 1, 0, copy); }
    if (act === "del") { if (!confirm("スライド " + (i + 1) + " を削除しますか？")) return; slides.splice(i, 1); state.selectedSlide = Math.max(0, Math.min(state.selectedSlide, slides.length - 1)); }
    reindex(); renderAll();
  }
  function selectSlide(i) {
    state.selectedSlide = i;
    document.querySelectorAll(".slide-item").forEach(function (x, k) { x.classList.toggle("selected", k === i); });
    renderEditor(); previewGoto(i);
  }

  function renderEditor() {
    var body = $("editor-body");
    body.innerHTML = "";
    if (!state.presentation || !state.presentation.slides.length) { body.innerHTML = '<p class="muted">スライドがありません。</p>'; $("editor-target").textContent = ""; return; }
    var s = state.presentation.slides[state.selectedSlide];
    if (!s) return;
    $("editor-target").textContent = "(スライド " + (state.selectedSlide + 1) + ")";
    (s.elements || []).forEach(function (el, k) {
      var box = document.createElement("div");
      box.className = "el-editor";
      var b = el.bbox ? " / x" + Math.round(el.bbox.x) + " y" + Math.round(el.bbox.y) + " w" + Math.round(el.bbox.w) + " h" + Math.round(el.bbox.h) + "pt" : " / 座標未確定";
      var head = '<div class="head"><span>' + escapeHtml(el.type + (el.role ? " / " + el.role : "") + b) + '</span><span>' + escapeHtml(el.id) + '</span></div>';
      if (el.type === "text" || el.type === "shape") box.innerHTML = head + '<textarea data-el="' + k + '" data-el-kind="text" title="1 行 = 1 段落。書式は元の段落のものを保ちます。">' + escapeHtml(elementText(el)) + '</textarea>';
      else if (el.type === "table") box.innerHTML = head + '<textarea data-el="' + k + '" data-el-kind="table" title="タブ区切りでセル、改行で行">' + escapeHtml(elementText(el)) + '</textarea>';
      else if (el.type === "image") box.innerHTML = head + '<label>代替テキスト <input type="text" data-el="' + k + '" data-el-kind="alt" value="' + escapeAttr(el.alt || "") + '"></label>';
      else box.innerHTML = head + '<p class="muted">' + escapeHtml(el.alt || "編集対象外の要素") + '</p>';
      body.appendChild(box);
    });
    var n = document.createElement("div");
    n.className = "el-editor";
    n.innerHTML = '<div class="head"><span>ノート</span></div><textarea data-el-kind="notes">' + escapeHtml(s.notes || "") + '</textarea>';
    body.appendChild(n);
  }
  /** 要素編集欄の change を状態へ反映する（イベント委譲から呼ばれる）。 */
  function editorChange(target) {
    var s = state.presentation.slides[state.selectedSlide];
    var kind = target.getAttribute("data-el-kind");
    if (kind === "notes") { s.notes = target.value || null; autosave(); return; }
    var el = s.elements[parseInt(target.getAttribute("data-el"), 10)];
    if (!el) return;
    if (kind === "text") {
      var old = el.paragraphs || [];
      el.paragraphs = target.value.split("\n").map(function (line, k) {
        var base = old[k] || old[old.length - 1] || { runs: [{ text: "" }], level: 0, bullet: null };
        var run0 = (base.runs && base.runs[0]) ? base.runs[0] : {};
        var newRun = {}; for (var key in run0) if (key !== "text") newRun[key] = run0[key];
        newRun.text = line;
        return { runs: [newRun], level: base.level || 0, bullet: base.bullet || null, align: base.align };
      });
    } else if (kind === "table") {
      el.rows = target.value.split("\n").map(function (line, r) {
        return line.split("\t").map(function (t, c) { var oldc = (el.rows[r] && el.rows[r][c]) || {}; var nc = {}; for (var key in oldc) nc[key] = oldc[key]; nc.text = t; return nc; });
      });
    } else if (kind === "alt") { el.alt = target.value; }
    renderAll();
  }

  function renderWarnings() {
    var ul = $("warning-list");
    ul.innerHTML = "";
    $("warn-count").textContent = state.warnings.length;
    if (!state.warnings.length) { ul.innerHTML = '<li class="muted">警告はありません。</li>'; return; }
    state.warnings.forEach(function (w) {
      var li = document.createElement("li");
      li.innerHTML = '<span><span class="sev-warning">[' + escapeHtml(w.code) + ']</span> ' + escapeHtml(w.message) + (w.fallback ? ' <span class="muted">→ ' + escapeHtml(w.fallback) + '</span>' : "") + '</span><span class="muted">' + escapeHtml((w.slide_id || "") + (w.element_id ? "/" + w.element_id : "")) + '</span>';
      ul.appendChild(li);
    });
  }
  function renderQuality() {
    var ul = $("quality-list");
    ul.innerHTML = "";
    var issues = (state.quality && state.quality.issues) || [];
    $("quality-count").textContent = issues.length;
    if (!issues.length) { ul.innerHTML = '<li class="muted">問題は見つかりませんでした。</li>'; return; }
    issues.forEach(function (i) {
      var li = document.createElement("li");
      li.innerHTML = '<span><span class="sev-' + escapeAttr(i.severity) + '">[' + escapeHtml(i.code) + ']</span> ' + escapeHtml(i.message) + '</span><span class="muted">' + escapeHtml((i.slide_id || "") + (i.element_id ? "/" + i.element_id : "")) + '</span>';
      ul.appendChild(li);
    });
  }
  /** 要素判別レポート（文字/画像、座標、フォント pt）を表に描く。 */
  function renderReport() {
    var tbody = document.querySelector("#report-table tbody");
    tbody.innerHTML = "";
    if (!state.report) { $("report-summary").textContent = "「最新化」で取得します。"; return; }
    var sm = state.report.summary;
    $("report-summary").textContent = "要素 " + sm.elements + " / 文字系 " + sm.text_as_shapes + "（座標確定 " + sm.text_with_bbox + "）/ 画像 " + sm.images + " / 編集可 " + Math.round(sm.editable_ratio * 100) + "%";
    var f = function (v) { return v == null ? "" : (Math.round(v * 10) / 10); };
    state.report.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      var font = r.font_pt_min == null ? "" : (r.font_pt_min === r.font_pt_max ? r.font_pt_min : r.font_pt_min + "–" + r.font_pt_max);
      tr.innerHTML = "<td>" + r.slide + "</td><td>" + escapeHtml(r.element_id) + "</td><td>" + escapeHtml(r.kind) + "</td><td>" + escapeHtml(r.role || "") + '</td><td class="num">' + f(r.x) + '</td><td class="num">' + f(r.y) + '</td><td class="num">' + f(r.w) + '</td><td class="num">' + f(r.h) + '</td><td class="num">' + font + "</td><td>" + escapeHtml(r.text || "") + "</td><td>" + escapeHtml(r.image_px || "") + "</td><td>" + (r.editable ? "○" : "×") + "</td>";
      tbody.appendChild(tr);
    });
  }
  function fetchReport() {
    if (!state.presentation) return;
    apiJson("/api/report", currentBody()).then(function (r) { state.report = r; renderReport(); activateTab("report"); }).catch(function (e) { setStatus(e.message, true); });
  }

  var previewTimer = null;
  function refreshPreview() {
    if (!state.presentation) { $("preview").srcdoc = "<p style='color:#ccc;font-family:sans-serif;padding:20px'>ファイルを投入するとここにプレビューが表示されます。</p>"; return; }
    clearTimeout(previewTimer);
    previewTimer = setTimeout(function () {
      api("/api/preview/html", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentBody()) })
        .then(function (r) { return r.text(); })
        .then(function (html) { $("preview").srcdoc = html; setTimeout(function () { previewGoto(state.selectedSlide); }, 300); })
        .catch(function (e) { log("プレビュー失敗: " + e.message, "ERROR"); });
    }, 250);
  }
  function previewGoto(i) { try { var w = $("preview").contentWindow; if (w && w.location) w.location.hash = "#s" + (i + 1); } catch (e) { /* sandbox 制約時は無視 */ } }

  // ---------------------------------------------------------------------
  // 出力
  // ---------------------------------------------------------------------
  function download(path, filename) {
    if (!state.presentation) { setStatus("先にファイルを投入してください。", true); return; }
    setStatus("生成中 …");
    var isVisual = path.indexOf("pptx") >= 0 && $("mode-select").value !== "editable";
    progressStart(["生成", "ダウンロード"], (isVisual ? 4000 : 1500) + state.presentation.slides.length * (isVisual ? 400 : 60));
    api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentBody({ name: $("project-name").value })) })
      .then(function (r) {
        progressStep(1);
        var out = r.headers.get("X-Output-Path"); if (out) { try { out = decodeURIComponent(out); } catch (e) { /* そのまま */ } }
        var warns = r.headers.get("X-Warnings");
        var cd = r.headers.get("Content-Disposition") || "";
        var m = /filename\*=UTF-8''([^;]+)/.exec(cd);
        if (m) { try { m = [null, decodeURIComponent(m[1])]; } catch (e) { m = null; } }
        if (!m) m = /filename="([^"]+)"/.exec(cd);
        return r.blob().then(function (blob) {
          var a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = (m && m[1]) || filename;
          document.body.appendChild(a); a.click(); a.remove();
          progressDone(true);
          setStatus("出力完了: " + a.download + (out ? "（" + out + "）" : ""));
          log("出力: " + a.download + (out ? " -> " + out : "") + (warns ? " 警告: " + warns : ""));
        });
      })
      .catch(function (e) { progressDone(false); setStatus("出力失敗: " + e.message, true); });
  }

  // ---------------------------------------------------------------------
  // プロジェクト
  // ---------------------------------------------------------------------
  function loadProjects() {
    apiJson("/api/projects").then(function (r) {
      var ul = $("project-list");
      ul.innerHTML = "";
      if (!r.projects.length) { ul.innerHTML = '<li class="muted">保存済みプロジェクトはありません。</li>'; return; }
      r.projects.forEach(function (p) {
        var li = document.createElement("li");
        li.innerHTML = '<span title="' + escapeAttr(p.updated_at) + '">' + escapeHtml(p.name) + ' <span class="muted">(' + p.slides + '枚)</span></span><span class="row"><button class="small" data-project-act="load" data-project="' + escapeAttr(p.name) + '">開く</button><button class="small secondary" data-project-act="del" data-project="' + escapeAttr(p.name) + '">削除</button></span>';
        ul.appendChild(li);
      });
    }).catch(function (e) { log("プロジェクト一覧取得失敗: " + e.message, "ERROR"); });
  }
  function autosave() { try { if (state.presentation) localStorage.setItem(LS_KEY, JSON.stringify({ presentation: state.presentation, at: Date.now() })); } catch (e) { /* 容量超過時は無視 */ } }

  // ---------------------------------------------------------------------
  // アクション（data-action）
  // ---------------------------------------------------------------------
  var actions = {
    "new": function () { apiJson("/api/new?template_id=" + encodeURIComponent($("template-select").value)).then(function (r) { applyImport({ presentation: r.presentation, warnings: [] }, "空の資料"); }); },
    "closing": function () {
      if (!state.presentation) { setStatus("先にファイルを投入してください。", true); return; }
      apiJson("/api/closing-slide", currentBody({ name: "" })).then(function (r) { state.presentation = r.presentation; state.selectedSlide = r.presentation.slides.length - 1; renderAll(); setStatus(r.added ? "最終ページを追加しました。" : "最終ページは既にあります。"); }).catch(function (e) { setStatus(e.message, true); });
    },
    "save": function () {
      if (!state.presentation) { setStatus("保存する資料がありません。", true); return; }
      var name = $("project-name").value.trim() || (state.presentation.meta.title || "project");
      apiJson("/api/projects", { name: name, presentation: state.presentation }).then(function (r) { $("project-name").value = r.name; setStatus("保存しました: " + r.saved); loadProjects(); }).catch(function (e) { setStatus(e.message, true); });
    },
    "export-html": function () { download("/api/export/html", "web.zip"); },
    "export-pptx": function () { download("/api/export/pptx", "presentation.pptx"); },
    "export-json": function () { download("/api/export/json", "presentation.json"); },
    "refresh": refreshPreview,
    "open-preview": function () { var html = $("preview").srcdoc; if (!html) return; window.open(URL.createObjectURL(new Blob([html], { type: "text/html" })), "_blank"); },
    "relayout": function () { if (!state.presentation) return; apiJson("/api/layout", currentBody()).then(function (r) { applyImport(r, "再レイアウト"); }).catch(function (e) { setStatus(e.message, true); }); },
    "check": function () { if (!state.presentation) return; apiJson("/api/quality", currentBody()).then(function (q) { state.quality = q; renderQuality(); activateTab("quality"); setStatus("品質検査: " + q.summary.total + " 件"); }).catch(function (e) { setStatus(e.message, true); }); },
    "report": fetchReport,
    "json-apply": function () {
      var raw;
      try { raw = JSON.parse($("json-editor").value); } catch (e) { setStatus("JSON 構文エラー: " + e.message, true); return; }
      apiJson("/api/validate", { presentation: raw }).then(function (r) {
        state.presentation = r.presentation; state.warnings = r.repairs || [];
        if (r.schema_errors.length) log("スキーマ違反: " + r.schema_errors.join(" / "), "ERROR");
        renderAll(); setStatus(r.valid ? "JSON を反映しました。" : "JSON を反映しましたが違反が残っています（ログ参照）。", !r.valid);
      }).catch(function (e) { setStatus(e.message, true); });
    }
  };

  /** ドキュメントレベルのイベント委譲（設計基準 3.3）。closest() で親要素を判定する。 */
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-action], [data-slide-act], [data-project-act], .tab, .slide-item, #dropzone");
    if (!t) return;
    if (t.hasAttribute("data-action")) { var fn = actions[t.getAttribute("data-action")]; if (fn) fn(); return; }
    if (t.hasAttribute("data-slide-act")) { e.stopPropagation(); slideAction(t.getAttribute("data-slide-act"), parseInt(t.getAttribute("data-slide"), 10)); return; }
    if (t.hasAttribute("data-project-act")) {
      var name = t.getAttribute("data-project");
      if (t.getAttribute("data-project-act") === "load") apiJson("/api/projects/" + encodeURIComponent(name)).then(function (res) { $("project-name").value = name; applyImport(res, "プロジェクト " + name); }).catch(function (err) { setStatus(err.message, true); });
      else if (confirm(name + " を削除しますか？")) api("/api/projects/" + encodeURIComponent(name), { method: "DELETE" }).then(loadProjects);
      return;
    }
    if (t.classList.contains("tab")) { activateTab(t.getAttribute("data-tab")); return; }
    if (t.id === "dropzone") { $("file-input").click(); return; }
    if (t.classList.contains("slide-item") && e.target.tagName !== "INPUT") { selectSlide(parseInt(t.getAttribute("data-slide"), 10)); }
  });
  document.addEventListener("focusin", function (e) {
    var inp = e.target.closest("[data-slide-title]");
    if (inp) { var i = parseInt(inp.getAttribute("data-slide-title"), 10); if (i !== state.selectedSlide) selectSlide(i); }
  });
  document.addEventListener("change", function (e) {
    var t = e.target;
    if (t.hasAttribute("data-slide-title")) {
      var s = state.presentation.slides[parseInt(t.getAttribute("data-slide-title"), 10)];
      s.title = t.value;
      var titleEl = (s.elements || []).filter(function (el) { return el.role === "title"; })[0];
      if (titleEl && titleEl.paragraphs && titleEl.paragraphs[0]) { var r0 = titleEl.paragraphs[0].runs[0] || {}; r0.text = t.value; titleEl.paragraphs[0].runs = [r0]; }
      renderAll(); return;
    }
    if (t.hasAttribute("data-el-kind")) { editorChange(t); return; }
    if (t.id === "file-input") { if (t.files[0]) importFile(t.files[0]); t.value = ""; return; }
    if (t.id === "template-select") { refreshPreview(); state.report = null; renderReport(); return; }
    if (t.id === "loglevel-select") { setLogLevel(t.value); return; }
  });
  document.addEventListener("keydown", function (e) { if (e.target.id === "dropzone" && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); $("file-input").click(); } });
  ["dragenter", "dragover"].forEach(function (ev) { document.addEventListener(ev, function (e) { var dz = e.target.closest("#dropzone"); if (dz) { e.preventDefault(); dz.classList.add("over"); } }); });
  ["dragleave", "drop"].forEach(function (ev) { document.addEventListener(ev, function (e) { var dz = e.target.closest("#dropzone"); if (dz) { e.preventDefault(); dz.classList.remove("over"); if (ev === "drop") { var f = e.dataTransfer.files[0]; if (f) importFile(f); } } }); });

  function activateTab(name) {
    document.querySelectorAll(".tab").forEach(function (t) { t.classList.toggle("active", t.getAttribute("data-tab") === name); });
    document.querySelectorAll(".tab-body").forEach(function (b) { b.classList.toggle("hidden", b.id !== "tab-" + name); });
    if (name === "report" && !state.report) fetchReport();
  }
  /** ログレベルをフロントとバックエンドの両方に設定する（設計基準 7.3）。 */
  function setLogLevel(level) {
    logLevel = level.toUpperCase();
    $("loglevel-select").value = logLevel;
    apiJson("/api/loglevel", { level: logLevel }).then(function () { log("ログレベル: " + logLevel, "WARNING"); }).catch(function (e) { log("ログレベル変更失敗: " + e.message, "ERROR"); });
  }
  function escapeHtml(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function escapeAttr(s) { return escapeHtml(s); }

  // ---------------------------------------------------------------------
  // デバッグコンソール（設計基準 7.1: 最終ビルド時に削除指示があるまで保持）
  // ---------------------------------------------------------------------
  window.qcDebug = window.__QC_DEBUG__ = {
    version: "0.2.0",
    state: function () { return state; },
    presentation: function () { return state.presentation; },
    setPresentation: function (p) { state.presentation = p; renderAll(); },
    slide: function (i) { return state.presentation && state.presentation.slides[i == null ? state.selectedSlide : i]; },
    setLogLevel: setLogLevel,
    logLevel: function () { return logLevel; },
    runQuality: function () { actions.check(); },
    report: function () { fetchReport(); return state.report; },
    exportPptx: function () { actions["export-pptx"](); },
    exportHtml: function () { actions["export-html"](); },
    relayout: function () { actions.relayout(); },
    clearAutosave: function () { try { localStorage.removeItem(LS_KEY); } catch (e) { /* 無視 */ } },
    help: function () { console.groupCollapsed("qcDebug コマンド一覧"); console.table(Object.keys(window.qcDebug).map(function (k) { return { command: "qcDebug." + k + (typeof window.qcDebug[k] === "function" ? "()" : "") }; })); console.groupEnd(); }
  };

  // ---------------------------------------------------------------------
  // 初期化
  // ---------------------------------------------------------------------
  function init() {
    apiJson("/api/config").then(function (c) {
      state.config = c;
      var ts = $("template-select");
      c.templates.forEach(function (t) { var o = document.createElement("option"); o.value = t.id; o.textContent = t.name; o.title = t.description; ts.appendChild(o); });
      var ms = $("mode-select");
      var labels = { editable: "編集性優先（文字はテキストシェイプ）", visual: "見た目優先（画像化）", hybrid: "ハイブリッド" };
      c.pptx_modes.forEach(function (m) { var o = document.createElement("option"); o.value = m; o.textContent = labels[m] || m; if (m === c.default_mode) o.selected = true; ms.appendChild(o); });
      $("raster-badge").textContent = "画像化: " + (c.raster_available ? "利用可" : "利用不可（見た目優先は編集性優先へ代替）");
      $("output-dir").textContent = c.output_dir;
      $("projects-dir").textContent = c.projects_dir;
      if (c.log_level) { logLevel = c.log_level; $("loglevel-select").value = logLevel; }
    }).catch(function (e) { setStatus("設定取得失敗: " + e.message, true); });
    loadProjects();
    try {
      var saved = JSON.parse(localStorage.getItem(LS_KEY) || "null");
      if (saved && saved.presentation && saved.presentation.slides && saved.presentation.slides.length) {
        state.presentation = saved.presentation; renderAll();
        setStatus("前回の作業内容を復元しました（" + new Date(saved.at).toLocaleString() + "）");
      } else { refreshPreview(); }
    } catch (e) { refreshPreview(); }
    log("qcDebug.help() でデバッグコマンド一覧を表示できます", "DEBUG");
  }
  document.addEventListener("DOMContentLoaded", init);
})();
