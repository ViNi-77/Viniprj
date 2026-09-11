/**
 * インスペクタ（要素の数値・書式編集）。選択中の要素のプロパティをフォームにし、変更を state へ書いて PWB.core.changed() を呼ぶ。
 * 何も選んでいないときはスライド自体（ノート・背景）を編集する。
 */
window.PWB = window.PWB || {};
PWB.inspector = (function () {
  "use strict";
  var root = null;
  var core = function () { return PWB.core; };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var ROLES = [["title", "題名"], ["subtitle", "副題"], ["body", "本文"], ["caption", "注記"], ["card", "カード"]];
  var SHAPES = [["rect", "四角"], ["rounded_rect", "角丸"], ["ellipse", "楕円"], ["triangle", "三角"], ["diamond", "ひし形"], ["arrow_right", "右矢印"], ["parallelogram", "平行四辺形"]];

  function init(el) {
    root = el;
    root.addEventListener("change", onChange);
    root.addEventListener("click", onClick);
  }

  function slide() { var st = core().state; return st.presentation && st.presentation.slides[st.selectedSlide]; }
  function selectedElement() {
    var ids = PWB.canvas.getSelection();
    var s = slide();
    if (!s || ids.length !== 1) return null;
    for (var i = 0; i < s.elements.length; i++) if (s.elements[i].id === ids[0]) return s.elements[i];
    return null;
  }
  function elementText(el) {
    if (el.type === "text" || el.type === "shape") return (el.paragraphs || []).map(function (p) { return (p.runs || []).map(function (r) { return r.text; }).join(""); }).join("\n");
    if (el.type === "table") return (el.rows || []).map(function (row) { return row.map(function (c) { return c.text; }).join("\t"); }).join("\n");
    return "";
  }
  function firstRun(el) { var p = (el.paragraphs || [])[0]; return p && p.runs && p.runs[0] ? p.runs[0] : {}; }
  function num(v) { return v == null ? "" : Math.round(v * 10) / 10; }
  function field(label, inner, cls) { return '<label class="f ' + (cls || "") + '"><span>' + esc(label) + "</span>" + inner + "</label>"; }
  function numberInput(key, value, step, extra) { return '<input type="number" data-prop="' + key + '" value="' + esc(num(value)) + '" step="' + (step || 1) + '" ' + (extra || "") + ">"; }
  function colorInput(key, value, allowNone) {
    var v = /^#[0-9A-Fa-f]{6}$/.test(value || "") ? value : "#000000";
    return '<span class="color-row"><input type="color" data-prop="' + key + '" value="' + v + '"' + (value ? "" : ' data-unset="1"') + ">" + (allowNone ? '<button type="button" class="small secondary" data-act="clear-prop" data-prop="' + key + '" title="指定を外す">なし</button>' : "") + "</span>";
  }
  function selectInput(key, value, options, allowEmpty) {
    var html = '<select data-prop="' + key + '">' + (allowEmpty ? '<option value="">（既定）</option>' : "");
    options.forEach(function (o) { html += '<option value="' + o[0] + '"' + (o[0] === (value || "") ? " selected" : "") + ">" + esc(o[1]) + "</option>"; });
    return html + "</select>";
  }

  function render() {
    if (!root) return;
    var s = slide();
    if (!s) { root.innerHTML = '<p class="muted">スライドを選ぶと編集できます。</p>'; return; }
    var el = selectedElement();
    var ids = PWB.canvas.getSelection();
    var html = "";
    if (ids.length > 1) {
      html += '<div class="insp-head">' + ids.length + ' 個の要素を選択中</div>';
      html += '<div class="row wrap"><button class="small secondary" data-act="delete">削除</button><button class="small secondary" data-act="duplicate">複製</button><button class="small secondary" data-act="align-left">左揃え</button><button class="small secondary" data-act="align-top">上揃え</button><button class="small secondary" data-act="same-width">幅を揃える</button></div>';
    } else if (el) {
      html += renderElement(el, s);
    } else {
      html += renderSlide(s);
    }
    root.innerHTML = html;
  }

  function renderElement(el, s) {
    var b = el.bbox || { x: 0, y: 0, w: 0, h: 0 };
    var html = '<div class="insp-head"><span>' + esc(typeLabel(el)) + " <code>" + esc(el.id) + "</code></span>" + (el.font_scale && el.font_scale < 1 ? '<span class="pill" title="自動縮小">縮小 ' + Math.round(el.font_scale * 100) + "%</span>" : "") + "</div>";
    html += '<div class="grid4">' + field("x", numberInput("bbox.x", b.x)) + field("y", numberInput("bbox.y", b.y)) + field("幅", numberInput("bbox.w", b.w)) + field("高さ", numberInput("bbox.h", b.h)) + "</div>";
    html += '<div class="row wrap"><button class="small secondary" data-act="fit-height" title="文字量から高さを求める">内容に合わせる</button><button class="small secondary" data-act="delete">削除</button><button class="small secondary" data-act="duplicate">複製</button><button class="small secondary" data-act="z-up" title="前面へ">前面</button><button class="small secondary" data-act="z-down" title="背面へ">背面</button></div>';
    if (el.type === "text" || el.type === "shape") {
      var r0 = firstRun(el);
      html += '<textarea data-prop="text" title="1 行 = 1 段落。書式は元の段落のものを保ちます。">' + esc(elementText(el)) + "</textarea>";
      html += '<div class="grid4">' + field("役割", selectInput("role", el.role, ROLES, true)) + field("フォント pt", numberInput("font_pt", explicitSize(el), 0.5, 'placeholder="' + esc(num(el.font_pt)) + '"')) + field("太字", '<input type="checkbox" data-prop="bold"' + (r0.bold ? " checked" : "") + ">") + field("文字色", colorInput("color", r0.color, true)) + "</div>";
      html += '<div class="grid4">' + field("揃え", selectInput("align", (el.paragraphs && el.paragraphs[0] && el.paragraphs[0].align) || "", [["left", "左"], ["center", "中央"], ["right", "右"], ["justify", "両端"]], true)) + field("縦位置", selectInput("vertical_align", el.vertical_align || "", [["top", "上"], ["middle", "中央"], ["bottom", "下"]], true)) + field("塗り", colorInput("fill", el.fill, true)) + (el.type === "shape" ? field("図形", selectInput("shape", el.shape || "rect", SHAPES)) : field("縮小", '<button type="button" class="small secondary" data-act="reset-scale"' + (el.font_scale ? "" : " disabled") + ">自動縮小を解除</button>")) + "</div>";
      if (el.type === "shape") html += '<div class="grid4">' + field("線の色", colorInput("stroke", el.stroke, true)) + field("線の太さ", numberInput("stroke_width_pt", el.stroke_width_pt, 0.5)) + "</div>";
    } else if (el.type === "image") {
      var asset = core().state.presentation.assets[el.asset_id] || null;
      html += '<div class="grid4">' + field("代替テキスト", '<input type="text" data-prop="alt" value="' + esc(el.alt || "") + '">', "span2") + field("収め方", selectInput("fit", el.fit || "contain", [["contain", "枠内に収める"], ["cover", "枠を埋める"], ["stretch", "引き伸ばす"]])) + field("回転", numberInput("rotation_deg", el.rotation_deg || 0, 1)) + "</div>";
      html += '<div class="row wrap"><label class="file-btn small secondary">画像を差し替え<input type="file" accept="image/*" data-prop="image-file" hidden></label>' + (asset && asset.width_px ? '<button class="small secondary" data-act="natural-size">実寸に戻す (' + asset.width_px + "×" + asset.height_px + " px)</button>" : "") + (el.placeholder ? '<span class="muted">取得できなかった画像の代替枠です</span>' : "") + "</div>";
    } else if (el.type === "table") {
      html += '<textarea data-prop="table" title="タブ区切りでセル、改行で行">' + esc(elementText(el)) + "</textarea>";
      html += '<div class="grid4">' + field("見出し行数", numberInput("header_rows", el.header_rows == null ? 1 : el.header_rows, 1)) + "</div>";
    } else if (el.type === "diagram") {
      var d = el.diagram || { type: "flow", items: [] };
      html += '<div class="grid4">' + field("型", selectInput("diagram.type", d.type || "flow", DIAGRAM_TYPES)) + field("項目", '<span class="muted">' + (d.items || []).length + " 件</span>") + "</div>";
      html += '<div class="diagram-items">';
      (d.items || []).forEach(function (it, i) {
        html += '<div class="diagram-item"><input type="text" data-prop="diagram.item.' + i + '.title" value="' + esc(it.title || "") + '" placeholder="見出し">'
          + (d.type === "kpi" ? '<input type="text" data-prop="diagram.item.' + i + '.value" value="' + esc(it.value || "") + '" placeholder="値">' : "")
          + '<input type="text" data-prop="diagram.item.' + i + '.text" value="' + esc(it.text || "") + '" placeholder="説明">'
          + '<button class="small secondary" data-act="diagram-up" data-index="' + i + '" title="上へ">↑</button>'
          + '<button class="small secondary" data-act="diagram-del" data-index="' + i + '" title="削除">✕</button></div>';
      });
      html += "</div>";
      html += '<div class="row wrap"><button class="small secondary" data-act="diagram-add">項目を追加</button><span class="muted">Copilot には「型: ' + esc(DIAGRAM_WORDS[d.type] || d.type) + '」として渡ります。</span></div>';
    } else if (el.type === "line") {
      html += '<div class="grid4">' + field("線の色", colorInput("stroke", el.stroke, true)) + field("線の太さ", numberInput("stroke_width_pt", el.stroke_width_pt || 1, 0.5)) + "</div>";
    } else {
      html += '<p class="muted">' + esc(el.alt || "編集対象外の要素") + "</p>";
    }
    return html;
  }

  function renderSlide(s) {
    var bg = s.background || {};
    var html = '<div class="insp-head"><span>スライド ' + (s.index + 1) + (s.continuation_of ? ' <span class="pill">続き</span>' : "") + '</span><span class="muted">' + esc(s.layout || "") + "</span></div>";
    html += '<p class="muted">プレビュー上の要素をクリックすると選択、ドラッグで移動、角で大きさ変更（Shift: 比率固定、Alt: スナップ無効）。矢印キーで微調整、Delete で削除、Ctrl+D で複製、Ctrl+Z / Y で取り消し・やり直し。</p>';
    html += '<div class="grid4">' + field("背景色", colorInput("slide.background.color", bg.color, true)) + field("文字色（既定）", colorInput("slide.background.text_color", bg.text_color, true)) + field("種別", selectInput("slide.layout", s.layout || "title_body", [["title", "表紙"], ["section", "区切り"], ["title_body", "題名+本文"], ["two_column", "2 列"], ["three_column", "3 列"], ["image", "画像"], ["table", "表"], ["blank", "白紙"], ["closing", "最終ページ"]])) + "</div>";
    html += '<label class="f"><span>ノート</span><textarea data-prop="slide.notes">' + esc(s.notes || "") + "</textarea></label>";
    return html;
  }

  var DIAGRAM_TYPES = [["flow", "フロー"], ["cards", "カード"], ["compare", "比較"], ["kpi", "数値"], ["timeline", "年表"]];
  var DIAGRAM_WORDS = { flow: "フロー", cards: "カード", compare: "比較", kpi: "数値", timeline: "年表" };

  function typeLabel(el) { return { text: "文字", shape: "図形", image: "画像", table: "表", line: "線", diagram: "図解", unsupported: "未対応" }[el.type] || el.type; }
  function explicitSize(el) {
    var sizes = [];
    (el.paragraphs || []).forEach(function (p) { (p.runs || []).forEach(function (r) { if (r.size_pt && (r.inherited || []).indexOf("size_pt") < 0) sizes.push(r.size_pt); }); });
    return sizes.length ? Math.max.apply(null, sizes) : null;
  }

  // ---------------------------------------------------------------- 変更の反映
  function onChange(e) {
    var t = e.target;
    var prop = t.getAttribute("data-prop");
    if (!prop) return;
    var s = slide();
    if (!s) return;
    var before = JSON.parse(JSON.stringify(core().state.presentation));
    if (prop.indexOf("slide.") === 0) { applySlideProp(s, prop.slice(6), t); core().changed({ index: core().state.selectedSlide, before: before }); return; }
    var el = selectedElement();
    if (!el) return;
    if (prop === "image-file") { replaceImage(el, t.files[0], before); t.value = ""; return; }
    applyElementProp(el, prop, t);
    core().changed({ index: core().state.selectedSlide, before: before, elementIds: [el.id] });
  }

  function applySlideProp(s, key, t) {
    if (key === "notes") { s.notes = t.value || null; return; }
    if (key === "layout") { s.layout = t.value; return; }
    if (key === "background.color" || key === "background.text_color") {
      s.background = s.background || {};
      s.background[key.split(".")[1]] = t.value.toUpperCase();
      if (!s.background.color) delete s.background.color;
      if (!Object.keys(s.background).length) s.background = null;
    }
  }

  function applyElementProp(el, prop, t) {
    var v = t.type === "checkbox" ? t.checked : t.value;
    if (prop.indexOf("bbox.") === 0) { el.bbox = el.bbox || { x: 0, y: 0, w: 100, h: 40 }; var n = parseFloat(v); if (!isNaN(n)) { el.bbox[prop.slice(5)] = Math.round(n * 10) / 10; el.user_bbox = true; } return; }
    if (prop === "text") { setText(el, v); return; }
    if (prop === "table") { el.rows = v.split("\n").map(function (line, r) { return line.split("\t").map(function (txt, c) { var oldc = (el.rows && el.rows[r] && el.rows[r][c]) || {}; var nc = {}; for (var k in oldc) nc[k] = oldc[k]; nc.text = txt; return nc; }); }); return; }
    if (prop === "role") { el.role = v || null; return; }
    if (prop === "font_pt") { setRuns(el, function (r) { if (v === "") { delete r.size_pt; r.inherited = (r.inherited || []).filter(function (k) { return k !== "size_pt"; }); } else { r.size_pt = parseFloat(v); r.inherited = (r.inherited || []).filter(function (k) { return k !== "size_pt"; }); } }); if (v !== "") el.font_pt = parseFloat(v); return; }
    if (prop === "bold") { setRuns(el, function (r) { r.bold = !!v; r.inherited = (r.inherited || []).filter(function (k) { return k !== "bold"; }); }); return; }
    if (prop === "color") { setRuns(el, function (r) { r.color = String(v).toUpperCase(); r.inherited = (r.inherited || []).filter(function (k) { return k !== "color"; }); }); return; }
    if (prop === "align") { (el.paragraphs || []).forEach(function (p) { if (v) p.align = v; else delete p.align; }); return; }
    if (prop === "vertical_align") { if (v) el.vertical_align = v; else delete el.vertical_align; return; }
    if (prop === "fill" || prop === "stroke") { el[prop] = String(v).toUpperCase(); return; }
    if (prop === "stroke_width_pt" || prop === "rotation_deg" || prop === "header_rows") { var f = parseFloat(v); if (!isNaN(f)) el[prop] = prop === "header_rows" ? Math.max(0, Math.round(f)) : f; if (prop === "rotation_deg" && !f) delete el.rotation_deg; return; }
    if (prop === "shape" || prop === "fit" || prop === "alt") { el[prop] = v; return; }
    if (prop === "diagram.type") { el.diagram = el.diagram || { items: [] }; el.diagram.type = v; return; }
    if (prop.indexOf("diagram.item.") === 0) {
      var parts = prop.split(".");
      var it = (el.diagram && el.diagram.items && el.diagram.items[parseInt(parts[2], 10)]) || null;
      if (it) it[parts[3]] = v;
      return;
    }
  }
  function setRuns(el, fn) { (el.paragraphs || []).forEach(function (p) { (p.runs || []).forEach(fn); }); }
  function setText(el, value) {
    var old = el.paragraphs || [];
    el.paragraphs = value.split("\n").map(function (line, k) {
      var base = old[k] || old[old.length - 1] || { runs: [{ text: "" }], level: 0, bullet: null };
      var run0 = (base.runs && base.runs[0]) ? base.runs[0] : {};
      var nr = {}; for (var key in run0) if (key !== "text") nr[key] = run0[key];
      nr.text = line;
      var p = { runs: [nr], level: base.level || 0, bullet: base.bullet || null };
      if (base.align) p.align = base.align;
      return p;
    });
  }

  function replaceImage(el, file, before) {
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      var dataUrl = String(reader.result);
      var m = /^data:([^;]+);base64,(.*)$/.exec(dataUrl);
      if (!m) return;
      var img = new Image();
      img.onload = function () {
        var pres = core().state.presentation;
        var id = "img_u" + Date.now().toString(36);
        pres.assets[id] = { mime: m[1], filename: id + "." + (m[1].split("/")[1] || "png"), data_base64: m[2], width_px: img.naturalWidth, height_px: img.naturalHeight };
        el.asset_id = id; delete el.placeholder;
        if (el.bbox && img.naturalWidth) { var w = el.bbox.w; el.bbox.h = Math.round(w * img.naturalHeight / img.naturalWidth * 10) / 10; }
        core().changed({ index: core().state.selectedSlide, before: before, elementIds: [el.id] });
      };
      img.src = dataUrl;
    };
    reader.readAsDataURL(file);
  }

  function onClick(e) {
    var btn = e.target.closest("[data-act]");
    if (!btn) return;
    var act = btn.getAttribute("data-act");
    var ids = PWB.canvas.getSelection();
    var el = selectedElement();
    var s = slide();
    if (el && el.type === "diagram" && act.indexOf("diagram-") === 0) {
      var before0 = JSON.parse(JSON.stringify(core().state.presentation));
      el.diagram = el.diagram || { type: "flow", items: [] };
      var items = el.diagram.items = el.diagram.items || [];
      var idx = parseInt(btn.getAttribute("data-index") || "0", 10);
      if (act === "diagram-add") items.push({ title: "見出し", text: "" });
      else if (act === "diagram-del") items.splice(idx, 1);
      else if (act === "diagram-up" && idx > 0) items.splice(idx - 1, 0, items.splice(idx, 1)[0]);
      core().changed({ index: core().state.selectedSlide, before: before0, elementIds: [el.id] });
      render();
      return;
    }
    if (act === "delete") { core().deleteElements(ids); return; }
    if (act === "duplicate") { core().duplicateElements(ids); return; }
    if (act === "z-up" || act === "z-down") { core().reorderZ(ids, act === "z-up" ? 1 : -1); return; }
    if (act === "clear-prop" && el) {
      var before = JSON.parse(JSON.stringify(core().state.presentation));
      var prop = btn.getAttribute("data-prop");
      if (prop === "color") setRuns(el, function (r) { delete r.color; });
      else if (prop.indexOf("slide.") === 0) { if (s.background) { delete s.background[prop.split(".")[2]]; if (!Object.keys(s.background).length) s.background = null; } }
      else el[prop] = null;
      core().changed({ index: core().state.selectedSlide, before: before, elementIds: [el.id] });
      return;
    }
    if (act === "clear-prop" && s) {
      var b2 = JSON.parse(JSON.stringify(core().state.presentation));
      var p2 = btn.getAttribute("data-prop").split(".")[2];
      if (s.background) { delete s.background[p2]; if (!Object.keys(s.background).length) s.background = null; }
      core().changed({ index: core().state.selectedSlide, before: b2 });
      return;
    }
    if (act === "reset-scale" && el) { var b3 = JSON.parse(JSON.stringify(core().state.presentation)); delete el.font_scale; core().changed({ index: core().state.selectedSlide, before: b3, elementIds: [el.id] }); return; }
    if (act === "fit-height" && el) { core().fitHeight(el.id); return; }
    if (act === "natural-size" && el) {
      var asset = core().state.presentation.assets[el.asset_id];
      if (!asset || !asset.width_px || !el.bbox) return;
      var b4 = JSON.parse(JSON.stringify(core().state.presentation));
      var cw = core().state.presentation.canvas.width_pt, ch = core().state.presentation.canvas.height_pt;
      var w = Math.min(asset.width_px * 0.75, cw - 2 * 36), h = w * asset.height_px / asset.width_px;
      if (h > ch * 0.8) { h = ch * 0.8; w = h * asset.width_px / asset.height_px; }
      el.bbox.w = Math.round(w * 10) / 10; el.bbox.h = Math.round(h * 10) / 10; el.user_bbox = true;
      core().changed({ index: core().state.selectedSlide, before: b4, elementIds: [el.id] });
      return;
    }
    if (act === "align-left" || act === "align-top" || act === "same-width") { core().alignSelection(ids, act); }
  }

  function focusText() { var ta = root && root.querySelector('textarea[data-prop="text"], textarea[data-prop="table"]'); if (ta) { ta.focus(); ta.select(); } }

  return { init: init, render: render, focusText: focusText };
})();
