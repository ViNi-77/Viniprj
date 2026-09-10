/**
 * アプリ UI ロジック（素の JavaScript）。司令塔として、状態・API・各モジュール（canvas / inspector / slidelist / history / splitter）をつなぐ。
 *
 * 設計基準の反映:
 * - 状態は state.presentation（Presentation JSON）1 つに集約し、編集は必ずここを書き換えてから描画する。
 * - 座標計算・ファイル生成・スライドの描画はローカル API に任せる（描画器は web_renderer の 1 つだけ）。
 *   キャンバスはサーバが描いた断片を差し込み、ドラッグ中だけ DOM を直接動かす。
 * - ボタン操作はドキュメントレベルのイベント委譲（data-action 属性）で受ける（設計基準 3.3）。
 * - 進捗バーは大ステップ表記 + 累積％ + タイマー補間 + 完了時サクセス表示（設計基準 3.1）。
 * - デバッグ用に window.qcDebug を常備し、ログレベルを実行時に切り替えられる（設計基準 7）。
 */
window.PWB = window.PWB || {};
(function () {
  "use strict";

  /** @type {{presentation: object|null, selectedSlide: number, config: object|null, warnings: object[], quality: object|null, report: object|null}} グローバル状態 */
  var state = { presentation: null, selectedSlide: 0, config: null, warnings: [], quality: null, report: null };
  var LS_KEY = "pptx_web_bridge.autosave";
  var LOG_LEVELS = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40 };
  var logLevel = "INFO";
  var $ = function (id) { return document.getElementById(id); };
  var lastCoalesce = { key: null, at: 0 };

  // ---------------------------------------------------------------------
  // ログ・状態表示
  // ---------------------------------------------------------------------
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
  function progressStart(steps, estimateMs) {
    progress.steps = steps; progress.estimate = estimateMs; progress.start = Date.now(); progress.base = 0; progress.span = 100 / steps.length;
    var el = $("progress"); el.classList.remove("hidden", "success");
    progressStep(0);
    clearInterval(progress.timer);
    progress.timer = setInterval(function () {
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
  function currentBody(extra) {
    var b = { presentation: state.presentation, template_id: $("template-select").value, mode: $("mode-select").value, write_to_output: $("write-output").checked };
    for (var k in (extra || {})) b[k] = extra[k];
    return b;
  }

  // ---------------------------------------------------------------------
  // 取込
  // ---------------------------------------------------------------------
  function applyImport(result, sourceLabel, keepHistory) {
    state.presentation = result.presentation;
    state.warnings = result.warnings || [];
    state.quality = result.quality || null;
    state.report = null;
    state.selectedSlide = Math.min(state.selectedSlide, Math.max(0, state.presentation.slides.length - 1));
    if (!keepHistory) { state.selectedSlide = 0; PWB.history.clear(); }
    PWB.slidelist.clearThumbs();
    PWB.canvas.setSelection([]);
    if (result.schema_errors && result.schema_errors.length) log("スキーマ違反が残っています: " + result.schema_errors.join(" / "), "ERROR");
    $("project-name").value = $("project-name").value || (state.presentation.meta && state.presentation.meta.title) || "";
    renderAll();
    setStatus(sourceLabel + " を取り込みました（スライド " + state.presentation.slides.length + " 枚、警告 " + state.warnings.length + " 件）");
    log(sourceLabel + " 取込完了: slides=" + state.presentation.slides.length + " warnings=" + state.warnings.length);
  }

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
    progressStart(["送信", "解析・レイアウト", "プレビュー描画"], 1500 + file.size / 1e6 * 1500);
    api(path, { method: "POST", body: fd }).then(function (r) { progressStep(1); return r.json(); })
      .then(function (result) { progressStep(2); applyImport(result, file.name); progressDone(true); })
      .catch(function (e) { progressDone(false); setStatus("取込失敗: " + e.message, true); });
  }

  // ---------------------------------------------------------------------
  // 描画
  // ---------------------------------------------------------------------
  function renderAll(opts) {
    opts = opts || {};
    PWB.slidelist.render();
    $("slide-count").textContent = state.presentation ? "(" + state.presentation.slides.length + " 枚)" : "";
    if (!opts.keepInspector) PWB.inspector.render();
    renderWarnings(); renderQuality(); renderReport();
    $("json-editor").value = state.presentation ? JSON.stringify(state.presentation, null, 2) : "";
    updateUndoButtons();
    scheduleRender();
    autosave();
  }
  function reindex() { state.presentation.slides.forEach(function (s, i) { s.index = i; }); }
  function updateUndoButtons() { $("btn-undo").disabled = !PWB.history.canUndo(); $("btn-redo").disabled = !PWB.history.canRedo(); }

  var renderTimer = null;
  var renderSeq = 0;
  /** 選択スライド（＋サムネイル未取得分）をサーバで描き、キャンバスとサムネイルへ反映する。 */
  function scheduleRender() {
    clearTimeout(renderTimer);
    if (!state.presentation) { PWB.canvas.clear(); return; }
    renderTimer = setTimeout(renderNow, 120);
  }
  function renderNow() {
    if (!state.presentation) return;
    var pres = state.presentation;
    var indices = [state.selectedSlide];
    pres.slides.forEach(function (s, i) { if (!PWB.slidelist.hasThumb(s.id) && indices.indexOf(i) < 0) indices.push(i); });
    var seq = ++renderSeq;
    apiJson("/api/render/slides", currentBody({ indices: indices })).then(function (r) {
      if (seq !== renderSeq) return; // 古い応答は捨てる
      var editing = document.activeElement && $("inspector").contains(document.activeElement);
      state.presentation = r.presentation; // prepare 後（修復・正規化・レイアウト・テンプレート適用）の状態を採用する
      var slides = state.presentation.slides;
      if (state.selectedSlide >= slides.length) state.selectedSlide = Math.max(0, slides.length - 1);
      Object.keys(r.slides).forEach(function (k) { var i = parseInt(k, 10); if (slides[i]) PWB.slidelist.setThumb(slides[i].id, r.slides[k]); });
      var html = r.slides[String(state.selectedSlide)];
      if (html) PWB.canvas.mount(html, r.canvas.width_pt, r.canvas.height_pt, r.theme_css);
      $("zoom-label").textContent = Math.round(PWB.canvas.scale() * 100) + "%";
      if (!editing) PWB.inspector.render();
      $("json-editor").value = JSON.stringify(state.presentation, null, 2);
      autosave();
    }).catch(function (e) { log("描画失敗: " + e.message, "ERROR"); });
  }

  function selectSlide(i) {
    if (!state.presentation) return;
    state.selectedSlide = Math.max(0, Math.min(i, state.presentation.slides.length - 1));
    PWB.canvas.setSelection([]);
    PWB.slidelist.render();
    PWB.inspector.render();
    scheduleRender();
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

  // ---------------------------------------------------------------------
  // 編集（各モジュールから PWB.core 経由で呼ばれる）
  // ---------------------------------------------------------------------
  function snapshot() { return JSON.parse(JSON.stringify(state.presentation)); }
  function currentSlide() { return state.presentation && state.presentation.slides[state.selectedSlide]; }
  function marginPt() { return (state.config && state.config.layout && state.config.layout.margin_pt) || 36; }
  function newId(prefix) { var s = currentSlide(); return (s ? s.id : "s") + "_" + prefix + Date.now().toString(36) + Math.floor(Math.random() * 1e3).toString(36); }

  /** 変更の共通処理: 履歴 → 更新日時 → 再描画。before は変更前のスナップショット。 */
  function changed(opts) {
    opts = opts || {};
    if (opts.before) {
      var now = Date.now();
      if (!(opts.coalesce && lastCoalesce.key === opts.coalesce && now - lastCoalesce.at < 1000)) PWB.history.push(opts.before);
      lastCoalesce = { key: opts.coalesce || null, at: now };
    }
    if (state.presentation) { state.presentation.meta = state.presentation.meta || {}; state.presentation.meta.edited_at = new Date().toISOString(); }
    if (opts.structural) PWB.slidelist.render();
    renderAll({ keepInspector: !!opts.keepInspector });
  }

  function deleteElements(ids) {
    var s = currentSlide();
    if (!s || !ids.length) return;
    var before = snapshot();
    s.elements = s.elements.filter(function (el) { return ids.indexOf(el.id) < 0; });
    PWB.canvas.setSelection([]);
    changed({ index: state.selectedSlide, before: before });
  }
  function duplicateElements(ids) {
    var s = currentSlide();
    if (!s || !ids.length) return;
    var before = snapshot();
    var maxZ = s.elements.reduce(function (m, el) { return Math.max(m, el.z || 0); }, 0);
    var created = [];
    ids.forEach(function (id, k) {
      var src = s.elements.filter(function (el) { return el.id === id; })[0];
      if (!src) return;
      var copy = JSON.parse(JSON.stringify(src));
      copy.id = newId("e");
      if (copy.bbox) { copy.bbox.x += 12; copy.bbox.y += 12; copy.user_bbox = true; }
      copy.z = maxZ + 1 + k;
      s.elements.push(copy);
      created.push(copy.id);
    });
    PWB.canvas.setSelection(created);
    changed({ index: state.selectedSlide, before: before });
  }
  function reorderZ(ids, dir) {
    var s = currentSlide();
    if (!s || !ids.length) return;
    var before = snapshot();
    var zs = s.elements.map(function (el) { return el.z || 0; });
    var target = dir > 0 ? Math.max.apply(null, zs) + 1 : Math.min.apply(null, zs) - 1;
    s.elements.forEach(function (el) { if (ids.indexOf(el.id) >= 0) el.z = target; });
    changed({ index: state.selectedSlide, before: before });
  }
  function alignSelection(ids, act) {
    var s = currentSlide();
    if (!s || ids.length < 2) return;
    var before = snapshot();
    var els = s.elements.filter(function (el) { return ids.indexOf(el.id) >= 0 && el.bbox; });
    if (act === "align-left") { var x = Math.min.apply(null, els.map(function (e) { return e.bbox.x; })); els.forEach(function (e) { e.bbox.x = x; e.user_bbox = true; }); }
    if (act === "align-top") { var y = Math.min.apply(null, els.map(function (e) { return e.bbox.y; })); els.forEach(function (e) { e.bbox.y = y; e.user_bbox = true; }); }
    if (act === "same-width") { var w = els[0].bbox.w; els.forEach(function (e) { e.bbox.w = w; e.user_bbox = true; }); }
    changed({ index: state.selectedSlide, before: before });
  }
  function fitHeight(id) {
    apiJson("/api/layout/fit", currentBody({ index: state.selectedSlide, element_id: id })).then(function (r) {
      var s = currentSlide();
      var el = s && s.elements.filter(function (e) { return e.id === id; })[0];
      if (!el || !el.bbox) return;
      var before = snapshot();
      el.bbox.h = Math.round(r.h * 10) / 10; el.user_bbox = true;
      changed({ index: state.selectedSlide, before: before });
    }).catch(function (e) { setStatus(e.message, true); });
  }
  function addElement(kind, file) {
    var s = currentSlide();
    if (!s) { setStatus("先にスライドを用意してください。", true); return; }
    var before = snapshot();
    var m = marginPt();
    var cw = state.presentation.canvas.width_pt, ch = state.presentation.canvas.height_pt;
    var colors = (state.presentation.theme && state.presentation.theme.colors) || {};
    var maxZ = s.elements.reduce(function (mm, el) { return Math.max(mm, el.z || 0); }, 0);
    var el = null;
    if (kind === "text") el = { id: newId("e"), type: "text", role: "body", bbox: { x: m + 24, y: m + 100, w: 400, h: 60 }, paragraphs: [{ runs: [{ text: "テキスト" }], level: 0, bullet: null }], editable: true };
    if (kind === "shape") el = { id: newId("e"), type: "shape", role: null, bbox: { x: m + 24, y: m + 120, w: 240, h: 100 }, shape: "rounded_rect", fill: colors.surface || "#F4F6F9", stroke: colors.line || "#C9D1DB", stroke_width_pt: 1, paragraphs: [], editable: true };
    if (kind === "line") el = { id: newId("e"), type: "line", role: null, bbox: { x: m, y: ch / 2, w: cw - 2 * m, h: 1 }, points: [[m, ch / 2], [cw - m, ch / 2]], stroke: colors.line || "#999999", stroke_width_pt: 1.5, editable: true };
    if (kind === "image" && file) {
      var reader = new FileReader();
      reader.onload = function () {
        var mm = /^data:([^;]+);base64,(.*)$/.exec(String(reader.result));
        if (!mm) return;
        var img = new Image();
        img.onload = function () {
          var aid = "img_u" + Date.now().toString(36);
          state.presentation.assets[aid] = { mime: mm[1], filename: aid + "." + (mm[1].split("/")[1] || "png"), data_base64: mm[2], width_px: img.naturalWidth, height_px: img.naturalHeight };
          var w = Math.min(img.naturalWidth * 0.75, (cw - 2 * m) * 0.5), h = w * img.naturalHeight / img.naturalWidth;
          var e2 = { id: newId("e"), type: "image", role: null, bbox: { x: m + 24, y: m + 100, w: Math.round(w * 10) / 10, h: Math.round(h * 10) / 10 }, asset_id: aid, alt: file.name, fit: "contain", editable: true, z: maxZ + 1, user_bbox: true };
          s.elements.push(e2);
          PWB.canvas.setSelection([e2.id]);
          changed({ index: state.selectedSlide, before: before });
        };
        img.src = String(reader.result);
      };
      reader.readAsDataURL(file);
      return;
    }
    if (!el) return;
    el.z = maxZ + 1; el.user_bbox = true;
    s.elements.push(el);
    PWB.canvas.setSelection([el.id]);
    changed({ index: state.selectedSlide, before: before });
  }
  function moveSlide(from, to) {
    var slides = state.presentation.slides;
    if (from === to || from + 1 === to) return;
    var before = snapshot();
    var s = slides.splice(from, 1)[0];
    if (to > from) to -= 1;
    slides.splice(to, 0, s);
    reindex();
    state.selectedSlide = to;
    changed({ before: before, structural: true });
  }
  function slideAction(act, i) {
    var slides = state.presentation.slides, s = slides[i];
    var before = snapshot();
    if (act === "up" && i > 0) { slides.splice(i - 1, 0, slides.splice(i, 1)[0]); state.selectedSlide = i - 1; }
    else if (act === "down" && i < slides.length - 1) { slides.splice(i + 1, 0, slides.splice(i, 1)[0]); state.selectedSlide = i + 1; }
    else if (act === "dup") { var copy = JSON.parse(JSON.stringify(s)); copy.id = s.id + "_copy" + Date.now().toString(36); delete copy.continuation_of; delete copy.continuation_index; copy.elements.forEach(function (el, k) { el.id = copy.id + "_e" + (k + 1); }); slides.splice(i + 1, 0, copy); state.selectedSlide = i + 1; }
    else if (act === "del") { if (!confirm("スライド " + (i + 1) + " を削除しますか？")) return; slides.splice(i, 1); state.selectedSlide = Math.max(0, Math.min(state.selectedSlide, slides.length - 1)); }
    else return;
    reindex();
    PWB.canvas.setSelection([]);
    changed({ before: before, structural: true });
  }
  function layoutSlide(scope) {
    if (!state.presentation) return;
    var before = snapshot();
    apiJson("/api/layout/slide", currentBody({ index: state.selectedSlide, scope: scope })).then(function (r) {
      PWB.history.push(before);
      state.presentation = r.presentation;
      PWB.canvas.setSelection([]);
      renderAll();
      setStatus(r.count > 1 ? "自動配置しました（" + r.count + " 枚に分割）" : "自動配置しました");
    }).catch(function (e) { setStatus(e.message, true); });
  }
  function undo() { var p = PWB.history.undo(state.presentation); if (p) { state.presentation = p; PWB.canvas.setSelection([]); renderAll(); } }
  function redo() { var p = PWB.history.redo(state.presentation); if (p) { state.presentation = p; PWB.canvas.setSelection([]); renderAll(); } }

  PWB.core = {
    state: state, api: api, apiJson: apiJson, currentBody: currentBody, log: log, setStatus: setStatus, escapeHtml: escapeHtml,
    changed: changed, deleteElements: deleteElements, duplicateElements: duplicateElements, reorderZ: reorderZ, alignSelection: alignSelection, fitHeight: fitHeight, addElement: addElement, moveSlide: moveSlide,
    onSelectionChanged: function () { PWB.inspector.render(); },
    focusInspector: function (id) { PWB.canvas.setSelection([id]); activateTab("inspector"); PWB.inspector.focusText(); },
    select: function (ids) { PWB.canvas.setSelection(ids); }
  };

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
      var before = snapshot();
      apiJson("/api/closing-slide", currentBody({ name: "" })).then(function (r) { PWB.history.push(before); state.presentation = r.presentation; state.selectedSlide = r.presentation.slides.length - 1; renderAll(); setStatus(r.added ? "最終ページを追加しました。" : "最終ページは既にあります。"); }).catch(function (e) { setStatus(e.message, true); });
    },
    "save": function () {
      if (!state.presentation) { setStatus("保存する資料がありません。", true); return; }
      var name = $("project-name").value.trim() || (state.presentation.meta.title || "project");
      apiJson("/api/projects", { name: name, presentation: state.presentation }).then(function (r) { $("project-name").value = r.name; setStatus("保存しました: " + r.saved); loadProjects(); }).catch(function (e) { setStatus(e.message, true); });
    },
    "export-html": function () { download("/api/export/html", "web.zip"); },
    "export-pptx": function () { download("/api/export/pptx", "presentation.pptx"); },
    "export-json": function () { download("/api/export/json", "presentation.json"); },
    "refresh": function () { PWB.slidelist.clearThumbs(); scheduleRender(); },
    "open-preview": function () {
      if (!state.presentation) return;
      api("/api/preview/html", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentBody()) })
        .then(function (r) { return r.text(); })
        .then(function (html) { var w = window.open(URL.createObjectURL(new Blob([html], { type: "text/html" })), "_blank"); if (w) { try { w.location.hash = "#s" + (state.selectedSlide + 1); } catch (e) { /* 無視 */ } } })
        .catch(function (e) { setStatus("プレビュー失敗: " + e.message, true); });
    },
    "relayout": function () { if (!state.presentation) return; var before = snapshot(); apiJson("/api/layout", currentBody()).then(function (r) { PWB.history.push(before); applyImport(r, "再レイアウト", true); }).catch(function (e) { setStatus(e.message, true); }); },
    "layout-slide-unplaced": function () { layoutSlide("unplaced"); },
    "layout-slide-all": function () { if (confirm("このスライドの全要素を配置し直します。手で動かした位置も元に戻ります。よろしいですか？")) layoutSlide("all"); },
    "check": function () { if (!state.presentation) return; apiJson("/api/quality", currentBody()).then(function (q) { state.quality = q; renderQuality(); activateTab("quality"); setStatus("品質検査: " + q.summary.total + " 件"); }).catch(function (e) { setStatus(e.message, true); }); },
    "report": fetchReport,
    "undo": undo,
    "redo": redo,
    "add-text": function () { addElement("text"); },
    "add-shape": function () { addElement("shape"); },
    "add-line": function () { addElement("line"); },
    "add-image": function () { if (!currentSlide()) { setStatus("先にスライドを用意してください。", true); return; } $("add-image-input").click(); },
    "json-apply": function () {
      var raw;
      try { raw = JSON.parse($("json-editor").value); } catch (e) { setStatus("JSON 構文エラー: " + e.message, true); return; }
      var before = snapshot();
      apiJson("/api/validate", { presentation: raw }).then(function (r) {
        if (before) PWB.history.push(before);
        state.presentation = r.presentation; state.warnings = r.repairs || [];
        if (r.schema_errors.length) log("スキーマ違反: " + r.schema_errors.join(" / "), "ERROR");
        PWB.slidelist.clearThumbs();
        renderAll(); setStatus(r.valid ? "JSON を反映しました。" : "JSON を反映しましたが違反が残っています（ログ参照）。", !r.valid);
      }).catch(function (e) { setStatus(e.message, true); });
    }
  };

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
    if (t.classList.contains("slide-item") && e.target.tagName !== "INPUT" && !e.target.closest("button")) { selectSlide(parseInt(t.getAttribute("data-slide"), 10)); }
  });
  document.addEventListener("focusin", function (e) {
    var inp = e.target.closest("[data-slide-title]");
    if (inp) { var i = parseInt(inp.getAttribute("data-slide-title"), 10); if (i !== state.selectedSlide) selectSlide(i); }
  });
  document.addEventListener("change", function (e) {
    var t = e.target;
    if (t.hasAttribute("data-slide-title")) {
      var before = snapshot();
      var s = state.presentation.slides[parseInt(t.getAttribute("data-slide-title"), 10)];
      s.title = t.value;
      var titleEl = (s.elements || []).filter(function (el) { return el.role === "title"; })[0];
      if (titleEl && titleEl.paragraphs && titleEl.paragraphs[0]) { var r0 = titleEl.paragraphs[0].runs[0] || {}; r0.text = t.value; titleEl.paragraphs[0].runs = [r0]; }
      changed({ before: before, structural: true }); return;
    }
    if (t.id === "file-input") { if (t.files[0]) importFile(t.files[0]); t.value = ""; return; }
    if (t.id === "add-image-input") { if (t.files[0]) addElement("image", t.files[0]); t.value = ""; return; }
    if (t.id === "template-select") { state.report = null; renderReport(); PWB.slidelist.clearThumbs(); scheduleRender(); return; }
    if (t.id === "loglevel-select") { setLogLevel(t.value); return; }
  });
  document.addEventListener("keydown", function (e) {
    if (e.target.id === "dropzone" && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); $("file-input").click(); return; }
    if (e.target && /input|textarea|select/i.test(e.target.tagName)) return;
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === "z" || e.key === "Z")) { e.preventDefault(); undo(); }
    else if ((e.ctrlKey || e.metaKey) && (e.key === "y" || e.key === "Y" || (e.shiftKey && (e.key === "z" || e.key === "Z")))) { e.preventDefault(); redo(); }
    else if (e.key === "PageDown" && state.presentation) { e.preventDefault(); selectSlide(state.selectedSlide + 1); }
    else if (e.key === "PageUp" && state.presentation) { e.preventDefault(); selectSlide(state.selectedSlide - 1); }
  });
  ["dragenter", "dragover"].forEach(function (ev) { document.addEventListener(ev, function (e) { var dz = e.target.closest("#dropzone"); if (dz) { e.preventDefault(); dz.classList.add("over"); } }); });
  ["dragleave", "drop"].forEach(function (ev) { document.addEventListener(ev, function (e) { var dz = e.target.closest("#dropzone"); if (dz) { e.preventDefault(); dz.classList.remove("over"); if (ev === "drop") { var f = e.dataTransfer.files[0]; if (f) importFile(f); } } }); });

  function activateTab(name) {
    document.querySelectorAll(".tab").forEach(function (t) { t.classList.toggle("active", t.getAttribute("data-tab") === name); });
    document.querySelectorAll(".tab-body").forEach(function (b) { b.classList.toggle("hidden", b.id !== "tab-" + name); });
    if (name === "report" && !state.report) fetchReport();
  }
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
    version: "0.3.0",
    state: function () { return state; },
    presentation: function () { return state.presentation; },
    setPresentation: function (p) { state.presentation = p; PWB.slidelist.clearThumbs(); renderAll(); },
    slide: function (i) { return state.presentation && state.presentation.slides[i == null ? state.selectedSlide : i]; },
    selectSlide: selectSlide,
    select: function (ids) { PWB.canvas.setSelection(Array.isArray(ids) ? ids : [ids]); },
    selection: function () { return PWB.canvas.getSelection(); },
    setBbox: function (id, b) { var s = currentSlide(); var el = s && s.elements.filter(function (e) { return e.id === id; })[0]; if (!el) return false; var before = snapshot(); el.bbox = { x: b.x, y: b.y, w: b.w, h: b.h }; el.user_bbox = true; changed({ index: state.selectedSlide, before: before }); return true; },
    undo: undo, redo: redo,
    canvasScale: function () { return PWB.canvas.scale(); },
    rendered: function () { return renderSeq; },
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
    PWB.splitter.init();
    PWB.canvas.init($("canvas-area"));
    PWB.inspector.init($("inspector"));
    PWB.slidelist.init($("slide-list"));
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
      } else { PWB.inspector.render(); }
    } catch (e) { PWB.inspector.render(); }
    log("qcDebug.help() でデバッグコマンド一覧を表示できます", "DEBUG");
  }
  document.addEventListener("DOMContentLoaded", init);
})();
