/* 年末の塔のマップ。40列×130行。1階＝13行（上壁1・床11・下壁1）。10Fが最上段、1Fが最下段。
   凡例: # 壁  = 壁の上面  . 床  , 絨毯  S 下り階段  s 上り階段  E エレベーター扉  | 縦坑
         M 石碑(きろく)  D 扉(閉)  d 扉(開)  B 本棚  W 窓  F 花の鉢  @ 開始位置  x NPCの立ち位置(床と同じ) */
(function () {
  "use strict";
  var NT = window.NT = window.NT || {}; NT.DATA = NT.DATA || {};
  var COLS = 40, FLOOR_ROWS = 13, FLOORS = 10;

  /* 階ごとの配色 [暗, 中, 明, 最明]。10F の寒色から 1F の暖色へ */
  var PALETTES = {
    10: ["#0b1a2e", "#1f3b57", "#5c8bb0", "#dbe9f5"],
    9: ["#0f1f33", "#24455f", "#6a95b3", "#dfeaf2"],
    8: ["#14213a", "#2d4a66", "#7a9fba", "#e3ecf2"],
    7: ["#1a2338", "#3a4f68", "#8aa5b8", "#e6edf1"],
    6: ["#1f2434", "#474f63", "#9aa6b2", "#eaeeef"],
    5: ["#262430", "#54505f", "#a9a6ac", "#eeecec"],
    4: ["#2c2429", "#60505a", "#b8a39f", "#f1ebe6"],
    3: ["#30231f", "#6c4f43", "#c6a28a", "#f5ecdf"],
    2: ["#331f14", "#754a2a", "#d19a66", "#f8eed8"],
    1: ["#2e1a0b", "#6e3b1f", "#d08a4f", "#fff1dc"]
  };

  /* 階ごとの配置。stair: 下り階段の列（右 36 か 左 5）。stone: 石碑の座標。pots: 花の鉢。shelves/windows: 上壁の飾り */
  var FLOORS_CFG = {
    10: { stair: 36, stone: [8, 4], pots: [[12, 3], [26, 3], [30, 9]], shelves: [14, 15, 16], windows: [22, 28] },
    9: { stair: 5, stone: [31, 4], pots: [[10, 9], [20, 3], [33, 9]], shelves: [8, 9], windows: [18, 24, 30] },
    8: { stair: 36, stone: [8, 9], pots: [[14, 3], [24, 9], [30, 4]], shelves: [26, 27, 28], windows: [10, 16] },
    7: { stair: 5, stone: [31, 9], pots: [[10, 3], [19, 9], [27, 3]], shelves: [12, 13], windows: [20, 26, 32] },
    6: { stair: 36, stone: [8, 4], pots: [[16, 9], [22, 3], [30, 9]], shelves: [24, 25, 26, 27], windows: [12, 18] },
    5: { stair: 5, stone: [31, 4], pots: [[9, 9], [18, 3], [28, 9]], shelves: [10, 11, 12], windows: [20, 26] },
    4: { stair: 36, stone: [8, 9], pots: [[13, 3], [21, 9], [29, 3]], shelves: [30, 31], windows: [12, 18, 24] },
    3: { stair: 5, stone: [31, 9], pots: [[11, 3], [19, 3], [27, 9]], shelves: [14, 15], windows: [22, 28, 34] },
    2: { stair: 36, stone: [8, 4], pots: [[15, 9], [23, 3], [31, 9]], shelves: [10, 11, 26, 27], windows: [18] },
    1: { stair: null, stone: [8, 4], pots: [[12, 3], [28, 3]], shelves: [], windows: [14, 20, 26] }
  };

  function buildRows() {
    var rows = [];
    for (var f = FLOORS; f >= 1; f--) {
      var cfg = FLOORS_CFG[f];
      var band = [];
      for (var r = 0; r < FLOOR_ROWS; r++) {
        var line = [];
        for (var c = 0; c < COLS; c++) {
          var ch = ".";
          if (r === 0 || r === FLOOR_ROWS - 1) ch = "#";
          else if (c === 0 || c === COLS - 1) ch = "#";
          else if (c === 1) ch = "|";
          if (r === 1 && c > 1 && c < COLS - 1) ch = "=";
          line.push(ch);
        }
        band.push(line);
      }
      /* エレベーター扉（x=2, 中段） */
      band[6][2] = "E";
      /* 上壁の飾り */
      cfg.shelves.forEach(function (x) { band[1][x] = "B"; });
      cfg.windows.forEach(function (x) { band[1][x] = "W"; });
      /* 石碑と鉢 */
      band[cfg.stone[1]][cfg.stone[0]] = "M";
      cfg.pots.forEach(function (p) { band[p[1]][p[0]] = "F"; });
      /* 絨毯（中央の通路） */
      for (var cc = 17; cc <= 22; cc++) for (var rr = 3; rr <= 10; rr++) if (band[rr][cc] === ".") band[rr][cc] = ",";
      /* 下り階段：この階の下壁を抜けて次の階へ */
      if (cfg.stair !== null) {
        var sx = cfg.stair;
        band[11][sx] = "S"; band[11][sx + 1] = "S";
        band[12][sx] = "S"; band[12][sx + 1] = "S";
      }
      /* 上り階段：上の階から降りてきた位置 */
      if (f < FLOORS) {
        var ux = FLOORS_CFG[f + 1].stair;
        band[0][ux] = "s"; band[0][ux + 1] = "s";
        band[1][ux] = "s"; band[1][ux + 1] = "s";
        band[2][ux] = "s"; band[2][ux + 1] = "s";
      }
      /* 1F：奥の部屋と扉 */
      if (f === 1) {
        for (var dx = 1; dx < COLS - 1; dx++) if (band[8][dx] !== "|") band[8][dx] = "#";
        band[8][20] = "D";
        for (var ry = 9; ry <= 11; ry++) for (var rx = 2; rx < COLS - 1; rx++) if (band[ry][rx] !== "|") band[ry][rx] = ",";
      }
      /* 10F：開始位置 */
      if (f === FLOORS) band[5][20] = "@";
      band.forEach(function (l) { rows.push(l.join("")); });
    }
    return rows;
  }

  NT.DATA.MAP = {
    cols: COLS, floorRows: FLOOR_ROWS, floors: FLOORS,
    rows: buildRows(),
    palettes: PALETTES,
    cfg: FLOORS_CFG,
    /* 階 f の帯の先頭行 */
    bandY: function (f) { return (FLOORS - f) * FLOOR_ROWS; },
    floorAt: function (y) { var f = FLOORS - Math.floor(y / FLOOR_ROWS); return Math.max(1, Math.min(FLOORS, f)); },
    /* エレベーターで降り立つ位置（扉の右隣） */
    elevatorSpot: function (f) { return { x: 3, y: (FLOORS - f) * FLOOR_ROWS + 6 }; }
  };
})();
