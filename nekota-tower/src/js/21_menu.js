/* 汎用カーソルメニュー（オーバーレイ）。items: [{label, value, disabled, note}] */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input;

  /* opts: {x,y,w, title, items, index, cancelable, onSelect(item,index), onCancel(), onChange(item), draw(ctx) 追加描画, compact, cols} */
  NT.Menu = function (opts) {
    var m = {
      id: "MENU", opaque: false,
      x: opts.x, y: opts.y, w: opts.w || 120,
      items: opts.items || [],
      index: opts.index || 0,
      cancelable: opts.cancelable !== false,
      title: opts.title || null,
      lh: opts.lh || 16,
      pad: 10
    };
    var rows = m.items.length + (m.title ? 1 : 0);
    m.h = opts.h || (rows * m.lh + m.pad * 2 - 2);
    if (m.x === undefined) m.x = Math.round((NT.W - m.w) / 2);
    if (m.y === undefined) m.y = Math.round((NT.H - m.h) / 2);
    m.rowY = function (i) { return m.y + m.pad + (m.title ? m.lh : 0) + i * m.lh - 2; };

    function move(d) {
      var n = m.items.length; if (!n) return;
      var i = m.index, guard = 0;
      do { i = (i + d + n) % n; guard++; } while (m.items[i].disabled && guard <= n);
      if (i !== m.index) { m.index = i; NT.Audio.play("cursor"); if (opts.onChange) opts.onChange(m.items[i], i); }
    }
    m.select = function () {
      var it = m.items[m.index];
      if (!it || it.disabled) { NT.Audio.play("error"); return; }
      NT.Audio.play(it.sfx || "decide");
      if (opts.onSelect) opts.onSelect(it, m.index, m);
    };
    m.cancel = function () {
      if (!m.cancelable) return;
      NT.Audio.play("cancel");
      if (opts.onCancel) opts.onCancel(m); else NT.Scenes.pop(null);
    };
    m.update = function () {
      if (I.pressed("up")) move(-1);
      if (I.pressed("down")) move(1);
      if (I.pressed("ok")) { I.consume("ok"); m.select(); return; }
      if (I.pressed("cancel")) { I.consume("cancel"); m.cancel(); return; }
      var cl = I.clicks();
      for (var k = 0; k < cl.length; k++) {
        var c = cl[k];
        for (var i = 0; i < m.items.length; i++) {
          var ry = m.rowY(i);
          if (c.x >= m.x && c.x < m.x + m.w && c.y >= ry - 2 && c.y < ry + m.lh - 2) {
            if (m.index !== i) { m.index = i; if (opts.onChange) opts.onChange(m.items[i], i); }
            m.select(); return;
          }
        }
        if (m.cancelable && (c.x < m.x || c.x >= m.x + m.w || c.y < m.y || c.y >= m.y + m.h)) { m.cancel(); return; }
      }
    };
    m.draw = function (ctx) {
      G.frame(ctx, m.x, m.y, m.w, m.h);
      var ty = m.y + m.pad - 2;
      if (m.title) { T.draw(ctx, m.title, m.x + m.pad, ty, "#f4d03f"); }
      for (var i = 0; i < m.items.length; i++) {
        var it = m.items[i], ry = m.rowY(i);
        var col = it.disabled ? "#5b5a66" : (it.color || "#f4f1e8");
        T.draw(ctx, it.label, m.x + m.pad + 10, ry, col);
        if (it.note) T.drawRight(ctx, it.note, m.x + m.w - m.pad, ry, it.disabled ? "#5b5a66" : "#9aa0b4");
        if (i === m.index) G.cursor(ctx, m.x + m.pad + 1, ry + 1, "#f4d03f");
      }
      if (opts.draw) opts.draw(ctx, m);
    };
    return m;
  };

  /* はい／いいえ の確認。onYes/onNo */
  NT.Confirm = function (text, onYes, onNo, opts) {
    opts = opts || {};
    var lines = T.wrap(text, 240);
    var h = lines.length * 16 + 16 * 2 + 24;
    var w = 264, x = Math.round((NT.W - w) / 2), y = opts.y !== undefined ? opts.y : Math.round((NT.H - h) / 2);
    var items = [{ label: opts.noLabel || "いいえ", value: false }, { label: opts.yesLabel || "はい", value: true }];
    if (opts.yesFirst) items.reverse();
    var m = NT.Menu({
      x: x, y: y, w: w, h: h, items: items, index: opts.defaultYes ? items.findIndex(function (i) { return i.value; }) : items.findIndex(function (i) { return !i.value; }),
      cancelable: opts.cancelable !== false,
      onSelect: function (it) { NT.Scenes.pop(it.value); if (it.value) { if (onYes) onYes(); } else if (onNo) onNo(); },
      onCancel: function () { NT.Scenes.pop(false); if (onNo) onNo(); }
    });
    m.id = "CONFIRM";
    m.rowY = function (i) { return y + 10 + lines.length * 16 + 8 + i * 16; };
    var baseDraw = m.draw;
    m.draw = function (ctx) {
      G.frame(ctx, x, y, w, h);
      T.drawLines(ctx, lines, x + 12, y + 10, "#f4f1e8");
      for (var i = 0; i < items.length; i++) {
        var ry = m.rowY(i);
        T.draw(ctx, items[i].label, x + 12 + 10, ry, "#f4f1e8");
        if (i === m.index) G.cursor(ctx, x + 12 + 1, ry + 1, "#f4d03f");
      }
      void baseDraw;
    };
    return m;
  };

  /* 1行メッセージ（OK で閉じる）*/
  NT.Notice = function (text, onClose, opts) {
    opts = opts || {};
    var lines = T.wrap(text, 272);
    var h = lines.length * 16 + 24, w = 296, x = 12, y = opts.y !== undefined ? opts.y : NT.H - h - 10;
    var t = 0;
    return {
      id: "NOTICE", opaque: false,
      update: function (dt) {
        t += dt;
        if (I.pressed("ok") || I.pressed("cancel") || I.clicks().length) { I.consume("ok"); I.consume("cancel"); NT.Scenes.pop(); if (onClose) onClose(); }
      },
      draw: function (ctx) {
        G.frame(ctx, x, y, w, h);
        T.drawLines(ctx, lines, x + 12, y + 10, opts.color || "#f4f1e8");
        if ((t % 1000) < 500) G.nextMark(ctx, x + w - 16, y + h - 9, "#f4d03f");
      }
    };
  };
})();
