/* タイトル画面 */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx, I = NT.Input;

  NT.SceneTitle = function () {
    var t = 0, started = false, idle = 0;
    var menu = null;
    var stars = [];
    var rng = NT.Util.rng(3);
    for (var i = 0; i < 60; i++) stars.push([Math.floor(rng() * NT.W), Math.floor(rng() * 150), rng()]);

    function hasSaves() { for (var n = 1; n <= 3; n++) { var r = NT.Storage.readSlot(n); if (r && r.rec) return true; } return false; }
    function openMenu() {
      var cont = hasSaves();
      var items = [
        { label: "はじめから", value: "new" },
        { label: "つづきから", value: "continue", disabled: !cont },
        { label: "メモリーカード", value: "card" },
        { label: "せってい", value: "settings" }
      ];
      menu = NT.Menu({
        x: 104, y: 146, w: 120, items: items, index: cont ? 1 : 0, cancelable: false,
        onSelect: function (it) {
          if (it.value === "new") NT.Flow.newGame();
          else if (it.value === "continue") NT.Flow.openSlots("load");
          else if (it.value === "card") NT.Flow.openCard();
          else if (it.value === "settings") NT.Flow.openSettings();
        }
      });
      menu.draw2 = menu.draw;
      menu.draw = function (ctx) { G.frame(ctx, menu.x, menu.y, menu.w, menu.h, { innerColor: "#4a4560" }); menu.draw2(ctx); };
      /* メモリーカードや せってい から戻ったら、きろく の有無を見直す（カードから読み込んだ直後に つづきから を使えるように） */
      menu.resume = function () {
        var c = hasSaves();
        menu.items[1].disabled = !c;
        if (c && menu.index === 0) menu.index = 1;
      };
      NT.Scenes.push(menu);
    }
    var scene = {
      id: "TITLE", opaque: true,
      enter: function () { t = 0; idle = 0; started = false; },
      resume: function () { started = true; idle = 0; },
      update: function (dt) {
        t += dt; idle += dt;
        if (!started) {
          if (I.anyKey()) { NT.Audio.unlock(); NT.Audio.play("decide"); started = true; openMenu(); }
          return;
        }
        if (NT.Scenes.top() === scene) openMenu();
      },
      draw: function (ctx) {
        NT.Screen.clear("#070716");
        /* 夜空と塔のシルエット */
        for (var i = 0; i < stars.length; i++) {
          var s = stars[i];
          var tw = ((t / 700 + s[2] * 10) % 2) < 1 ? "#f4f1e8" : "#6e6a7a";
          ctx.fillStyle = tw; ctx.fillRect(s[0], s[1], 1, 1);
        }
        ctx.fillStyle = "#121228";
        ctx.fillRect(0, 170, NT.W, 70);
        ctx.fillStyle = "#1d1b3a";
        ctx.fillRect(236, 60, 44, 120); ctx.fillRect(228, 52, 60, 8); ctx.fillRect(244, 40, 28, 12);
        ctx.fillStyle = "#f4d03f";
        [[244, 74], [262, 74], [244, 98], [262, 98], [244, 122], [262, 146]].forEach(function (p) { if (((t / 900) + p[1]) % 7 > 1) ctx.fillRect(p[0], p[1], 6, 8); });
        ctx.fillStyle = "#fff6d6"; ctx.fillRect(252, 158, 12, 10);
        /* ロゴ */
        T.drawCenter(ctx, "ねこ太と", 128, 40, "#f4f1e8", { head: true, size: 16 });
        T.drawCenter(ctx, "十二月の塔", 128, 62, "#f4d03f", { head: true, size: 16, shadow: true });
        ctx.fillStyle = "#f4d03f"; ctx.fillRect(74, 84, 108, 1);
        T.drawCenter(ctx, "年末クエスト", 128, 90, "#9aa0b4");
        T.drawCenter(ctx, "難易度 ★★★★★★★★★★", 128, 108, "#f4afc4");
        T.drawCenter(ctx, "報酬：人生最高の余暇", 128, 124, "#9aa0b4");
        if (NT.Sprites && NT.Sprites.ready) NT.Sprites.draw(ctx, "nekota:down:" + (Math.floor(t / 400) % 2 === 0 ? 0 : 1), 200, 182);
        if (!started) {
          if ((Math.floor(t / 600) % 2) === 0 || NT.Settings.get("reduceMotion")) T.drawCenter(ctx, "PUSH START BUTTON", 160, 168, "#f4f1e8");
        }
        T.drawRight(ctx, "(C) 2026 NETTA GAME-BU", NT.W - 8, NT.H - 14, "#5b5a66");
        T.draw(ctx, "NETTA BOY", 8, NT.H - 14, "#5b5a66");
      },
      start: function () { if (!started) { started = true; openMenu(); } }
    };
    return scene;
  };
})();
