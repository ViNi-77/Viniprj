/* NPC の配置。座標は階の帯の中の (x, 行) 。dialog は data/dialogs.js のスクリプト名 */
(function () {
  "use strict";
  var NT = window.NT = window.NT || {}; NT.DATA = NT.DATA || {};
  NT.DATA.ENTITIES = [
    { id: "elder", floor: 10, x: 23, y: 5, sprite: "npc:elder", name: "としのせの長老", dialog: "d.elder", face: "down" },
    { id: "npc10", floor: 10, x: 30, y: 6, sprite: "npc:npc10", name: "アライのグマ", dialog: "d.q10", quest: "q10" },
    { id: "npc9", floor: 9, x: 12, y: 6, sprite: "npc:npc9", name: "ハムの助", dialog: "d.q9", quest: "q9" },
    { id: "npc8", floor: 8, x: 27, y: 6, sprite: "npc:npc8", name: "フクロウ先生", dialog: "d.q8", quest: "q8" },
    { id: "npc7", floor: 7, x: 13, y: 6, sprite: "npc:npc7", name: "カメ吉", dialog: "d.q7", quest: "q7" },
    { id: "npc6", floor: 6, x: 26, y: 6, sprite: "npc:npc6", name: "うさ子", dialog: "d.q6", quest: "q6" },
    { id: "npc5", floor: 5, x: 14, y: 6, sprite: "npc:npc5", name: "でんでん", dialog: "d.q5", quest: "q5" },
    { id: "npc4", floor: 4, x: 25, y: 6, sprite: "npc:npc4", name: "ポッポ", dialog: "d.q4", quest: "q4" },
    { id: "npc3", floor: 3, x: 15, y: 6, sprite: "npc:npc3", name: "ペン太郎", dialog: "d.q3", quest: "q3" },
    { id: "npc2", floor: 2, x: 24, y: 6, sprite: "npc:npc2", name: "ケロ吉", dialog: "d.q2", quest: "q2" },
    { id: "npc1", floor: 1, x: 16, y: 5, sprite: "npc:npc1", name: "しろくまさん", dialog: "d.q1", quest: "q1" },
    { id: "boss", floor: 1, x: 20, y: 10, sprite: "npc:boss", name: "？？？", dialog: "d.boss" }
  ];
})();
