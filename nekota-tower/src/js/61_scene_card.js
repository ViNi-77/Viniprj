/* メモリーカード画面。本体メモリのきろくを暗号化CSVに書き出し／読み込み */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input, TX = function () { return NT.DATA.TEXT.card; };
  var C = NT.Card = {};
  var fileInput = null, dropzone = null;

  function ensureDom() {
    var ov = document.getElementById("overlay");
    if (!fileInput) {
      fileInput = document.createElement("input");
      fileInput.type = "file"; fileInput.id = "filepick"; fileInput.accept = ".csv,text/csv,text/plain";
      fileInput.setAttribute("aria-label", "メモリーカードを選ぶ");
      ov.appendChild(fileInput);
      fileInput.addEventListener("change", function () {
        var f = fileInput.files && fileInput.files[0];
        fileInput.value = "";
        if (f) C.importFile(f);
      });
    }
    if (!dropzone) {
      dropzone = document.createElement("div");
      dropzone.id = "dropzone"; dropzone.textContent = TX().drop;
      ov.appendChild(dropzone);
    }
  }
  C.installDrop = function () {
    ensureDom();
    var count = 0;
    window.addEventListener("dragenter", function (e) { e.preventDefault(); count++; dropzone.classList.add("show"); });
    window.addEventListener("dragover", function (e) { e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = "copy"; });
    window.addEventListener("dragleave", function (e) { e.preventDefault(); count = Math.max(0, count - 1); if (!count) dropzone.classList.remove("show"); });
    window.addEventListener("drop", function (e) {
      e.preventDefault(); count = 0; dropzone.classList.remove("show");
      var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) C.importFile(f);
    });
  };
  C.pickFile = function () { ensureDom(); fileInput.click(); };

  /* ---- 書き出し ---- */
  C.download = function (text, name) {
    var blob = new Blob([text], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = name; a.style.display = "none";
    document.body.appendChild(a); a.click();
    setTimeout(function () { document.body.removeChild(a); URL.revokeObjectURL(url); }, 1000);
  };
  C.exportSlot = function (n, password) {
    var r = NT.Storage.readSlot(n);
    if (!r || !r.rec) return Promise.reject(new Error("empty"));
    return NT.Codec.encodeCard([{ slot: n, record: r.rec }], { password: password || undefined }).then(function (csv) {
      var name = NT.Codec.fileName(n, new Date(NT.Time.now()));
      C.download(csv, name);
      C.lastExport = { name: name, csv: csv };
      return name;
    });
  };
  /* ---- 読み込み ---- */
  C.importText = function (text, password) {
    return NT.Codec.decodeCard(text, { password: password || undefined });
  };
  C.importFile = function (file) {
    var scene = NT.Scenes.find("CARD");
    file.text().then(function (text) {
      C.pendingText = text;
      if (scene) scene.onFileText(text); else NT.Flow.openCard(text);
    }).catch(function () { NT.Scenes.push(NT.Notice(TX().bad)); });
  };

  /* ---- 画面 ---- */
  NT.SceneCard = function (opts) {
    opts = opts || {};
    var menu = null, status = "", statusColor = "#9aa0b4", busy = false;
    function setStatus(s, col) { status = s; statusColor = col || "#9aa0b4"; }
    function askPassword(title, cb) {
      NT.InputBox.open({ x: 24, y: 70, w: 272, maxLen: 32, title: title, hint: "なしなら そのまま Enter", onDone: function (v) { cb(v); } });
    }
    function doExport() {
      if (!NT.Codec.isSupported()) { setStatus(TX().unsupported, "#f4afc4"); NT.Audio.play("error"); return; }
      var items = [];
      for (var n = 1; n <= 3; n++) { var r = NT.Storage.readSlot(n); items.push({ label: "きろく " + n + (r && r.rec ? "　" + r.rec.state.name : "　" + NT.DATA.TEXT.slot.empty), value: n, disabled: !(r && r.rec) }); }
      if (NT.State.cur && NT.State.dirty) items.unshift({ label: "いまの状態を そのまま", value: 0 });
      items.push({ label: NT.DATA.TEXT.menu.back, value: -1 });
      NT.Scenes.push(NT.Menu({ title: TX().choose, w: 230, items: items, onSelect: function (it) {
        NT.Scenes.pop();
        if (it.value < 0) return;
        askPassword(TX().passPrompt, function (pw) {
          if (pw === null) return;
          var go = function (pw2) {
            busy = true;
            var p;
            if (it.value === 0) {
              var rec = NT.State.toRecord();
              p = NT.Codec.encodeCard([{ slot: NT.State.slot || 1, record: rec }], { password: pw2 || undefined }).then(function (csv) {
                var name = NT.Codec.fileName(NT.State.slot || 1, new Date(NT.Time.now())); C.download(csv, name); C.lastExport = { name: name, csv: csv }; return name;
              });
            } else p = C.exportSlot(it.value, pw2);
            p.then(function (name) { busy = false; setStatus(NT.Util.fmt(TX().exported, { file: name }), "#7dffb0"); NT.Audio.play("save"); })
             .catch(function () { busy = false; setStatus(TX().bad, "#f4afc4"); NT.Audio.play("error"); });
          };
          if (pw) askPassword(TX().passAgain, function (pw2) { if (pw2 === null) return; if (pw2 !== pw) { setStatus(TX().passMismatch, "#f4afc4"); NT.Audio.play("error"); return; } go(pw); });
          else go("");
        });
      } }));
    }
    function doImport() {
      if (!NT.Codec.isSupported()) { setStatus(TX().unsupported, "#f4afc4"); NT.Audio.play("error"); return; }
      setStatus(TX().drop + "、または ファイルを えらぶ");
      C.pickFile();
    }
    function onFileText(text) {
      busy = true;
      var tryDecode = function (pw) {
        C.importText(text, pw).then(function (entries) {
          busy = false;
          if (!entries.length) throw new Error("empty");
          var e = entries[0];
          var migrated = NT.Storage.migrate(e.record);
          if (!migrated || migrated.tooNew) { setStatus(TX().bad, "#f4afc4"); NT.Audio.play("error"); return; }
          var items = [];
          for (var n = 1; n <= 3; n++) { var r = NT.Storage.readSlot(n); items.push({ label: "きろく " + n + (r && r.rec ? "　" + r.rec.state.name : "　" + NT.DATA.TEXT.slot.empty), value: n }); }
          items.push({ label: NT.DATA.TEXT.menu.back, value: -1 });
          NT.Scenes.push(NT.Menu({ title: TX().toSlot + "（" + migrated.rec.state.name + "）", w: 240, items: items, onSelect: function (it) {
            NT.Scenes.pop();
            if (it.value < 0) return;
            var write = function () {
              var ok = NT.Storage.writeSlot(it.value, migrated.rec);
              setStatus(ok ? TX().imported + "（きろく " + it.value + "）" : NT.DATA.TEXT.save.fail, ok ? "#7dffb0" : "#f4afc4");
              NT.Audio.play(ok ? "save" : "error");
              C.lastImport = { slot: it.value, rec: migrated.rec };
            };
            var r = NT.Storage.readSlot(it.value);
            if (r && r.rec) NT.Scenes.push(NT.Confirm(NT.Util.fmt(NT.DATA.TEXT.slot.overwrite, { n: it.value }), write)); else write();
          } }));
        }).catch(function (err) {
          busy = false;
          if (err && err.code === "auth" && pw === undefined) {
            /* あいことば付きかもしれないので一度だけ聞く */
            askPassword(TX().passPrompt, function (v) { if (v === null || v === "") { setStatus(TX().bad, "#f4afc4"); NT.Audio.play("error"); return; } busy = true; tryDecode(v); });
            return;
          }
          setStatus(TX().bad, "#f4afc4"); NT.Audio.play("error");
        });
      };
      tryDecode(undefined);
    }
    function openMenu() {
      menu = NT.Menu({ x: 40, y: 56, w: 240, items: [
        { label: TX().export, value: "export" },
        { label: TX().import, value: "import" },
        { label: NT.DATA.TEXT.menu.back, value: "back" }
      ], cancelable: true, onSelect: function (it) {
        if (it.value === "back") { NT.Scenes.pop(); NT.Scenes.pop(); return; }
        if (busy) return;
        if (it.value === "export") doExport(); else doImport();
      }, onCancel: function () { NT.Scenes.pop(); NT.Scenes.pop(); } });
      menu.id = "CARDMENU";
      NT.Scenes.push(menu);
    }
    var scene = {
      id: "CARD", opaque: true,
      enter: function () { C.installDrop(); openMenu(); if (opts.pendingText) setTimeout(function () { onFileText(opts.pendingText); }, 0); },
      resume: function (res, popped) { if (!NT.Scenes.has("CARDMENU") && NT.Scenes.top() === scene) openMenu(); },
      update: function () {},
      draw: function (ctx) {
        NT.Screen.clear("#070716");
        T.drawCenter(ctx, TX().title, NT.W / 2, 14, "#f4d03f", { head: true, size: 16 });
        /* カードの絵 */
        G.frame(ctx, 110, 120, 100, 60, { fill: "#1d1b3a", border: "#9aa0b4" });
        ctx.fillStyle = "#f4d03f"; ctx.fillRect(118, 128, 24, 14);
        T.draw(ctx, "NETTA", 150, 129, "#f4f1e8"); T.draw(ctx, "CARD", 150, 143, "#9aa0b4");
        T.draw(ctx, "かな で かかれた きろく", 118, 160, "#5b5a66");
        var lines = T.wrap(status || NT.DATA.TEXT.save.memoryNote, 288);
        T.drawLines(ctx, lines, 16, 190, statusColor);
        if (busy) T.drawCenter(ctx, NT.DATA.TEXT.sys.loading + "…", NT.W / 2, 100, "#9aa0b4");
        NT.InputBox.draw(ctx);
      },
      onFileText: onFileText,
      status: function () { return status; }
    };
    return scene;
  };
  NT.Flow = NT.Flow || {};
  NT.Flow.openCard = function (pendingText) { NT.Scenes.push(NT.SceneCard({ pendingText: pendingText })); };
})();
