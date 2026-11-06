/* ❾ やめられなかったコトを やめる：宣言・日次チェック・お守り */
(function () {
  "use strict";
  var NT = window.NT;
  var TX = function () { return NT.DATA.TEXT.quest; };
  NT.QuestImpl = NT.QuestImpl || {};
  NT.QuestImpl.q9 = {
    entryCommands: function (q, entry) {
      var items = [];
      if (!q.declared) items.push({ label: "これを 年末限定で やめると 宣言する", value: "declare" });
      items.push({ label: TX().edit, value: "edit" });
      if (!q.declared || q.declared.text !== entry.text) items.push({ label: TX().remove, value: "remove" });
      items.push({ label: NT.DATA.TEXT.menu.back, value: "back" });
      return items;
    },
    entryLine: function (entry, q) {
      var mark = q.declared && q.declared.text === entry.text ? "★ " : "・ ";
      return mark + entry.text;
    },
    /* 実行タブ上部の状態表示と日次コマンド */
    execStatus: function (q) {
      if (!q.declared) return ["まだ 宣言していない。候補を えらんで 宣言しよう"];
      var s = NT.Quests.streak(q);
      var lines = ["やめていること：" + q.declared.text, NT.Util.fmt(TX().streak, { n: s }) + "（" + q.declared.startKey.slice(5).replace("-", "/") + "〜）", TX().charm + "　" + NT.Util.fmt(TX().charmLeft, { n: q.charms || 0 })];
      return lines;
    },
    dailyCommands: function (q) {
      if (!q.declared) return [];
      var can = NT.Quests.canCheckToday(q);
      return [
        { label: "きょうも やめた", value: "check", disabled: !can.ok, note: can.ok ? "" : "" },
        { label: "おやすみのお守りを つかう", value: "charm", disabled: !(q.charms > 0) || !can.ok }
      ];
    },
    execHint: "1日1回「きょうも やめた」。休む日は お守りで つなぐ（2つまで）"
  };
})();
