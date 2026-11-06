/* 設定。本体メモリに保存する */
(function () {
  "use strict";
  var NT = window.NT;
  var S = NT.Settings = {};
  var DEF = { msgSpeed: 1, sfx: true, crt: true, scaleMode: "device", reduceMotion: false };
  var cur = NT.Util.assign({}, DEF);
  S.SPEEDS = [{ id: 0, label: "そくじ", cps: 0 }, { id: 1, label: "ふつう", cps: 1, ms: 30 }, { id: 2, label: "はやい", cps: 2, ms: 30 }, { id: 3, label: "おそい", cps: 1, ms: 60 }];

  S.load = function () {
    var saved = NT.Storage.getJSON("settings");
    if (saved) NT.Util.assign(cur, saved);
    if (!("reduceMotion" in (saved || {}))) {
      try { cur.reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (e) { /* 無視 */ }
    }
    if (NT.query.nocrt) cur.crt = false;
    S.apply();
  };
  S.save = function () { NT.Storage.setJSON("settings", cur); };
  S.get = function (k) { return cur[k]; };
  S.set = function (k, v) { cur[k] = v; S.apply(); S.save(); };
  S.all = function () { return NT.Util.assign({}, cur); };
  S.apply = function () {
    NT.Screen.setCRT(cur.crt);
    NT.Screen.setMode(cur.scaleMode);
    NT.Audio.setSfx(cur.sfx);
    if (NT.Screen.crt) NT.Screen.crt.classList.toggle("still", !!cur.reduceMotion);
  };
  /* 文字送り：1ステップあたりの表示文字数（小数可）*/
  S.charsPerStep = function () {
    var sp = S.SPEEDS[cur.msgSpeed] || S.SPEEDS[1];
    if (sp.cps === 0) return Infinity;
    return sp.cps * NT.STEP / sp.ms;
  };
})();
