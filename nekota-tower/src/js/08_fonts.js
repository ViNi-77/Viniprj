/* 埋め込みフォントの読込待ち。最初の文字描画より前に ready を待つ */
(function () {
  "use strict";
  var NT = window.NT;
  var F = NT.Fonts = { ready: false, ok: false };
  var promise = null;
  F.load = function () {
    if (promise) return promise;
    var loads = [];
    if (document.fonts && document.fonts.load) {
      loads.push(document.fonts.load('12px "PM12"', "あ"));
      loads.push(document.fonts.load('16px "DG16"', "あ"));
    }
    var timeout = new Promise(function (res) { setTimeout(function () { res("timeout"); }, 3000); });
    promise = Promise.race([Promise.all(loads), timeout]).then(function (r) {
      F.ready = true;
      F.ok = r !== "timeout" && (!document.fonts || document.fonts.check('12px "PM12"'));
    }).catch(function () { F.ready = true; F.ok = false; });
    return promise;
  };
  F.check = function () {
    try { return !!(document.fonts && document.fonts.check('12px "PM12"')); } catch (e) { return false; }
  };
})();
