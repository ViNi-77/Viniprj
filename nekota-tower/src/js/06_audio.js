/* 合成音。音源ファイルは持たず、矩形波・三角波・ノイズで鳴らす。AudioContext は最初の操作（電源ボタン）で起こす */
(function () {
  "use strict";
  var NT = window.NT;
  var A = NT.Audio = { ctx: null, master: null, sfxOn: true, musicTimer: null };
  var midi = function (n) { return 440 * Math.pow(2, (n - 69) / 12); };
  A.midi = midi;

  A.unlock = function () {
    if (A.ctx) { if (A.ctx.state === "suspended") A.ctx.resume().catch(function () {}); return; }
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    try {
      A.ctx = new AC();
      A.master = A.ctx.createGain();
      A.master.gain.value = 0.45;
      A.master.connect(A.ctx.destination);
    } catch (e) { A.ctx = null; }
  };
  A.suspend = function (on) {
    if (!A.ctx) return;
    if (on) A.ctx.suspend().catch(function () {}); else A.ctx.resume().catch(function () {});
  };
  A.setSfx = function (on) { A.sfxOn = !!on; };

  /* 1音。duty 付き矩形波は PeriodicWave で作る */
  var waves = {};
  function pulse(ctx, duty) {
    var k = "p" + duty;
    if (waves[k]) return waves[k];
    var n = 32, real = new Float32Array(n), imag = new Float32Array(n);
    for (var i = 1; i < n; i++) { real[i] = 0; imag[i] = (2 / (i * Math.PI)) * Math.sin(i * Math.PI * duty); }
    waves[k] = ctx.createPeriodicWave(real, imag, { disableNormalization: false });
    return waves[k];
  }
  A.tone = function (freq, o) {
    o = o || {};
    var c = A.ctx; if (!c) return;
    var t0 = c.currentTime + (o.t || 0), dur = o.dur || 0.12, vol = o.vol == null ? 0.2 : o.vol;
    var osc = c.createOscillator(), g = c.createGain();
    var type = o.type || "square";
    if (type === "pulse25") osc.setPeriodicWave(pulse(c, 0.25));
    else if (type === "pulse12") osc.setPeriodicWave(pulse(c, 0.125));
    else osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    if (o.slide) osc.frequency.exponentialRampToValueAtTime(Math.max(30, freq * o.slide), t0 + dur);
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(vol, t0 + (o.attack || 0.004));
    if (o.hold) g.gain.setValueAtTime(vol, t0 + dur - 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(g); g.connect(o.dest || A.master);
    osc.start(t0); osc.stop(t0 + dur + 0.03);
  };
  A.noise = function (o) {
    o = o || {};
    var c = A.ctx; if (!c) return;
    var t0 = c.currentTime + (o.t || 0), dur = o.dur || 0.2, vol = o.vol == null ? 0.08 : o.vol;
    var len = Math.max(1, Math.floor(c.sampleRate * dur)), buf = c.createBuffer(1, len, c.sampleRate), d = buf.getChannelData(0);
    /* NES 風の 15bit LFSR ノイズ */
    var lfsr = 1, step = Math.max(1, Math.floor(c.sampleRate / (o.rate || 22000))), v = 0;
    for (var i = 0; i < len; i++) {
      if (i % step === 0) { var b = (lfsr ^ (lfsr >> 1)) & 1; lfsr = (lfsr >> 1) | (b << 14); v = (lfsr & 1) ? 1 : -1; }
      d[i] = v;
    }
    var src = c.createBufferSource(); src.buffer = buf;
    var g = c.createGain();
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(vol, t0 + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(g); g.connect(A.master); src.start(t0);
  };

  /* ジングル表：data/jingles.js があればそれを使う。各音は [midi, t, dur, type, vol] */
  var BUILTIN = {
    cursor: [[88, 0, 0.03, "pulse25", 0.06]],
    decide: [[84, 0, 0.05, "square", 0.1], [91, 0.05, 0.08, "square", 0.1]],
    cancel: [[79, 0, 0.05, "square", 0.08], [72, 0.05, 0.08, "square", 0.08]],
    tap: [[96, 0, 0.025, "triangle", 0.08]],
    error: [[52, 0, 0.12, "pulse12", 0.1], [50, 0.1, 0.16, "pulse12", 0.1]],
    boot: [[84, 0, 0.05, "square", 0.14], [91, 0.055, 0.14, "square", 0.14]],
    cart: [[60, 0, 0.04, "pulse12", 0.1], [72, 0.04, 0.06, "pulse12", 0.1]],
    save: [[76, 0, 0.06, "triangle", 0.12], [83, 0.06, 0.06, "triangle", 0.12], [88, 0.12, 0.16, "triangle", 0.12]],
    open: [[72, 0, 0.05, "triangle", 0.08], [79, 0.05, 0.08, "triangle", 0.08]],
    close: [[79, 0, 0.05, "triangle", 0.07], [72, 0.05, 0.08, "triangle", 0.07]],
    accept: [[72, 0, 0.07, "square", 0.1], [76, 0.07, 0.07, "square", 0.1], [79, 0.14, 0.14, "square", 0.1]],
    item: [[84, 0, 0.05, "square", 0.1], [88, 0.05, 0.05, "square", 0.1], [96, 0.1, 0.12, "square", 0.1]],
    clear: [[72, 0, 0.1, "square", 0.12], [76, 0.1, 0.1, "square", 0.12], [79, 0.2, 0.1, "square", 0.12], [84, 0.3, 0.3, "square", 0.14],
            [60, 0.3, 0.3, "triangle", 0.1], [67, 0.3, 0.3, "triangle", 0.1], [79, 0.6, 0.14, "square", 0.1], [84, 0.74, 0.5, "square", 0.14], [64, 0.74, 0.5, "triangle", 0.1]],
    rank: [[79, 0, 0.08, "square", 0.1], [83, 0.08, 0.08, "square", 0.1], [86, 0.16, 0.08, "square", 0.1], [91, 0.24, 0.4, "square", 0.12], [67, 0.24, 0.4, "triangle", 0.1]],
    step: [[50, 0, 0.02, "triangle", 0.03]],
    bump: [[45, 0, 0.05, "pulse12", 0.05]],
    elevator: [[64, 0, 0.3, "triangle", 0.06, 1.5]]
  };
  A.play = function (name) {
    if (!A.sfxOn || !A.ctx) return;
    var seq = (NT.DATA.JINGLES && NT.DATA.JINGLES[name]) || BUILTIN[name];
    if (!seq) return;
    if (name === "cart") A.noise({ dur: 0.08, vol: 0.05 });
    seq.forEach(function (n) { A.tone(midi(n[0]), { t: n[1], dur: n[2], type: n[3], vol: n[4], slide: n[5] }); });
  };
  /* 簡易ループ BGM（EDとタイトルで使う短いフレーズ）。tracks: [{notes:[midi|0,...], type, vol}]、step 秒 */
  A.startMusic = function (song) {
    A.stopMusic();
    if (!A.ctx || !song) return;
    var c = A.ctx, i = 0, t = c.currentTime + 0.1, step = song.step || 0.2;
    var len = song.tracks[0].notes.length;
    A.musicTimer = setInterval(function () {
      if (!A.ctx) return;
      while (t < c.currentTime + 0.5) {
        song.tracks.forEach(function (tr) {
          var n = tr.notes[i % len];
          if (n) A.tone(midi(n), { t: t - c.currentTime, dur: step * (tr.len || 0.9), type: tr.type || "square", vol: tr.vol || 0.05 });
        });
        i++; t += step;
      }
    }, 120);
  };
  A.stopMusic = function () { if (A.musicTimer) { clearInterval(A.musicTimer); A.musicTimer = null; } };
})();
