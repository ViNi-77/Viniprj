/* 枠・カーソル・ゲージ・タイル絵。画像ファイルは使わず、すべて手続きで描く */
(function () {
  "use strict";
  var NT = window.NT;
  var G = NT.Gfx = {};
  var TILE = NT.TILE;

  /* 黒地に白枠の窓 */
  G.frame = function (ctx, x, y, w, h, opts) {
    opts = opts || {};
    ctx.fillStyle = opts.fill || "#000";
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = opts.border || "#f4f1e8";
    ctx.fillRect(x + 1, y + 1, w - 2, 2); ctx.fillRect(x + 1, y + h - 3, w - 2, 2);
    ctx.fillRect(x + 1, y + 1, 2, h - 2); ctx.fillRect(x + w - 3, y + 1, 2, h - 2);
    ctx.fillStyle = opts.fill || "#000";
    ctx.fillRect(x, y, 1, 1); ctx.fillRect(x + w - 1, y, 1, 1); ctx.fillRect(x, y + h - 1, 1, 1); ctx.fillRect(x + w - 1, y + h - 1, 1, 1);
    if (opts.inner !== false) {
      ctx.fillStyle = opts.innerColor || "#6e6a7a";
      ctx.fillRect(x + 4, y + 4, w - 8, 1); ctx.fillRect(x + 4, y + h - 5, w - 8, 1);
      ctx.fillRect(x + 4, y + 4, 1, h - 8); ctx.fillRect(x + w - 5, y + 4, 1, h - 8);
    }
  };
  /* ▶ カーソル */
  G.cursor = function (ctx, x, y, color) {
    ctx.fillStyle = color || "#f4f1e8";
    ctx.fillRect(x, y + 1, 1, 9); ctx.fillRect(x + 1, y + 2, 1, 7); ctx.fillRect(x + 2, y + 3, 1, 5); ctx.fillRect(x + 3, y + 4, 1, 3); ctx.fillRect(x + 4, y + 5, 1, 1);
  };
  /* ▼ 次ページ */
  G.nextMark = function (ctx, x, y, color) {
    ctx.fillStyle = color || "#f4f1e8";
    ctx.fillRect(x, y, 7, 1); ctx.fillRect(x + 1, y + 1, 5, 1); ctx.fillRect(x + 2, y + 2, 3, 1); ctx.fillRect(x + 3, y + 3, 1, 1);
  };
  G.gauge = function (ctx, x, y, w, h, ratio, fg, bg) {
    ctx.fillStyle = bg || "#2a2a33"; ctx.fillRect(x, y, w, h);
    ctx.fillStyle = fg || "#f4d03f"; ctx.fillRect(x + 1, y + 1, Math.round((w - 2) * NT.Util.clamp(ratio, 0, 1)), h - 2);
  };
  G.dither = function (ctx, x, y, w, h, color) {
    ctx.fillStyle = color || "rgba(0,0,0,.5)";
    for (var yy = y; yy < y + h; yy++) for (var xx = x + (yy & 1); xx < x + w; xx += 2) ctx.fillRect(xx, yy, 1, 1);
  };
  G.fade = function (ctx, alpha, color) {
    ctx.fillStyle = "rgba(" + (color || "0,0,0") + "," + NT.Util.clamp(alpha, 0, 1) + ")";
    ctx.fillRect(0, 0, NT.W, NT.H);
  };
  /* 肉球 */
  G.paw = function (ctx, cx, cy, s, color) {
    ctx.fillStyle = color || "#f4d03f";
    s = s || 1;
    ctx.beginPath(); ctx.ellipse(cx, cy + 2 * s, 5 * s, 4 * s, 0, 0, Math.PI * 2); ctx.fill();
    [[-5, -3], [-1.8, -5.5], [1.8, -5.5], [5, -3]].forEach(function (p) {
      ctx.beginPath(); ctx.ellipse(cx + p[0] * s, cy + p[1] * s, 1.9 * s, 2.2 * s, 0, 0, Math.PI * 2); ctx.fill();
    });
  };

  /* タイルセット。インデックスは 40_tilemap.js と共有 */
  G.T = { FLOOR: 0, WALL: 1, WALLTOP: 2, STAIRS_DOWN: 3, STAIRS_UP: 4, ELEVATOR: 5, STONE: 6, DOOR: 7, DOOR_OPEN: 8, SHELF: 9, WINDOW: 10, CARPET: 11, FLOWER_POT: 12, FLOWER: 13, VOID: 14, ELEVATOR_SHAFT: 15 };
  var tilesets = {};
  /* palette: [dark, mid, light, bright] */
  G.tileset = function (floor, palette) {
    var k = floor + ":" + palette.join(",");
    if (tilesets[k]) return tilesets[k];
    var N = 16, cv = document.createElement("canvas");
    cv.width = TILE * N; cv.height = TILE;
    var c = cv.getContext("2d");
    var dark = palette[0], mid = palette[1], light = palette[2], bright = palette[3];
    var rnd = NT.Util.rng(floor * 7919 + 13);
    function at(i) { return i * TILE; }
    function px(x, y, col) { c.fillStyle = col; c.fillRect(x, y, 1, 1); }
    // FLOOR
    c.fillStyle = mid; c.fillRect(at(0), 0, TILE, TILE);
    for (var i = 0; i < 6; i++) px(at(0) + Math.floor(rnd() * 16), Math.floor(rnd() * 16), light);
    px(at(0) + 3, 12, dark); px(at(0) + 11, 5, dark);
    // WALL（石積み）
    c.fillStyle = dark; c.fillRect(at(1), 0, TILE, TILE);
    c.fillStyle = mid;
    for (var r = 0; r < 4; r++) { var off = (r & 1) ? 4 : 0; for (var b = -1; b < 3; b++) c.fillRect(at(1) + off + b * 8 + 1, r * 4 + 1, 6, 2); }
    // WALLTOP（天井の縁）
    c.fillStyle = light; c.fillRect(at(2), 0, TILE, TILE);
    c.fillStyle = mid; c.fillRect(at(2), 13, TILE, 3);
    c.fillStyle = bright; c.fillRect(at(2), 0, TILE, 1);
    // STAIRS_DOWN / UP
    [3, 4].forEach(function (idx) {
      c.fillStyle = dark; c.fillRect(at(idx), 0, TILE, TILE);
      for (var s = 0; s < 4; s++) { var yy = idx === 3 ? s * 4 : 12 - s * 4; c.fillStyle = light; c.fillRect(at(idx) + 2, yy, 12, 3); c.fillStyle = mid; c.fillRect(at(idx) + 2, yy + 3, 12, 1); }
    });
    // ELEVATOR（扉）
    c.fillStyle = dark; c.fillRect(at(5), 0, TILE, TILE);
    c.fillStyle = bright; c.fillRect(at(5) + 1, 1, 14, 14);
    c.fillStyle = light; c.fillRect(at(5) + 2, 2, 5, 12); c.fillRect(at(5) + 9, 2, 5, 12);
    c.fillStyle = "#f4d03f"; c.fillRect(at(5) + 7, 2, 2, 12);
    // STONE（石碑）
    c.fillStyle = mid; c.fillRect(at(6), 0, TILE, TILE);
    c.fillStyle = "#8a8f9c"; c.fillRect(at(6) + 4, 2, 8, 12); c.fillStyle = "#c9ced8"; c.fillRect(at(6) + 5, 3, 6, 10);
    c.fillStyle = "#f4d03f"; c.fillRect(at(6) + 7, 5, 2, 2); c.fillRect(at(6) + 6, 8, 4, 1); c.fillRect(at(6) + 6, 10, 4, 1);
    c.fillStyle = "#5c6070"; c.fillRect(at(6) + 3, 14, 10, 2);
    // DOOR（閉）
    c.fillStyle = dark; c.fillRect(at(7), 0, TILE, TILE);
    c.fillStyle = "#6b3f1f"; c.fillRect(at(7) + 2, 1, 12, 15);
    c.fillStyle = "#8c5a2b"; c.fillRect(at(7) + 3, 2, 4, 13); c.fillRect(at(7) + 9, 2, 4, 13);
    c.fillStyle = "#f4d03f"; c.fillRect(at(7) + 7, 8, 2, 2);
    // DOOR_OPEN
    c.fillStyle = dark; c.fillRect(at(8), 0, TILE, TILE);
    c.fillStyle = "#fff6d6"; c.fillRect(at(8) + 3, 1, 10, 15);
    c.fillStyle = "#f4d03f"; c.fillRect(at(8) + 5, 3, 6, 11);
    // SHELF
    c.fillStyle = dark; c.fillRect(at(9), 0, TILE, TILE);
    c.fillStyle = "#6b3f1f"; c.fillRect(at(9) + 1, 0, 14, 16);
    ["#c0392b", "#2e86c1", "#27ae60", "#f4d03f", "#8e44ad", "#e67e22"].forEach(function (col, j) { c.fillStyle = col; c.fillRect(at(9) + 2 + (j % 3) * 4, 2 + Math.floor(j / 3) * 7, 3, 5); });
    // WINDOW
    c.fillStyle = dark; c.fillRect(at(10), 0, TILE, TILE);
    c.fillStyle = "#1b2a4a"; c.fillRect(at(10) + 3, 2, 10, 10);
    c.fillStyle = "#f4f1e8"; px(at(10) + 6, 4, "#f4f1e8"); px(at(10) + 10, 7, "#f4f1e8"); px(at(10) + 5, 9, "#f4f1e8");
    c.fillStyle = light; c.fillRect(at(10) + 7, 2, 2, 10); c.fillRect(at(10) + 3, 6, 10, 2);
    // CARPET
    c.fillStyle = "#7a2d3a"; c.fillRect(at(11), 0, TILE, TILE);
    c.fillStyle = "#a33d4e"; c.fillRect(at(11) + 2, 2, 12, 12);
    c.fillStyle = "#f4d03f"; px(at(11) + 7, 7, "#f4d03f"); px(at(11) + 8, 8, "#f4d03f");
    // FLOWER_POT（まだ咲いていない）
    c.fillStyle = mid; c.fillRect(at(12), 0, TILE, TILE);
    c.fillStyle = "#6b3f1f"; c.fillRect(at(12) + 5, 10, 6, 5); c.fillStyle = "#3b6d3a"; c.fillRect(at(12) + 7, 7, 2, 3);
    // FLOWER（咲いた）
    c.fillStyle = mid; c.fillRect(at(13), 0, TILE, TILE);
    c.fillStyle = "#6b3f1f"; c.fillRect(at(13) + 5, 10, 6, 5); c.fillStyle = "#3b6d3a"; c.fillRect(at(13) + 7, 6, 2, 4);
    c.fillStyle = "#f4afc4"; c.fillRect(at(13) + 5, 3, 6, 4); c.fillStyle = "#f4d03f"; c.fillRect(at(13) + 7, 4, 2, 2);
    // VOID
    c.fillStyle = "#000"; c.fillRect(at(14), 0, TILE, TILE);
    // ELEVATOR_SHAFT（縦坑の内壁）
    c.fillStyle = dark; c.fillRect(at(15), 0, TILE, TILE);
    c.fillStyle = mid; c.fillRect(at(15) + 2, 0, 1, 16); c.fillRect(at(15) + 13, 0, 1, 16);
    c.fillStyle = light; c.fillRect(at(15) + 7, 0, 2, 16);
    tilesets[k] = cv;
    return cv;
  };
  G.drawTile = function (ctx, tileset, idx, x, y) {
    ctx.drawImage(tileset, idx * TILE, 0, TILE, TILE, x, y, TILE, TILE);
  };
})();
