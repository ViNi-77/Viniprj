/* スプライト：SVG 文字列を 32x40 の offscreen canvas にラスタライズしてキャッシュ */
(function () {
  "use strict";
  var NT = window.NT = window.NT || {};

  var SW = 32, SH = 40;
  var DIRS = ['down', 'up', 'left', 'right'];
  var FRAMES = [-1, 0, 1];
  var NPC_IDS = ['elder', 'npc10', 'npc9', 'npc8', 'npc7', 'npc6', 'npc5', 'npc4', 'npc3', 'npc2', 'npc1', 'boss'];
  var TIMEOUT_MS = 2000;

  var cache = {};
  var loading = null;

  function makeCanvas() {
    var c = document.createElement('canvas');
    c.width = SW; c.height = SH;
    return c;
  }

  // 失敗時の代替：耳付きの色つき団子
  function placeholder(color) {
    var c = makeCanvas();
    var g = c.getContext('2d');
    g.fillStyle = color || '#CDBDEC';
    g.beginPath(); g.ellipse(16, 24, 10, 9, 0, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.moveTo(7, 20); g.lineTo(9, 10); g.lineTo(14, 16); g.closePath(); g.fill();
    g.beginPath(); g.moveTo(25, 20); g.lineTo(23, 10); g.lineTo(18, 16); g.closePath(); g.fill();
    g.fillStyle = '#3A3A45';
    g.fillRect(12, 22, 2, 3); g.fillRect(18, 22, 2, 3);
    return c;
  }

  function rasterize(svg) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      var done = false;
      var timer = setTimeout(function () {
        if (done) return; done = true; reject(new Error('timeout'));
      }, TIMEOUT_MS);
      function finish(err) {
        if (done) return; done = true; clearTimeout(timer);
        if (err) { reject(err); return; }
        try {
          var c = makeCanvas();
          var g = c.getContext('2d');
          g.imageSmoothingEnabled = false;
          g.drawImage(img, 0, 0, SW, SH);
          resolve(c);
        } catch (e) { reject(e); }
      }
      img.onerror = function () { finish(new Error('load error')); };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      var p = (typeof img.decode === 'function') ? img.decode() : new Promise(function (ok) { img.onload = ok; });
      p.then(function () { finish(null); }, function (e) { finish(e || new Error('decode error')); });
    });
  }

  function loadOne(key, svg, color) {
    return rasterize(svg).then(function (c) {
      cache[key] = c;
    }, function () {
      cache[key] = placeholder(color);
      NT.Sprites.failed.push(key);
    });
  }

  NT.Sprites = {
    ready: false,
    failed: [],
    W: SW,
    H: SH,

    /** 全バリアントをラスタライズ。2回目以降は同じ Promise を返す */
    load: function () {
      if (loading) return loading;
      var jobs = [];
      DIRS.forEach(function (d) {
        FRAMES.forEach(function (f) {
          jobs.push(loadOne('nekota:' + d + ':' + f, NT.SVG.nekota(d, f, { sushi: true }), '#CDBDEC'));
        });
      });
      jobs.push(loadOne('nekota:down:0:wave', NT.SVG.nekota('down', 0, { sushi: true, wave: true }), '#CDBDEC'));
      NPC_IDS.forEach(function (id) {
        jobs.push(loadOne('npc:' + id, NT.SVG.npc(id), '#B9B6C4'));
      });
      loading = Promise.all(jobs).then(function () {
        NT.Sprites.ready = true;
      });
      return loading;
    },

    /** @returns {HTMLCanvasElement} 未知キーはプレースホルダ（キャッシュする） */
    get: function (key) {
      var c = cache[key];
      if (!c) {
        c = cache[key] = placeholder('#CDBDEC');
        if (NT.Sprites.failed.indexOf(key) < 0) NT.Sprites.failed.push(key);
      }
      return c;
    },

    /** 足元中心 (x,y) に描く。内部解像度ピクセルで整数に丸める */
    draw: function (ctx, key, x, y) {
      ctx.drawImage(NT.Sprites.get(key), Math.round(x) - (SW >> 1), Math.round(y) - SH);
    },

    keys: function () {
      return Object.keys(cache);
    }
  };
})();
