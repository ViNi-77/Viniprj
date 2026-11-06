/* 名前入力。実 input を重ねて IME で入力できるようにする */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Text, G = NT.Gfx;

  NT.SceneName = function (opts) {
    var done = false, value = "";
    var scene = {
      id: "NAME", opaque: true,
      enter: function () {
        NT.InputBox.open({
          x: 40, y: 92, w: 240, maxLen: 6, title: NT.DATA.TEXT.name.title, hint: NT.DATA.TEXT.name.hint,
          placeholder: "ねこ太のともだち",
          onDone: function (v) {
            if (v === null) { NT.Scenes.pop(null); if (opts.onCancel) opts.onCancel(); return; }
            value = v || "ねこ太のともだち";
            NT.Scenes.push(NT.Confirm(NT.Util.fmt(NT.DATA.TEXT.name.confirm, { name: value }), function () {
              done = true; NT.Scenes.pop(value); if (opts.onDone) opts.onDone(value);
            }, function () { scene.enter(); }, { defaultYes: true, y: 150 }));
          }
        });
      },
      update: function () {},
      draw: function (ctx) {
        NT.Screen.clear("#070716");
        T.drawCenter(ctx, "あなたの なまえは？", NT.W / 2, 26, "#f4d03f", { head: true, size: 16 });
        if (NT.Sprites.ready) NT.Sprites.draw(ctx, "nekota:down:0:wave", NT.W / 2, 84);
        NT.InputBox.draw(ctx);
        T.drawCenter(ctx, "ねこ太は きみの なまえで よびかける", NT.W / 2, 200, "#9aa0b4");
      },
      exit: function () { if (!done) NT.InputBox.close(null); }
    };
    return scene;
  };
})();
