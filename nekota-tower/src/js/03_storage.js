/* 本体メモリ（localStorage）。file:// ではブラウザごとに挙動が違うので、失敗したらメモリ内に退避して告知する */
(function () {
  "use strict";
  var NT = window.NT;
  var S = NT.Storage = {};
  var PREFIX = NT.APP + ":v1:";
  var mem = {};
  S.available = false;
  S.reason = "";

  function key(k) { return PREFIX + k; }

  S.probe = function () {
    try {
      var k = key("probe"), v = String(Date.now());
      localStorage.setItem(k, v);
      var ok = localStorage.getItem(k) === v;
      localStorage.removeItem(k);
      S.available = ok;
      if (!ok) S.reason = "readback";
    } catch (e) {
      S.available = false;
      S.reason = (e && e.name) || "error";
    }
    return S.available;
  };

  S.getRaw = function (k) {
    if (S.available) { try { return localStorage.getItem(key(k)); } catch (e) { return mem[k] === undefined ? null : mem[k]; } }
    return mem[k] === undefined ? null : mem[k];
  };
  S.setRaw = function (k, v) {
    mem[k] = v;
    if (!S.available) return false;
    try { localStorage.setItem(key(k), v); return true; }
    catch (e) { S.lastError = e; return false; }
  };
  S.remove = function (k) {
    delete mem[k];
    if (!S.available) return;
    try { localStorage.removeItem(key(k)); } catch (e) { /* 無視 */ }
  };
  S.getJSON = function (k) {
    var raw = S.getRaw(k);
    if (raw == null) return null;
    try { return JSON.parse(raw); } catch (e) { return null; }
  };
  S.setJSON = function (k, obj) { return S.setRaw(k, JSON.stringify(obj)); };

  /* セーブレコードの版管理。将来 v2 にするときは MIGRATIONS[1] に 1→2 の変換を書く */
  S.MIGRATIONS = {};
  S.migrate = function (rec) {
    if (!rec || typeof rec !== "object") return null;
    if (rec.app !== NT.APP) return null;
    var v = rec.v | 0;
    if (v > NT.SAVE_VERSION) return { tooNew: true, rec: rec };
    var guard = 0;
    while (v < NT.SAVE_VERSION && guard++ < 20) {
      var fn = S.MIGRATIONS[v];
      if (!fn) return null;
      rec = fn(rec);
      v = rec.v | 0;
    }
    return { rec: rec };
  };

  S.slotKey = function (n) { return "slot:" + n; };
  S.readSlot = function (n) {
    var r = S.migrate(S.getJSON(S.slotKey(n)));
    return r;
  };
  S.writeSlot = function (n, rec) { return S.setJSON(S.slotKey(n), rec); };
  S.readSuspend = function () { return S.migrate(S.getJSON("suspend")); };
  S.writeSuspend = function (rec) { return S.setJSON("suspend", rec); };
  S.clearSuspend = function () { S.remove("suspend"); };
})();
