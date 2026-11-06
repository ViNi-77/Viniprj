/* NPC と仕掛け。マップ上の座標に変換して持つ */
(function () {
  "use strict";
  var NT = window.NT;
  var TILE = NT.TILE;
  var E = NT.Entities = { list: [] };
  var byPos = {};

  E.init = function () {
    E.list = NT.DATA.ENTITIES.map(function (d) {
      var e = NT.Util.assign({}, d);
      e.wx = d.x; e.wy = NT.DATA.MAP.bandY(d.floor) + d.y;
      e.bob = 0; e.dir = d.face || "down";
      return e;
    });
    byPos = {};
    E.list.forEach(function (e) { byPos[e.wx + "," + e.wy] = e; });
  };
  E.at = function (x, y) { return byPos[x + "," + y] || null; };
  E.byId = function (id) { for (var i = 0; i < E.list.length; i++) if (E.list[i].id === id) return E.list[i]; return null; };
  E.visible = function (e) {
    if (e.id === "boss") return !!(NT.State.cur && NT.State.cur.flags.doorOpen);
    return true;
  };
  E.update = function (dt) {
    E.list.forEach(function (e) { e.bob += dt; });
  };
  E.draw = function (ctx, cam) {
    var st = NT.State.cur;
    E.list.forEach(function (e) {
      if (!E.visible(e)) return;
      var px = e.wx * TILE - cam.x, py = e.wy * TILE - cam.y;
      if (px < -32 || py < -48 || px > NT.W + 32 || py > NT.H + 48) return;
      var hop = (e.hopUntil && e.hopUntil > NT.Loop.elapsed) ? -Math.round(Math.abs(Math.sin((e.hopUntil - NT.Loop.elapsed) / 60)) * 4) : 0;
      NT.Sprites.draw(ctx, e.sprite, px + TILE / 2, py + TILE + 2 + hop);
      /* クエストの状態を頭上に */
      if (e.quest && st) {
        var q = st.quests[e.quest] || {}, mark = null, col = "#f4d03f";
        if (q.status === "cleared") { mark = "●"; col = "#7dffb0"; }
        else if (NT.Quests && NT.Quests.isReportable(e.quest)) { mark = "!"; col = "#f4afc4"; }
        else if (q.status === "offered" && NT.DATA.QUESTS[e.quest] && NT.DATA.QUESTS[e.quest].implemented) { mark = "?"; }
        if (mark && ((e.bob % 900) < 650)) NT.Text.draw(ctx, mark, px + 5, py - 30 + hop, col, { shadow: true });
      }
    });
  };
  E.hop = function (id) { var e = E.byId(id); if (e) e.hopUntil = NT.Loop.elapsed + 360; };
})();
