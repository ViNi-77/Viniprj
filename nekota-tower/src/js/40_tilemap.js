/* タイルマップ。衝突判定と描画 */
(function () {
  "use strict";
  var NT = window.NT;
  var G = NT.Gfx, TILE = NT.TILE;
  var M = NT.Tilemap = {};
  var map = null, cols = 0, rows = 0, grid = [];
  var CH = { "#": G.T.WALL, "=": G.T.WALLTOP, ".": G.T.FLOOR, ",": G.T.CARPET, "S": G.T.STAIRS_DOWN, "s": G.T.STAIRS_UP, "E": G.T.ELEVATOR, "|": G.T.ELEVATOR_SHAFT, "M": G.T.STONE, "D": G.T.DOOR, "d": G.T.DOOR_OPEN, "B": G.T.SHELF, "W": G.T.WINDOW, "F": G.T.FLOWER_POT, "@": G.T.CARPET, "x": G.T.FLOOR, " ": G.T.VOID };
  var SOLID = { "#": 1, "=": 1, "|": 1, "M": 1, "B": 1, "W": 1, "F": 1, " ": 1 };

  M.init = function () {
    map = NT.DATA.MAP;
    cols = map.cols; rows = map.rows.length;
    grid = map.rows.map(function (r) { return r.split(""); });
    M.cols = cols; M.rows = rows;
    M.pxW = cols * TILE; M.pxH = rows * TILE;
    M.spawn = null;
    for (var y = 0; y < rows; y++) for (var x = 0; x < cols; x++) if (grid[y][x] === "@") M.spawn = { x: x, y: y };
  };
  M.at = function (x, y) { if (x < 0 || y < 0 || x >= cols || y >= rows) return " "; return grid[y][x]; };
  M.set = function (x, y, ch) { if (x >= 0 && y >= 0 && x < cols && y < rows) grid[y][x] = ch; };
  M.floorAt = function (y) { return map.floorAt(y); };
  M.bandY = function (f) { return map.bandY(f); };
  M.solid = function (x, y) {
    var ch = M.at(x, y);
    if (ch === "D") return !(NT.State.cur && NT.State.cur.flags.doorOpen);
    if (SOLID[ch]) return true;
    if (NT.Entities && NT.Entities.at(x, y)) return true;
    return false;
  };
  M.isFlower = function (x, y) { return M.at(x, y) === "F"; };
  /* 階の鉢の一覧 */
  M.potsOf = function (f) { return (map.cfg[f] && map.cfg[f].pots) || []; };
  /* 描画。camera: {x,y}（px、左上） */
  M.draw = function (ctx, cam) {
    var x0 = Math.floor(cam.x / TILE), y0 = Math.floor(cam.y / TILE);
    var x1 = Math.ceil((cam.x + NT.W) / TILE), y1 = Math.ceil((cam.y + NT.H) / TILE);
    var flowers = (NT.State.cur && NT.State.cur.flowers) || {};
    for (var y = y0; y <= y1; y++) {
      if (y < 0 || y >= rows) continue;
      var f = map.floorAt(y);
      var ts = G.tileset(f, map.palettes[f]);
      for (var x = x0; x <= x1; x++) {
        if (x < 0 || x >= cols) continue;
        var ch = grid[y][x];
        var idx = CH[ch] === undefined ? G.T.FLOOR : CH[ch];
        if (ch === "D" && NT.State.cur && NT.State.cur.flags.doorOpen) idx = G.T.DOOR_OPEN;
        if (ch === "F") {
          var list = flowers[f] || [];
          for (var i = 0; i < list.length; i++) if (list[i][0] === x && list[i][1] === y) { idx = G.T.FLOWER; break; }
        }
        var px = x * TILE - cam.x, py = y * TILE - cam.y;
        if (idx !== G.T.FLOOR && idx !== G.T.CARPET && idx !== G.T.WALL && idx !== G.T.WALLTOP && idx !== G.T.VOID && idx !== G.T.ELEVATOR_SHAFT) G.drawTile(ctx, ts, G.T.FLOOR, px, py);
        G.drawTile(ctx, ts, idx, px, py);
      }
    }
  };
})();
