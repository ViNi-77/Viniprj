/* ねこ太の SVG 文字列（ロジックなし）。32x40、足元中心が (0,0)、上が y 負 */
(function () {
  "use strict";
  var NT = window.NT = window.NT || {};
  NT.SVG = NT.SVG || {};

  var BODY = "#CDBDEC", PAW = "#B6A3DE", PINK = "#F4AFC4", BAND = "#F4D03F", STRIPE = "#D9AE22";
  var EYE = "#3A3A45", MOUTH = "#6B4A3A", WHISKER = "#8E7FB5", SALMON = "#F47A4B";

  // 影（原作 L1(8)）。揺れグループの外に置く
  var SHADOW = '<ellipse cx="0" cy="0" rx="8" ry="2.7" fill="rgba(40,55,40,.2)"/>';

  // 胴（しっぽ無し）＋前掛け。しっぽは向きごとに付ける
  var TORSO = '<ellipse cx="0" cy="-6.8" rx="6.8" ry="6.8" fill="' + BODY + '"/>' +
    '<path d="M-4.8 -8.8H4.8V-3.2Q0 -1.2 -4.8 -3.2Z" fill="#FFFDF6" stroke="#E7E0D0" stroke-width="0.4"/>' +
    '<path d="M-1.4 -8.6q1.4 1.4 2.8 0M0 -7.8l-0.9 1.8M0 -7.8l0.9 1.8" stroke="#E0D8C6" stroke-width="0.5" fill="none"/>';
  var TORSO_BACK = '<ellipse cx="0" cy="-6.8" rx="6.8" ry="6.8" fill="' + BODY + '"/>' +
    '<path d="M-4.4 -9.2Q0 -8.2 4.4 -9.2" stroke="#FFFDF6" stroke-width="0.9" fill="none" stroke-linecap="round"/>';

  // しっぽ：右側に出る版（原作）。左側は mirror で作る
  var TAIL_R = '<path d="M5.2 -4.4C10.5 -3.6 12.6 -8.6 10 -10.6" stroke="' + BODY + '" stroke-width="2.4" fill="none" stroke-linecap="round"/>';
  var TAIL_L = '<path d="M-5.2 -4.4C-10.5 -3.6 -12.6 -8.6 -10 -10.6" stroke="' + BODY + '" stroke-width="2.4" fill="none" stroke-linecap="round"/>';

  var HEAD = '<ellipse cx="0" cy="-16.4" rx="10.2" ry="8.4" fill="' + BODY + '"/>';

  // 耳（外側）。dx で片耳を少し後ろへ（3/4 向き用）
  function ears(inner, lx, rx) {
    lx = lx || 0; rx = rx || 0;
    var s = '<path d="M' + (-9.4 + lx) + ' -19L' + (-7.6 + lx) + ' -27.4L' + (-2.6 + lx) + ' -23Z" fill="' + BODY + '"/>' +
      '<path d="M' + (9.4 + rx) + ' -19L' + (7.6 + rx) + ' -27.4L' + (2.6 + rx) + ' -23Z" fill="' + BODY + '"/>';
    if (inner) {
      s += '<path d="M' + (-7.8 + lx) + ' -21.4L' + (-7.1 + lx) + ' -25.3L' + (-4.3 + lx) + ' -23Z" fill="' + PINK + '"/>' +
        '<path d="M' + (7.8 + rx) + ' -21.4L' + (7.1 + rx) + ' -25.3L' + (4.3 + rx) + ' -23Z" fill="' + PINK + '"/>';
    }
    return s;
  }

  // はちまき（帯＋縞）。結び目は向きごとに
  var BAND_BASE = '<path d="M-9.9 -20.6Q0 -24.2 9.9 -20.6L9.6 -18.4Q0 -21.8 -9.6 -18.4Z" fill="' + BAND + '"/>' +
    '<path d="M-7.5 -21.9l1.2 2M-4.5 -22.8l1.2 2M-1.5 -23.2l1.2 2M1.5 -23.2l1.2 2M4.5 -22.8l1.2 2M7.2 -21.9l1.1 2" stroke="' + STRIPE + '" stroke-width="0.7" stroke-linecap="round"/>';
  var KNOT_R = '<path d="M8.4 -21L13.4 -24.6L12.2 -19.8ZM8.6 -20.4L13.6 -18L10.4 -17.2Z" fill="' + BAND + '"/>' +
    '<circle cx="9.2" cy="-20.2" r="1.3" fill="' + STRIPE + '"/>';
  // 後ろ姿：結び目が頭の真ん中、垂れが左右下へ
  var KNOT_BACK = '<path d="M-0.6 -19.8L-4.6 -16.2L-1.4 -15.4ZM0.6 -19.8L4.6 -16.2L1.4 -15.4Z" fill="' + BAND + '"/>' +
    '<path d="M-3.4 -17.6l0.9 0.9M3.4 -17.6l-0.9 0.9" stroke="' + STRIPE + '" stroke-width="0.6" stroke-linecap="round"/>' +
    '<circle cx="0" cy="-20.2" r="1.4" fill="' + STRIPE + '"/>';

  // 顔（目・口・ほっぺ・ひげ）
  var FACE = '<ellipse cx="-3.9" cy="-15.8" rx="1.7" ry="2.1" fill="' + EYE + '"/><ellipse cx="3.9" cy="-15.8" rx="1.7" ry="2.1" fill="' + EYE + '"/>' +
    '<circle cx="-3.4" cy="-16.4" r="0.55" fill="#fff"/><circle cx="4.4" cy="-16.4" r="0.55" fill="#fff"/>' +
    '<path d="M-6.1 -17.9L-1.9 -17.3M1.9 -17.3L6.1 -17.9" stroke="' + EYE + '" stroke-width="1.1" stroke-linecap="round"/>' +
    '<path d="M-1.5 -13.1q0.75 0.9 1.5 0q0.75 0.9 1.5 0" stroke="' + MOUTH + '" stroke-width="0.7" fill="none" stroke-linecap="round"/>' +
    '<ellipse cx="-6.8" cy="-13.4" rx="1.8" ry="1" fill="' + PINK + '" opacity=".85"/><ellipse cx="6.8" cy="-13.4" rx="1.8" ry="1" fill="' + PINK + '" opacity=".85"/>';
  var WHISKERS = '<path d="M-10.6 -14.6h2.2M-10.4 -13.2h2M10.6 -14.6h-2.2M10.4 -13.2h-2" stroke="' + WHISKER + '" stroke-width="0.45" stroke-linecap="round"/>';
  // 3/4 向き：遠い側のひげは短く
  var WHISKERS_R = '<path d="M-9.2 -14.6h1.6M-9 -13.2h1.4M10.6 -14.6h-2.2M10.4 -13.2h-2" stroke="' + WHISKER + '" stroke-width="0.45" stroke-linecap="round"/>';

  // おすし＋両手。dx で手前にずらす
  function sushi(on, dx) {
    dx = dx || 0;
    if (!on) return '';
    return '<g transform="translate(' + (-0.5 + dx) + ' -9.6) rotate(-12)">' +
      '<ellipse cx="0" cy="0.6" rx="4.2" ry="1.9" fill="#FFFFFF" stroke="#E6E6E6" stroke-width="0.3"/>' +
      '<path d="M-4.6 -0.4Q0 -3.8 4.8 -0.8Q0 -0.2 -4.6 -0.4Z" fill="' + SALMON + '"/>' +
      '<path d="M-2.4 -1.4l0.9 0.9M-0.4 -2.1l0.8 1.1M1.6 -2l0.7 1.1" stroke="#FFD2BF" stroke-width="0.45"/></g>' +
      '<ellipse cx="' + (-4.6 + dx) + '" cy="-8.8" rx="1.8" ry="1.5" fill="' + BODY + '"/>' +
      '<ellipse cx="' + (4.2 + dx) + '" cy="-9.4" rx="1.8" ry="1.5" fill="' + BODY + '"/>';
  }
  // 手を振る（上げた前足）
  var WAVE = '<ellipse cx="-8.4" cy="-12.6" rx="1.8" ry="2.6" fill="' + BODY + '" transform="rotate(-24 -8.4 -12.6)"/>';

  // 足。frame で左右交互に ±0.6 ずらして一歩を示す
  function feet(frame) {
    var d = 0.6 * frame;
    return '<ellipse cx="-3" cy="' + (-0.9 + d).toFixed(1) + '" rx="2.6" ry="1.5" fill="' + PAW + '"/>' +
      '<ellipse cx="3" cy="' + (-0.9 - d).toFixed(1) + '" rx="2.6" ry="1.5" fill="' + PAW + '"/>';
  }

  function down(frame, o) {
    return TAIL_R + TORSO + feet(frame) + (o.wave ? WAVE : '') + ears(true) + HEAD + BAND_BASE + KNOT_R + FACE + WHISKERS + sushi(o.sushi, 0);
  }
  function up(frame) {
    // 後ろ姿：顔・ひげ・おすし無し。しっぽは左側へ巻き上がる
    return TAIL_L + TORSO_BACK + feet(frame) + ears(false) + HEAD + BAND_BASE + KNOT_BACK;
  }
  function right(frame, o) {
    // 3/4 向き：顔を +2 へ、左耳を少し中央寄り（後ろ）に、しっぽは遠い側（左）
    var face = '<g transform="translate(2 0)">' + FACE + WHISKERS_R + '</g>';
    return TAIL_L + TORSO + feet(frame) + (o.wave ? WAVE : '') + ears(true, 1.2, 0) + HEAD + BAND_BASE + KNOT_R + face + sushi(o.sushi, 1);
  }

  /**
   * @param {string} dir 'down'|'up'|'left'|'right'
   * @param {number} frame -1|0|1（揺れ。±3.5°）
   * @param {{sushi?:boolean, wave?:boolean}} opts
   * @returns {string} 完全な SVG 文字列（32x40、viewBox -16 -36 32 40）
   */
  NT.SVG.nekota = function (dir, frame, opts) {
    var o = opts || {};
    var s = o.sushi !== false;
    var f = frame > 0 ? 1 : frame < 0 ? -1 : 0;
    var body;
    if (dir === 'up') body = up(f);
    else if (dir === 'right') body = right(f, { sushi: s, wave: !!o.wave });
    else if (dir === 'left') body = '<g transform="scale(-1,1)">' + right(f, { sushi: s, wave: !!o.wave }) + '</g>';
    else body = down(f, { sushi: s, wave: !!o.wave });
    var rot = f * 3.5;
    return '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="40" viewBox="-16 -36 32 40">' +
      SHADOW + '<g transform="rotate(' + rot + ')">' + body + '</g></svg>';
  };
})();
