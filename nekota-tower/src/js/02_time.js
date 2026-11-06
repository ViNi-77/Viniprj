/* 実時間。日付キーは常に日本時間。Date.now をラップしてテストで差し替えられるようにする */
(function () {
  "use strict";
  var NT = window.NT;
  var T = NT.Time = {};
  var fmt = null;
  try {
    fmt = new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  } catch (e) { fmt = null; }

  T.now = function () { return Date.now(); };

  /* 'YYYY-MM-DD'（JST）*/
  T.jstKey = function (ms) {
    if (ms === undefined) ms = T.now();
    if (fmt) {
      var p = {};
      fmt.formatToParts(new Date(ms)).forEach(function (x) { p[x.type] = x.value; });
      return p.year + "-" + p.month + "-" + p.day;
    }
    return new Date(ms + 9 * 3600 * 1000).toISOString().slice(0, 10);
  };
  /* JST の時:分 */
  T.jstHM = function (ms) {
    if (ms === undefined) ms = T.now();
    if (fmt) {
      var p = {};
      fmt.formatToParts(new Date(ms)).forEach(function (x) { p[x.type] = x.value; });
      return (p.hour === "24" ? "00" : p.hour) + ":" + p.minute;
    }
    var d = new Date(ms + 9 * 3600 * 1000);
    return NT.Util.pad2(d.getUTCHours()) + ":" + NT.Util.pad2(d.getUTCMinutes());
  };
  T.keyToUTC = function (key) { var a = key.split("-"); return Date.UTC(+a[0], +a[1] - 1, +a[2]); };
  T.nextKey = function (key) { return new Date(T.keyToUTC(key) + 86400000).toISOString().slice(0, 10); };
  T.prevKey = function (key) { return new Date(T.keyToUTC(key) - 86400000).toISOString().slice(0, 10); };
  T.diffDays = function (a, b) { return Math.round((T.keyToUTC(b) - T.keyToUTC(a)) / 86400000); };
  T.yearOf = function (key) { return +key.slice(0, 4); };
  T.mmdd = function (key) { return key.slice(5); };

  /* 局面。prep: 〜11/30 ×1, dec: 12/1〜27 ×2, final: 12/28〜31 ×7, over: 年が明けた */
  T.phase = function (key, year) {
    key = key || T.jstKey();
    year = year || T.yearOf(key);
    if (T.yearOf(key) > year) return "over";
    var md = T.mmdd(key);
    if (md < "12-01") return "prep";
    if (md < "12-28") return "dec";
    return "final";
  };
  T.mult = function (phase) { return { prep: 1, dec: 2, final: 7, over: 0 }[phase] || 1; };
  /* 12/31 までの残り日数（当日を含む）*/
  T.daysLeft = function (key, year) {
    key = key || T.jstKey();
    year = year || T.yearOf(key);
    var end = year + "-12-31";
    return Math.max(0, T.diffDays(key, end) + 1);
  };
  /* 体感残り日数（演出用の換算）*/
  T.feelDays = function (key, year) {
    key = key || T.jstKey();
    year = year || T.yearOf(key);
    var total = 0, k = key, end = year + "-12-31";
    var guard = 0;
    while (k <= end && guard++ < 400) { total += T.mult(T.phase(k, year)); k = T.nextKey(k); }
    return total;
  };
  /* 時計の疑い：保存時刻が未来、または最後に見た日付より過去 */
  T.clockSuspect = function (rec) {
    if (!rec) return false;
    var now = T.now();
    if (rec.savedAt && (new Date(rec.savedAt).getTime() - now) > 10 * 60 * 1000) return true;
    if (rec.state && rec.state.lastKey && T.jstKey(now) < rec.state.lastKey) return true;
    return false;
  };
  /* 日本の年末暦（演出用）*/
  T.calendarNote = function (key) {
    var md = T.mmdd(key || T.jstKey());
    var notes = NT.DATA.CALENDAR_NOTES || {};
    return notes[md] || null;
  };
})();
