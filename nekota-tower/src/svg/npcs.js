/* NPC の SVG 文字列（ロジックなし）。32x40、足元中心が (0,0)、上が y 負。ねこ太と同じ丸い雰囲気 */
(function () {
  "use strict";
  var NT = window.NT = window.NT || {};
  NT.SVG = NT.SVG || {};

  var EYE = "#3A3A45";
  var SHADOW = '<ellipse cx="0" cy="0" rx="8" ry="2.7" fill="rgba(40,55,40,.2)"/>';

  function wrap(inner) {
    return '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="40" viewBox="-16 -36 32 40">' + SHADOW + inner + '</svg>';
  }
  // 丸い体＋頭＋足（共通シルエット）
  function base(body, feet, headY, headR) {
    return '<ellipse cx="0" cy="-6.6" rx="6.6" ry="6.6" fill="' + body + '"/>' +
      '<ellipse cx="-3" cy="-0.9" rx="2.6" ry="1.5" fill="' + feet + '"/><ellipse cx="3" cy="-0.9" rx="2.6" ry="1.5" fill="' + feet + '"/>' +
      '<ellipse cx="0" cy="' + headY + '" rx="' + headR + '" ry="' + (headR * 0.84) + '" fill="' + body + '"/>';
  }
  // 点目＋小さな口
  function dots(y, dx) {
    dx = dx || 3.4;
    return '<circle cx="' + (-dx) + '" cy="' + y + '" r="1.1" fill="' + EYE + '"/><circle cx="' + dx + '" cy="' + y + '" r="1.1" fill="' + EYE + '"/>';
  }

  var NPC = {
    // としのせの長老：灰色の老猫、白ひげ、ニット帽、鈴付きの杖
    elder: '<path d="M8 -2V-26" stroke="#8B6A4A" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="-27" r="1.8" fill="#F4D03F" stroke="#D9AE22" stroke-width="0.5"/>' +
      base("#B9B6C4", "#A09CB0", -16, 9.6) +
      '<path d="M-9 -18.8L-7.2 -26.6L-2.6 -22.6ZM9 -18.8L7.2 -26.6L2.6 -22.6Z" fill="#B9B6C4"/>' +
      '<path d="M-9.4 -21Q0 -31 9.4 -21Q0 -24.6 -9.4 -21Z" fill="#D96C6C"/><path d="M-9.6 -20.4Q0 -23.6 9.6 -20.4L9.3 -18.6Q0 -21.4 -9.3 -18.6Z" fill="#F6F0E6"/><circle cx="0" cy="-29" r="1.8" fill="#F6F0E6"/>' +
      '<path d="M-7 -16.4Q-5 -15.6 -3.6 -16.4M3.6 -16.4Q5 -15.6 7 -16.4" stroke="' + EYE + '" stroke-width="1" fill="none" stroke-linecap="round"/>' +
      '<path d="M-5.6 -13Q0 -5 5.6 -13Q0 -12.4 -5.6 -13Z" fill="#F6F0E6"/><path d="M-5.6 -13.2Q0 -11.6 5.6 -13.2" stroke="#E6E0D4" stroke-width="0.5" fill="none"/>',

    // 10 捨てる：あふれる箱を持ったたぬき
    npc10: base("#9B8C7A", "#7E7060", -16, 9.4) +
      '<path d="M-9 -19.6L-8.2 -25.4L-3.6 -22ZM9 -19.6L8.2 -25.4L3.6 -22Z" fill="#9B8C7A"/>' +
      '<path d="M-9 -16Q-4.6 -19 -1 -16Q-4.6 -13.6 -9 -16ZM9 -16Q4.6 -19 1 -16Q4.6 -13.6 9 -16Z" fill="#5A4E44"/>' + dots(-16, 4.4) +
      '<circle cx="0" cy="-12.6" r="1.1" fill="#3A3A45"/>' +
      '<rect x="-7" y="-9" width="14" height="7.4" fill="#C9A97A" stroke="#A8885C" stroke-width="0.5"/>' +
      '<circle cx="-3.6" cy="-9.6" r="2" fill="#7FC47A"/><rect x="-0.6" y="-11.6" width="3.4" height="3" fill="#6FA8DC" transform="rotate(-14 1 -10)"/><circle cx="4.6" cy="-9.4" r="1.6" fill="#F47A4B"/>',

    // 9 やめる：ポテチの袋を抱えたハムスター
    npc9: base("#F2C48D", "#E0A86C", -15.6, 9.2) +
      '<circle cx="-7.6" cy="-21" r="2.4" fill="#F2C48D"/><circle cx="7.6" cy="-21" r="2.4" fill="#F2C48D"/><circle cx="-7.6" cy="-21" r="1.2" fill="#F4AFC4"/><circle cx="7.6" cy="-21" r="1.2" fill="#F4AFC4"/>' +
      '<ellipse cx="-6.2" cy="-13.4" rx="2.4" ry="1.4" fill="#F4AFC4" opacity=".85"/><ellipse cx="6.2" cy="-13.4" rx="2.4" ry="1.4" fill="#F4AFC4" opacity=".85"/>' + dots(-16) +
      '<path d="M-1.2 -13.2q1.2 1 2.4 0" stroke="#6B4A3A" stroke-width="0.7" fill="none"/>' +
      '<path d="M-4 -11H4L4.8 -3H-4.8Z" fill="#F4D03F" stroke="#D9AE22" stroke-width="0.4"/><path d="M-4.4 -7.8H4.4" stroke="#E0574B" stroke-width="1.6"/><ellipse cx="0" cy="-4.8" rx="1.6" ry="0.9" fill="#F2C48D"/>',

    // 8 人間関係：カレンダーを持ったフクロウ
    npc8: base("#A98867", "#E0A86C", -16.4, 9.6) +
      '<path d="M-9.4 -22L-7.4 -27.6L-4 -23.4ZM9.4 -22L7.4 -27.6L4 -23.4Z" fill="#A98867"/>' +
      '<circle cx="-4.2" cy="-16.6" r="3.6" fill="#FFFDF6"/><circle cx="4.2" cy="-16.6" r="3.6" fill="#FFFDF6"/>' + dots(-16.4, 4.2) +
      '<path d="M-1.2 -13.2L0 -11.4L1.2 -13.2Z" fill="#E8A54A"/>' +
      '<rect x="-5" y="-10" width="10" height="7.6" fill="#FFFFFF" stroke="#C9C9C9" stroke-width="0.4"/><rect x="-5" y="-10" width="10" height="2.2" fill="#E0574B"/>' +
      '<path d="M-3 -6.4h2M1 -6.4h2M-3 -4.4h2M1 -4.4h2" stroke="#9FA8C4" stroke-width="0.8"/>',

    // 7 再開：壊れたギターを持ったカメ
    npc7: '<ellipse cx="0" cy="-8" rx="8.4" ry="7" fill="#6E8F5E"/><path d="M-4 -11.6l4 -2.4 4 2.4 -1 4.6H-3Z" fill="#88A978"/>' +
      '<ellipse cx="-4.6" cy="-1" rx="2.6" ry="1.6" fill="#8FB38A"/><ellipse cx="4.6" cy="-1" rx="2.6" ry="1.6" fill="#8FB38A"/>' +
      '<path d="M-3 -12V-16H3V-12Z" fill="#8FB38A"/><ellipse cx="0" cy="-19" rx="6" ry="5.2" fill="#8FB38A"/>' + dots(-19.6, 2.8) +
      '<path d="M-1 -16.4q1 0.8 2 0" stroke="#4F6B45" stroke-width="0.6" fill="none"/>' +
      '<g transform="rotate(-30 8 -10)"><ellipse cx="8" cy="-8" rx="3" ry="3.4" fill="#C98A4A"/><circle cx="8" cy="-8.4" r="1" fill="#6B4A3A"/><path d="M8 -11V-20" stroke="#8B6A4A" stroke-width="1.2"/><path d="M6.6 -17.4L8.4 -15.8M9.4 -19.6L10.8 -18" stroke="#3A3A45" stroke-width="0.4"/></g>',

    // 6 手を付ける：封筒を持ったうさぎ
    npc6: base("#F6F2EC", "#E6DCD0", -15.6, 9) +
      '<ellipse cx="-5" cy="-27" rx="2.4" ry="6" fill="#F6F2EC"/><ellipse cx="5" cy="-27" rx="2.4" ry="6" fill="#F6F2EC"/><ellipse cx="-5" cy="-27" rx="1.1" ry="4.4" fill="#F4AFC4"/><ellipse cx="5" cy="-27" rx="1.1" ry="4.4" fill="#F4AFC4"/>' +
      dots(-16) + '<path d="M-1.4 -13.2q0.7 0.9 1.4 0q0.7 0.9 1.4 0" stroke="#6B4A3A" stroke-width="0.6" fill="none"/>' +
      '<ellipse cx="-6.4" cy="-13.4" rx="1.8" ry="1" fill="#F4AFC4" opacity=".85"/><ellipse cx="6.4" cy="-13.4" rx="1.8" ry="1" fill="#F4AFC4" opacity=".85"/>' +
      '<rect x="-5" y="-9.4" width="10" height="6.4" fill="#FFFDF6" stroke="#C9C0B0" stroke-width="0.4"/><path d="M-5 -9.4L0 -5.6L5 -9.4" stroke="#C9C0B0" stroke-width="0.4" fill="none"/><circle cx="0" cy="-6.2" r="1.2" fill="#E0574B"/>',

    // 5 小さく変える：ちいさなかたつむり
    npc5: '<path d="M-9 -1Q-7 -5 -1 -4.4H8Q9 -2.6 7 -0.8Z" fill="#B8D89A"/>' +
      '<circle cx="1" cy="-8.6" r="6.2" fill="#E8B86D"/><path d="M1 -8.6m-4 0a4 4 0 1 1 4 4a2.4 2.4 0 1 1 2.4 -2.4" stroke="#B88A45" stroke-width="1" fill="none" stroke-linecap="round"/>' +
      '<path d="M-7.2 -4.8V-11M-5 -4.8V-10.6" stroke="#B8D89A" stroke-width="1.6" stroke-linecap="round"/><circle cx="-7.2" cy="-11.4" r="1.1" fill="' + EYE + '"/><circle cx="-5" cy="-11" r="1.1" fill="' + EYE + '"/>' +
      '<path d="M-8.2 -2.2q1 0.8 2 0" stroke="#4F6B45" stroke-width="0.5" fill="none"/>',

    // 4 連絡：手紙をくわえたハト
    npc4: '<ellipse cx="0" cy="-7" rx="7" ry="6.4" fill="#9FA8C4"/><path d="M-6.8 -8Q-11 -11 -9 -4Z" fill="#8A93B0"/><path d="M6.8 -8Q11 -11 9 -4Z" fill="#8A93B0"/>' +
      '<path d="M-3 -2V0.6M3 -2V0.6M-4.4 0.4L-3 -0.8L-1.6 0.4M1.6 0.4L3 -0.8L4.4 0.4" stroke="#E0574B" stroke-width="0.9" stroke-linecap="round" fill="none"/>' +
      '<circle cx="0" cy="-16.6" r="5.6" fill="#9FA8C4"/><path d="M-5.6 -17.6Q-5 -11.6 0 -11.4Q5 -11.6 5.6 -17.6Z" fill="#8FB38A" opacity=".55"/>' + dots(-17.4, 2.6) +
      '<path d="M0 -14.6L2.2 -13.4L0 -12.4Z" fill="#E8A54A"/>' +
      '<rect x="2" y="-14.4" width="7" height="4.6" fill="#FFFDF6" stroke="#C9C0B0" stroke-width="0.4"/><path d="M2 -14.4L5.5 -11.8L9 -14.4" stroke="#C9C0B0" stroke-width="0.4" fill="none"/>',

    // 3 行く予定：トランクを持ったペンギン
    npc3: '<ellipse cx="0" cy="-10" rx="7.4" ry="9.4" fill="#3F4556"/><ellipse cx="0" cy="-8.6" rx="5" ry="6.6" fill="#FFFDF6"/>' +
      '<ellipse cx="-3.4" cy="-0.8" rx="2.8" ry="1.4" fill="#E8A54A"/><ellipse cx="3.4" cy="-0.8" rx="2.8" ry="1.4" fill="#E8A54A"/>' +
      '<circle cx="0" cy="-18.6" r="6" fill="#3F4556"/><ellipse cx="0" cy="-17.4" rx="4" ry="3" fill="#FFFDF6"/>' + dots(-18.6, 2.4) +
      '<path d="M-1.4 -15.8L0 -14.2L1.4 -15.8Z" fill="#E8A54A"/>' +
      '<path d="M-8.6 -9Q-13 -5 -8.4 -4Z" fill="#3F4556"/>' +
      '<rect x="6.4" y="-8" width="7.6" height="6.2" rx="0.8" fill="#C96B4A" stroke="#8B4A32" stroke-width="0.5"/><path d="M8.6 -8V-9.6H11.8V-8" stroke="#8B4A32" stroke-width="0.7" fill="none"/><path d="M6.4 -5H14" stroke="#F4D03F" stroke-width="0.6"/>',

    // 2 新記録：ストップウォッチを持ったカエル
    npc2: '<ellipse cx="0" cy="-6.8" rx="7.4" ry="6.4" fill="#7FC47A"/><ellipse cx="0" cy="-5.4" rx="4.4" ry="3.6" fill="#DDF0C8"/>' +
      '<ellipse cx="-4.4" cy="-0.8" rx="3" ry="1.4" fill="#5FA85A"/><ellipse cx="4.4" cy="-0.8" rx="3" ry="1.4" fill="#5FA85A"/>' +
      '<ellipse cx="0" cy="-15.6" rx="8.4" ry="5.6" fill="#7FC47A"/><circle cx="-4.6" cy="-20" r="2.6" fill="#7FC47A"/><circle cx="4.6" cy="-20" r="2.6" fill="#7FC47A"/>' +
      '<circle cx="-4.6" cy="-20" r="1.3" fill="' + EYE + '"/><circle cx="4.6" cy="-20" r="1.3" fill="' + EYE + '"/>' +
      '<path d="M-4 -14q4 2.6 8 0" stroke="#4F6B45" stroke-width="0.7" fill="none" stroke-linecap="round"/><ellipse cx="-6.4" cy="-13.2" rx="1.6" ry="0.9" fill="#F4AFC4" opacity=".8"/><ellipse cx="6.4" cy="-13.2" rx="1.6" ry="0.9" fill="#F4AFC4" opacity=".8"/>' +
      '<circle cx="9.4" cy="-8.6" r="3.4" fill="#FFFFFF" stroke="#8A93B0" stroke-width="0.8"/><rect x="8.6" y="-13.2" width="1.6" height="1.4" fill="#8A93B0"/><path d="M9.4 -8.6V-10.8M9.4 -8.6L11 -7.8" stroke="#E0574B" stroke-width="0.6" stroke-linecap="round"/>',

    // 1 ホワイトタイム：クッションで眠るしろくま
    npc1: '<ellipse cx="0" cy="-1.6" rx="12" ry="3.4" fill="#F2A7B5"/><ellipse cx="0" cy="-2.6" rx="11" ry="2.2" fill="#F7BFC9"/>' +
      '<ellipse cx="1.4" cy="-7.4" rx="9.2" ry="5.2" fill="#F6F4F0"/>' +
      '<circle cx="-6.4" cy="-9.4" r="5.4" fill="#F6F4F0"/><circle cx="-9.6" cy="-13.4" r="1.7" fill="#F6F4F0"/><circle cx="-4.4" cy="-14" r="1.7" fill="#F6F4F0"/>' +
      '<path d="M-9.2 -9.4q1 -1 2 0M-5.6 -9.4q1 -1 2 0" stroke="' + EYE + '" stroke-width="0.8" fill="none" stroke-linecap="round"/><ellipse cx="-6.8" cy="-7.2" rx="1.1" ry="0.8" fill="#3A3A45"/>' +
      '<ellipse cx="-10.6" cy="-7.4" rx="1.4" ry="0.8" fill="#F4AFC4" opacity=".8"/><ellipse cx="7.6" cy="-4.4" rx="2.6" ry="1.4" fill="#E9E4DC"/>' +
      '<path d="M3 -16h2.6l-2.6 2.6h2.6M7 -21h3l-3 3h3" stroke="#8A93B0" stroke-width="0.7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',

    // 塔の主：目を閉じた雲のような白い生きもの
    boss: '<ellipse cx="0" cy="-10" rx="12" ry="8.4" fill="#FBFBFD"/><circle cx="-7" cy="-14" r="5.2" fill="#FBFBFD"/><circle cx="1" cy="-18" r="6.4" fill="#FBFBFD"/><circle cx="8" cy="-13" r="5" fill="#FBFBFD"/>' +
      '<path d="M-12 -10Q-14 -4 -8 -3M12 -10Q14 -4 8 -3" stroke="#E3E3EC" stroke-width="0.8" fill="none"/>' +
      '<path d="M-5.4 -11q1.8 -1.6 3.6 0M1.8 -11q1.8 -1.6 3.6 0" stroke="' + EYE + '" stroke-width="1" fill="none" stroke-linecap="round"/>' +
      '<path d="M-0.8 -7.6q0.8 0.9 1.6 0" stroke="#6B4A3A" stroke-width="0.6" fill="none"/>' +
      '<ellipse cx="-7.4" cy="-7.8" rx="2" ry="1.1" fill="#F4AFC4" opacity=".7"/><ellipse cx="7.4" cy="-7.8" rx="2" ry="1.1" fill="#F4AFC4" opacity=".7"/>' +
      '<circle cx="-11" cy="-22" r="1" fill="#FBFBFD" opacity=".8"/><circle cx="11" cy="-24" r="1.4" fill="#FBFBFD" opacity=".8"/>'
  };

  /**
   * @param {string} id 'elder' | 'npc10'..'npc1' | 'boss'
   * @returns {string} 完全な SVG 文字列（32x40）。未知の id は 'boss' の丸いシルエットを返す
   */
  NT.SVG.npc = function (id) {
    return wrap(NPC[id] || NPC.boss);
  };
  NT.SVG.npcIds = Object.keys(NPC);
})();
