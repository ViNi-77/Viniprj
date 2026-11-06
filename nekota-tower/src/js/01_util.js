/* 小さな共通関数 */
(function () {
  "use strict";
  var NT = window.NT;
  var U = NT.Util = {};

  U.clamp = function (v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; };
  U.lerp = function (a, b, t) { return a + (b - a) * t; };
  U.easeInOut = function (t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };
  U.easeOut = function (t) { return 1 - (1 - t) * (1 - t); };
  U.sign = function (v) { return v > 0 ? 1 : v < 0 ? -1 : 0; };
  U.pad2 = function (n) { return (n < 10 ? "0" : "") + n; };

  /* 乱数（再現性のため種あり。演出用途のみ） */
  U.rng = function (seed) {
    var s = (seed >>> 0) || 0x9e3779b9;
    return function () {
      s += 0x6D2B79F5; s >>>= 0;
      var t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };

  U.deepClone = function (o) { return JSON.parse(JSON.stringify(o)); };
  U.assign = function (dst, src) { for (var k in src) if (Object.prototype.hasOwnProperty.call(src, k)) dst[k] = src[k]; return dst; };

  /* 文字数（書記素）。Intl.Segmenter が無ければコードポイント数 */
  var seg = (typeof Intl !== "undefined" && Intl.Segmenter) ? new Intl.Segmenter("ja", { granularity: "grapheme" }) : null;
  U.graphemes = function (s) {
    if (!s) return [];
    if (seg) { var out = []; for (var g of seg.segment(s)) out.push(g.segment); return out; }
    return Array.from(s);
  };
  U.gLen = function (s) { return U.graphemes(s).length; };
  U.gSlice = function (s, n) { return U.graphemes(s).slice(0, n).join(""); };

  /* 文字列テンプレート {key} 置換 */
  U.fmt = function (s, vars) {
    if (!vars) return s;
    return String(s).replace(/\{(\w+)\}/g, function (m, k) { return (k in vars) ? String(vars[k]) : m; });
  };

  U.uid = function () { return Date.now().toString(36) + Math.random().toString(36).slice(2, 7); };

  U.escapeHtml = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  };
})();
