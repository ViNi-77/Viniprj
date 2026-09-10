/**
 * 取り消し／やり直し（資料全体のスナップショット）。
 * - 1 操作 = 1 スナップショット。ドラッグ中は push せず、確定時に 1 回だけ push する。
 * - 上限を超えた古い履歴は捨てる。
 */
window.PWB = window.PWB || {};
PWB.history = (function () {
  "use strict";
  var LIMIT = 100;
  var undoStack = [];
  var redoStack = [];

  function snapshot(presentation) { return JSON.stringify(presentation); }

  return {
    /** 変更前の状態を積む（変更を加える直前に呼ぶ）。 */
    push: function (presentation) {
      if (!presentation) return;
      undoStack.push(snapshot(presentation));
      if (undoStack.length > LIMIT) undoStack.shift();
      redoStack = [];
    },
    /** 直前の状態を返す（無ければ null）。current は「今の状態」で、redo 用に積む。 */
    undo: function (current) {
      if (!undoStack.length) return null;
      redoStack.push(snapshot(current));
      return JSON.parse(undoStack.pop());
    },
    redo: function (current) {
      if (!redoStack.length) return null;
      undoStack.push(snapshot(current));
      return JSON.parse(redoStack.pop());
    },
    canUndo: function () { return undoStack.length > 0; },
    canRedo: function () { return redoStack.length > 0; },
    clear: function () { undoStack = []; redoStack = []; }
  };
})();
