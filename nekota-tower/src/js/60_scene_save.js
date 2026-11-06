/* きろく（セーブ）。スロット選択 → 書き込み → チャイム */
(function () {
  "use strict";
  var NT = window.NT;
  var S = NT.Save = {};

  S.writeTo = function (n) {
    var rec = NT.State.toRecord();
    var ok = NT.Storage.writeSlot(n, rec);
    if (ok) { NT.State.slot = n; NT.State.setDirty(false); NT.Storage.clearSuspend(); NT.Audio.play("save"); }
    else NT.Audio.play("error");
    return ok;
  };
  S.suspend = function () {
    if (!NT.State.cur || !NT.State.dirty) return;
    try { NT.Storage.writeSuspend(NT.State.toRecord()); } catch (e) { /* 無視 */ }
  };

  NT.Flow = NT.Flow || {};
  NT.Flow.openSave = function () {
    NT.Scenes.push(NT.SceneSlot({ mode: "save", onPick: function (n) {
      var ok = S.writeTo(n);
      var msg = ok ? NT.DATA.TEXT.save.done + "（きろく " + n + "）" : NT.DATA.TEXT.save.fail;
      NT.Scenes.push(NT.Notice(msg, null, { y: 100, color: ok ? "#7dffb0" : "#f4afc4" }));
    } }));
  };
})();
