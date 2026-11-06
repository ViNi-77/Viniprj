/* 文字描画。全角 12px / 半角 6px の固定ピッチで、折り返しと禁則を自前で行う */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text = {};
  T.FULL = 12; T.HALF = 6; T.LH = 16;
  var HALF_RE = /[ -~｡-ﾟ]/;
  var NO_HEAD = "、。，．・：；？！ー）」』】〕〉》〙〗〟’”｝〉ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ々〻–〜~!?,.:;)]}";
  var NO_TAIL = "（「『【〔〈《〘〖〝‘“｛([{";
  var HANG = "、。，．,.";

  T.isHalf = function (ch) { return HALF_RE.test(ch); };
  T.width = function (ch) { return T.isHalf(ch) ? T.HALF : T.FULL; };
  T.measure = function (s) { var w = 0; for (var i = 0; i < s.length; i++) w += T.width(s[i]); return w; };

  /* 文字列を幅 maxW(px) に収まる行に分ける。'\n' は強制改行 */
  T.wrap = function (text, maxW) {
    var lines = [];
    String(text).split("\n").forEach(function (para) {
      var chars = Array.from(para);
      var line = "", w = 0;
      for (var i = 0; i < chars.length; i++) {
        var ch = chars[i], cw = T.width(ch);
        if (w + cw > maxW) {
          if (HANG.indexOf(ch) >= 0 && line) { line += ch; lines.push(line); line = ""; w = 0; continue; }
          if (NO_HEAD.indexOf(ch) >= 0 && line.length > 1) {
            var last = line[line.length - 1];
            if (NO_TAIL.indexOf(last) < 0) { line = line.slice(0, -1); lines.push(line); line = last + ch; w = T.width(last) + cw; continue; }
          }
          if (line && NO_TAIL.indexOf(line[line.length - 1]) >= 0) {
            var l2 = line[line.length - 1]; line = line.slice(0, -1); lines.push(line); line = l2 + ch; w = T.width(l2) + cw; continue;
          }
          lines.push(line); line = ch; w = cw; continue;
        }
        line += ch; w += cw;
      }
      lines.push(line);
    });
    return lines;
  };

  T.font = function (ctx, size, head) {
    ctx.font = (size || 12) + "px " + (head ? NT.FONT_HEAD : NT.FONT_BODY);
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
  };

  /* 1行描画（固定ピッチ）。shadow=true で 1px 右下に影 */
  T.draw = function (ctx, s, x, y, color, opts) {
    opts = opts || {};
    T.font(ctx, opts.size || 12, opts.head);
    var cx = x;
    var chars = Array.from(String(s));
    var limit = opts.limit === undefined ? chars.length : opts.limit;
    for (var i = 0; i < chars.length && i < limit; i++) {
      var ch = chars[i], w = T.width(ch);
      if (opts.size && opts.size !== 12) w = w * opts.size / 12;
      if (opts.shadow) { ctx.fillStyle = "#000"; ctx.fillText(ch, cx + 1, y + 1); }
      ctx.fillStyle = color || "#f4f1e8";
      ctx.fillText(ch, cx, y);
      cx += w;
    }
    return cx;
  };
  T.drawCenter = function (ctx, s, cx, y, color, opts) {
    var size = (opts && opts.size) || 12;
    var w = T.measure(String(s)) * size / 12;
    return T.draw(ctx, s, Math.round(cx - w / 2), y, color, opts);
  };
  T.drawRight = function (ctx, s, rx, y, color, opts) {
    var size = (opts && opts.size) || 12;
    var w = T.measure(String(s)) * size / 12;
    return T.draw(ctx, s, Math.round(rx - w), y, color, opts);
  };
  /* 複数行。shown は表示する総文字数（文字送り用。undefined なら全部） */
  T.drawLines = function (ctx, lines, x, y, color, shown, lh) {
    lh = lh || T.LH;
    var remain = shown === undefined ? Infinity : shown;
    for (var i = 0; i < lines.length; i++) {
      var chars = Array.from(lines[i]);
      var n = Math.min(chars.length, remain);
      if (n > 0) T.draw(ctx, lines[i], x, y + i * lh, color, { limit: n });
      remain -= chars.length;
      if (remain <= 0) return { line: i, done: false };
    }
    return { line: lines.length - 1, done: true };
  };
  T.countChars = function (lines) { var n = 0; lines.forEach(function (l) { n += Array.from(l).length; }); return n; };
})();
