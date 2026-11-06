/* 未保存の警告。ダーティなときだけ beforeunload を登録し、隠れたら「ちゅうだんデータ」を書く */
(function () {
  "use strict";
  var NT = window.NT;
  var L = NT.Interlock = { armed: false };
  function onBeforeUnload(e) {
    e.preventDefault();
    e.returnValue = true; /* 文言は変えられない（ブラウザの定型） */
    return true;
  }
  L.arm = function () { if (L.armed) return; L.armed = true; window.addEventListener("beforeunload", onBeforeUnload); };
  L.disarm = function () { if (!L.armed) return; L.armed = false; window.removeEventListener("beforeunload", onBeforeUnload); };
  L.install = function () {
    NT.State.onDirty(function (d) { if (d) L.arm(); else L.disarm(); });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { NT.Save.suspend(); NT.Audio.suspend(true); }
      else NT.Audio.suspend(false);
    });
    window.addEventListener("pagehide", function () { NT.Save.suspend(); });
  };
})();
