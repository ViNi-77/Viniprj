/* ❿ すてられなかった物を すてる：項目ごとの実行コマンドと文言 */
(function () {
  "use strict";
  var NT = window.NT;
  NT.QuestImpl = NT.QuestImpl || {};
  NT.QuestImpl.q10 = {
    /* 実行タブで項目を選んだときのメニュー */
    entryCommands: function (q, entry) {
      var def = NT.Quests.def("q10"), cmd = def.exec.commands[0];
      var items = [];
      if (!entry.doneKey) items.push({ label: cmd.label, value: "do", cmd: cmd });
      else if (entry.undoUntil > NT.Loop.elapsed) items.push({ label: NT.DATA.TEXT.quest.undo, value: "undo" });
      items.push({ label: NT.DATA.TEXT.quest.edit, value: "edit" });
      if (!entry.doneKey) items.push({ label: NT.DATA.TEXT.quest.remove, value: "remove" });
      items.push({ label: NT.DATA.TEXT.menu.back, value: "back" });
      return items;
    },
    entryLine: function (entry) {
      var tags = {}; NT.Quests.def("q10").prep.list.tags.forEach(function (t) { tags[t[0]] = t[1]; });
      var tag = entry.tag && entry.tag !== "none" ? "〔" + tags[entry.tag] + "〕" : "";
      return (entry.doneKey ? "● " : "○ ") + entry.text + tag;
    },
    execHint: "項目を えらんで「すてる」。すてたら その場で 押す。教訓は ほうこく で 書く"
  };
})();
