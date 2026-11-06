/* シーンスタック。不透明なシーンまで遡って下から順に描く（会話やメニューはマップの上に重なる） */
(function () {
  "use strict";
  var NT = window.NT;
  var S = NT.Scenes = { stack: [] };

  S.top = function () { return S.stack[S.stack.length - 1] || null; };
  S.push = function (scene) {
    var cur = S.top();
    if (cur && cur.pause) cur.pause();
    S.stack.push(scene);
    if (scene.enter) scene.enter();
    return scene;
  };
  S.pop = function (result) {
    var s = S.stack.pop();
    if (s && s.exit) s.exit(result);
    var cur = S.top();
    if (cur && cur.resume) cur.resume(result, s);
    return s;
  };
  /* 特定のシーンを（先頭でなくても）取り除く。会話から別画面を開いた直後に会話を閉じる場合に使う */
  S.remove = function (scene, result) {
    var i = S.stack.indexOf(scene);
    if (i < 0) return null;
    var wasTop = i === S.stack.length - 1;
    S.stack.splice(i, 1);
    if (scene.exit) scene.exit(result);
    var cur = S.top();
    if (wasTop && cur && cur.resume) cur.resume(result, scene);
    return scene;
  };
  S.replace = function (scene) {
    var s = S.stack.pop();
    if (s && s.exit) s.exit();
    S.stack.push(scene);
    if (scene.enter) scene.enter();
    return scene;
  };
  S.reset = function (scene) {
    while (S.stack.length) { var s = S.stack.pop(); if (s && s.exit) s.exit(); }
    S.push(scene);
  };
  S.has = function (id) { return S.stack.some(function (s) { return s.id === id; }); };
  S.find = function (id) { for (var i = S.stack.length - 1; i >= 0; i--) if (S.stack[i].id === id) return S.stack[i]; return null; };

  S.update = function (dt) {
    var t = S.top();
    if (t && t.update) t.update(dt);
  };
  S.draw = function (ctx) {
    var i = S.stack.length - 1;
    while (i > 0 && !S.stack[i].opaque) i--;
    for (; i < S.stack.length; i++) if (S.stack[i].draw) S.stack[i].draw(ctx);
  };
  S.ids = function () { return S.stack.map(function (s) { return s.id; }); };
})();
