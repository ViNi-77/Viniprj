/* 図書室：本棚を調べると、その階の参考図書と動画の題名が並び、選ぶと要点を一言 */
(function () {
  "use strict";
  var NT = window.NT;
  var TX = function () { return NT.DATA.TEXT.library; };
  NT.Flow = NT.Flow || {};
  NT.Flow.openLibrary = function (floor) {
    var books = (NT.DATA.LIBRARY || {})[floor] || [];
    if (!books.length) { NT.Dialog.open("d.shelf"); return; }
    var items = books.map(function (b) { return { label: "『" + b.title + "』", note: b.kind, value: b }; });
    items.push({ label: NT.DATA.TEXT.menu.back, value: null });
    NT.Audio.play("open");
    NT.Scenes.push(NT.Menu({ x: 16, y: 40, w: 288, title: floor + "F の 本棚", items: items, onSelect: function (it) {
      if (!it.value) { NT.Scenes.pop(); return; }
      NT.Scenes.push(NT.Notice("『" + it.value.title + "』（" + it.value.kind + "）\n" + it.value.point, null, { y: 120 }));
    } }));
  };
})();
