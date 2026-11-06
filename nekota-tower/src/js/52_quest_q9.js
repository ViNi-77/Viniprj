/* ⑨ やめられなかったコトを やめる：見せ方の上書き（宣言・日次チェック・お守りは定義の汎用処理） */
(function () {
  "use strict";
  var NT = window.NT;
  var TX = function () { return NT.DATA.TEXT.quest; };
  NT.QuestImpl = NT.QuestImpl || {};
  NT.QuestImpl.q9 = {
    execStatus: function (q) {
      if (!q.declared) return ["まだ 宣言していない。候補を えらんで 宣言しよう"];
      var s = NT.Quests.streak(q);
      return ["やめていること：" + q.declared.text, NT.Util.fmt(TX().streak, { n: s }) + "（" + q.declared.startKey.slice(5).replace("-", "/") + "〜）", TX().charm + "　" + NT.Util.fmt(TX().charmLeft, { n: q.charms || 0 })];
    },
    execHint: "1日1回「きょうも やめた」。休む日は お守りで つなぐ（2つまで）"
  };
})();
