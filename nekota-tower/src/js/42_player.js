/* ねこ太の移動。タイル単位で歩き、見た目は揺れフレームで表現する */
(function () {
  "use strict";
  var NT = window.NT;
  var TILE = NT.TILE, I = NT.Input, U = NT.Util;
  var P = NT.Player = { x: 0, y: 0, px: 0, py: 0, dir: "down", moving: false, tx: 0, ty: 0, phase: 0, locked: false, path: null };
  var stepSfx = 0;

  P.place = function (x, y, dir) {
    P.x = x; P.y = y; P.px = x * TILE; P.py = y * TILE; P.dir = dir || P.dir; P.moving = false; P.path = null;
    if (NT.State.cur) NT.State.cur.pos = { x: x, y: y, dir: P.dir };
  };
  P.facing = function () {
    var d = { down: [0, 1], up: [0, -1], left: [-1, 0], right: [1, 0] }[P.dir];
    return { x: P.x + d[0], y: P.y + d[1] };
  };
  P.tryMove = function (dx, dy) {
    if (P.moving || P.locked) return false;
    P.dir = dx > 0 ? "right" : dx < 0 ? "left" : dy > 0 ? "down" : "up";
    var nx = P.x + dx, ny = P.y + dy;
    if (NT.Tilemap.solid(nx, ny)) { return false; }
    P.tx = nx; P.ty = ny; P.moving = true;
    return true;
  };
  P.update = function (dt) {
    var speed = I.held("dash") ? 4 : 2;
    if (!P.moving) {
      if (!P.locked) {
        var ax = I.axis();
        /* 一瞬だけ押された場合も1歩ぶんとして扱う */
        if (!ax.x && !ax.y) {
          ax.x = (I.pressed("right") ? 1 : 0) - (I.pressed("left") ? 1 : 0);
          ax.y = (I.pressed("down") ? 1 : 0) - (I.pressed("up") ? 1 : 0);
        }
        if (P.path && P.path.length) {
          var n = P.path[0];
          if (!P.tryMove(n.x - P.x, n.y - P.y)) P.path = null; else P.path.shift();
        } else if (ax.x || ax.y) {
          P.path = null;
          if (ax.x && !P.tryMove(ax.x, 0) && ax.y) P.tryMove(0, ax.y);
          else if (!ax.x && ax.y) P.tryMove(0, ax.y);
        }
      }
      if (!P.moving) { P.phase += dt * 0.0022; return; }
    }
    var gx = P.tx * TILE, gy = P.ty * TILE;
    if (P.px < gx) P.px = Math.min(gx, P.px + speed); else if (P.px > gx) P.px = Math.max(gx, P.px - speed);
    if (P.py < gy) P.py = Math.min(gy, P.py + speed); else if (P.py > gy) P.py = Math.max(gy, P.py - speed);
    P.phase += dt * 0.011;
    stepSfx += dt;
    if (stepSfx > 220) { stepSfx = 0; NT.Audio.play("step"); }
    if (P.px === gx && P.py === gy) {
      P.x = P.tx; P.y = P.ty; P.moving = false;
      if (NT.State.cur) NT.State.cur.pos = { x: P.x, y: P.y, dir: P.dir };
      if (P.onArrive) P.onArrive(P.x, P.y);
    }
  };
  P.spriteKey = function () {
    var f = 0;
    if (P.moving) f = Math.sin(P.phase) > 0.3 ? 1 : Math.sin(P.phase) < -0.3 ? -1 : 0;
    return "nekota:" + P.dir + ":" + f;
  };
  P.draw = function (ctx, cam) {
    var bob = P.moving ? Math.round(Math.abs(Math.sin(P.phase)) * 2) : 0;
    var x = Math.round(P.px - cam.x + TILE / 2), y = Math.round(P.py - cam.y + TILE - bob + 2);
    NT.Sprites.draw(ctx, P.spriteKey(), x, y);
  };
  /* クリック移動：幅優先で経路を引く（短い距離だけ） */
  P.walkTo = function (tx, ty) {
    if (P.locked) return;
    if (NT.Tilemap.solid(tx, ty)) {
      /* 固い所をクリックしたら、その手前まで */
      var cand = [[tx, ty + 1], [tx, ty - 1], [tx - 1, ty], [tx + 1, ty]].filter(function (c) { return !NT.Tilemap.solid(c[0], c[1]); });
      if (!cand.length) return;
      cand.sort(function (a, b) { return (Math.abs(a[0] - P.x) + Math.abs(a[1] - P.y)) - (Math.abs(b[0] - P.x) + Math.abs(b[1] - P.y)); });
      tx = cand[0][0]; ty = cand[0][1];
    }
    var start = { x: P.x, y: P.y }, key = function (p) { return p.x + "," + p.y; };
    var prev = {}, q = [start], seen = {}; seen[key(start)] = true;
    var found = null, limit = 2000;
    while (q.length && limit-- > 0) {
      var c = q.shift();
      if (c.x === tx && c.y === ty) { found = c; break; }
      [[0, 1], [0, -1], [1, 0], [-1, 0]].forEach(function (d) {
        var n = { x: c.x + d[0], y: c.y + d[1] }, k = key(n);
        if (seen[k] || NT.Tilemap.solid(n.x, n.y)) return;
        seen[k] = true; prev[k] = c; q.push(n);
      });
    }
    if (!found) return;
    var path = [], cur = found;
    while (cur && !(cur.x === start.x && cur.y === start.y)) { path.unshift(cur); cur = prev[key(cur)]; }
    P.path = path;
  };
})();
