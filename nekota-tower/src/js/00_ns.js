/* 名前空間と定数。全モジュールはこの NT にぶら下がる */
(function () {
  "use strict";
  var NT = window.NT = window.NT || {};
  NT.W = 320;            // 内部解像度（幅）
  NT.H = 240;            // 内部解像度（高さ）
  NT.TILE = 16;          // タイル1辺
  NT.STEP = 1000 / 60;   // 固定ステップ（ms）
  NT.BUILD = "{{BUILD}}";
  NT.APP = "nekota-tower";
  NT.SAVE_VERSION = 1;
  NT.DATA = NT.DATA || {};
  NT.SVG = NT.SVG || {};
  NT.FONT_BODY = '"PM12","MS Gothic","Yu Gothic","Hiragino Kaku Gothic ProN",monospace';
  NT.FONT_HEAD = '"DG16","PM12","MS Gothic","Yu Gothic",monospace';
  NT.debug = /[?&]debug=1/.test(location.search);
  NT.query = {};
  location.search.replace(/^\?/, "").split("&").forEach(function (kv) {
    if (!kv) return;
    var i = kv.indexOf("=");
    var k = decodeURIComponent(i < 0 ? kv : kv.slice(0, i));
    var v = i < 0 ? "1" : decodeURIComponent(kv.slice(i + 1));
    NT.query[k] = v;
  });
})();
