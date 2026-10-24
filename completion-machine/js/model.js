/* 補完機 — モデル（純粋関数）。画面に出るすべての数値はここから出す。
   ビルド時（Node）と実行時（ブラウザ）で同じファイルを使う。乱数は状態を持たない整数ハッシュ。 */
(function (root) {
  const CM = (root.CM = root.CM || {});
  const D = () => CM.DATA;

  /* 整数ハッシュ → [0,1)。seek 先がどこでも同じ値を返す */
  function hash(seed, a, b) {
    let h = (seed | 0) ^ 0x9e3779b9;
    h = Math.imul(h ^ (a | 0), 0x85ebca6b);
    h ^= h >>> 13;
    h = Math.imul(h ^ (b | 0), 0xc2b2ae35);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  }

  function initial() {
    const d = D();
    return {
      step: 0,
      letter: { intro: d.letter.intro, history: 0, material: 0, sample: 0, ask: 0 },
      capacity: d.deskSheets,
      rounds: 1,
      words: [],
      conditions: 1,
      dropped: 0,
      seed: d.seed,
    };
  }

  const onDesk = (s) => s.letter.intro + s.letter.history + s.letter.material + s.letter.sample + s.letter.ask;
  const usage = (s) => onDesk(s) / s.capacity;

  /* 位置 k の候補語。先頭が最もよく選ばれる語だが、重みはハッシュで揺れる */
  function candidatesOf(s, k) {
    const d = D();
    const list = d.vocabulary[k % d.vocabulary.length];
    return list.map((word, i) => ({ word, weight: (i === 0 ? 0.55 : 0.0) + hash(s.seed, k, i) * 0.45 })).sort((a, b) => b.weight - a.weight);
  }
  const pickOne = (s, k) => candidatesOf(s, k)[0].word;

  const actions = {
    write(s) {
      const d = D();
      return { ...s, step: 1, letter: { ...s.letter, ask: d.letter.ask, material: d.letter.material, sample: d.letter.sample } };
    },
    bind(s) {
      const d = D();
      return { ...s, step: 2, letter: { ...s.letter, history: d.priorRounds * d.roundSheets }, rounds: d.priorRounds + 1 };
    },
    spread(s) {
      return { ...s, step: 3 };
    },
    pick(s) {
      return { ...s, step: 4, words: [pickOne(s, 0)] };
    },
    fill(s) {
      const d = D();
      const words = [];
      for (let k = 0; k < d.sentenceLen; k++) words.push(pickOne(s, k));
      return { ...s, step: 5, words };
    },
    rounds(s) {
      const d = D();
      let next = { ...s, letter: { ...s.letter } };
      let guard = 0;
      while (onDesk(next) <= next.capacity && guard++ < 50) {
        next.rounds += 1;
        next.letter.history += d.roundSheets;
      }
      const over = onDesk(next) - next.capacity;
      next.letter.history -= over; /* 古いやり取りから落ちる。前置きは残る */
      return { ...next, step: 6, dropped: over };
    },
    stack(s) {
      return { ...s, step: 7, conditions: D().stackedConditions };
    },
    clear(s) {
      return { ...initial(), step: 8 };
    },
  };
  const order = ["write", "bind", "spread", "pick", "fill", "rounds", "stack", "clear"];

  const step = (s, n) => actions[order[n - 1]](s);
  function stateAfter(n) {
    let s = initial();
    for (let i = 1; i <= n; i++) s = step(s, i);
    return s;
  }

  const share = (s) => Math.round(100 / s.conditions);
  const pct = (s) => Math.round(Math.min(1, usage(s)) * 100);

  function readout(s) {
    if (s.step === 0) return "机 " + pct(s) + "% · 手紙なし";
    if (s.step === 8) return "机 " + pct(s) + "% · 片付いた";
    const parts = ["机 " + pct(s) + "%"];
    if (s.words.length) parts.push(s.words.length + "語");
    if (s.dropped) parts.push(s.dropped + "枚落ちた");
    if (s.conditions > 1) parts.push("取り分 " + share(s) + "%");
    if (parts.length === 1) parts.push("紙 " + onDesk(s) + "枚");
    return parts.join(" · ");
  }

  /* ビルド時の自己チェック（docs/03 §3 と突き合わせる） */
  function selfCheck() {
    const d = D();
    const s3 = stateAfter(3), s5 = stateAfter(5), s6 = stateAfter(6), s7 = stateAfter(7);
    return {
      realSheets: Math.round(d.publicContextTokens / d.sheetTokens),
      scale: Math.round(d.publicContextTokens / d.sheetTokens / d.deskSheets),
      usageAtStep3: pct(s3),
      roundsToOverflow: s6.rounds - s3.rounds,
      droppedAtStep6: s6.dropped,
      shareAtStep7: share(s7),
      sentence: s5.words.join(""),
    };
  }

  CM.model = { hash, initial, step, stateAfter, order, onDesk, usage, pct, share, candidatesOf, readout, selfCheck };
})(typeof globalThis !== "undefined" ? globalThis : window);
