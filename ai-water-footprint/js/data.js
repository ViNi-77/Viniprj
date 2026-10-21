/* 見えない水 — データ。数値は docs/03_数値の根拠.md と一致させる。file:// で fetch できないので JS に埋め込む。 */
window.AW = window.AW || {};

AW.DATA = {
  /** 1 回あたりの水（mL）。既定は mid。 */
  scenarios: {
    low: {
      id: 'low', label: '低', name: '事業者の公表値', mlPerPrompt: 0.26, unit: '回',
      source: { short: 'Google, 2025', title: 'Google「Measuring the environmental impact of AI inference」（2025-08）', url: 'https://www.techrepublic.com/article/news-google-gemini-ai-environmental-impact-methodology/' },
      scope: 'データセンター内の冷却水のみ。発電・学習・端末は含まない',
      note: 'Gemini アプリの中央値テキストプロンプト（0.24 Wh、0.26 mL）。OpenAI も 2025-06 に約 0.32 mL/回と述べたが方法は非公開。',
    },
    mid: {
      id: 'mid', label: '中', name: '第三者レビュー済み LCA', mlPerPrompt: 45, unit: '回',
      source: { short: 'Mistral AI, 2025', title: 'Mistral AI「Our contribution to a global environmental standard for AI」（2025-07）', url: 'https://mistral.ai/news/our-contribution-to-a-global-environmental-standard-for-ai' },
      scope: '冷却水に加え、発電・ハードウェア製造・学習の按分を含む',
      note: 'Mistral Large 2 で 400 トークンの応答 1 回。Carbone 4 / ADEME と作成、Resilio / Hubblo が査読。研究推計（Li ら 2023: GPT-3 で 10〜50 mL/回）と同じ桁。',
    },
    high: {
      id: 'high', label: '高', name: '報道で広まった上限', mlPerPrompt: 519, unit: '通',
      source: { short: 'Washington Post × UC Riverside, 2024', title: 'Washington Post × UC Riverside（2024-09）GPT-4 で 100 語のメール 1 通', url: 'https://www.yahoo.com/news/using-gpt-4-generate-100-120051801.html' },
      scope: '冷却水 + 発電の水を含むライフサイクル推計',
      note: '1 回のプロンプトではなく「メール 1 通」（呼び出し約 10 回分との指摘）。研究グループが後に GPT-4 の 1 回あたり約 15 mL に下方修正したとの報道がある。最も広まった数字として注意書き付きで残す。',
    },
  },
  scenarioOrder: ['low', 'mid', 'high'],
  defaultScenario: 'mid',

  /** 世界カウンターの基礎。ChatGPT だけ。 */
  world: {
    promptsPerDay: 2.5e9,
    label: 'ChatGPT',
    source: { short: 'OpenAI → Axios, 2025-07', title: 'OpenAI が Axios に開示（2025-07-21）、TechCrunch 報道', url: 'https://techcrunch.com/2025/07/21/chatgpt-users-send-2-5-billion-prompts-a-day/' },
  },

  /** 換算対象（mL）。verified: false は「目安」と表示する。 */
  comparisons: [
    { id: 'spoon',  name: 'ティースプーン', unit: '杯', mL: 5,       verified: true,  src: '小さじの規格' },
    { id: 'coffee', name: 'コーヒー 1 杯',   unit: '杯', mL: 150,     verified: false, src: '一般的なカップ' },
    { id: 'bottle', name: '500 mL ペットボトル', unit: '本', mL: 500, verified: true,  src: '規格' },
    { id: 'shower', name: 'シャワー 1 分',   unit: '分', mL: 12000,   verified: true,  src: '東京都水道局（1 分短縮で約 12 L）', url: 'https://www.waterworks.metro.tokyo.lg.jp/documents/d/waterworks/bunkyo_202312' },
    { id: 'bath',   name: '浴槽 1 杯',       unit: '杯', mL: 200000,  verified: false, src: '一般家庭の浴槽 200〜280 L' },
    { id: 'pool',   name: '25 m プール',     unit: '杯', mL: 390e6,   verified: false, src: '25 × 13 × 水深 1.2 m で計算' },
    { id: 'dome',   name: '東京ドーム',      unit: '杯', mL: 1.24e12, verified: true,  src: '東京ドームシティ公式 FAQ（容積 124 万 m³）', url: 'https://www.tokyo-dome.co.jp/faq/dome/' },
  ],

  /** 幕 3 の器。寸法は cm の相対値（横 w、高さ h）。shape は 0..1 の単位正方形で描き、scale(w, h) で伸ばす。 */
  vessels: [
    { id: 'bottle',  name: '500 mL ボトル', unit: '本', mL: 500,     w: 6.5,   h: 21,   maxCopies: 48 },
    { id: 'bottle2', name: '2 L ボトル',    unit: '本', mL: 2000,    w: 10,    h: 31,   maxCopies: 48 },
    { id: 'case',    name: '24 本ケース',   unit: '箱', mL: 12000,   w: 40,    h: 26,   maxCopies: 48 },
    { id: 'bath',    name: '浴槽',          unit: '杯', mL: 200000,  w: 160,   h: 60,   maxCopies: 120 },
    { id: 'pool',    name: '25 m プール',   unit: '杯', mL: 390e6,   w: 2500,  h: 150,  maxCopies: 48 },
    { id: 'dome',    name: '東京ドーム',    unit: '杯', mL: 1.24e12, w: 24400, h: 5600, maxCopies: 12 },
  ],

  /** 単位正方形（x 0..1、y 0..1、底が y=1）の輪郭。液体もこの形で切り抜く。 */
  shapes: {
    bottle:  'M.38 .07 H.62 V.15 C.62 .21 .95 .23 .95 .31 V.94 Q.95 1 .89 1 H.11 Q.05 1 .05 .94 V.31 C.05 .23 .38 .21 .38 .15 Z',
    bottle2: 'M.35 .05 H.65 V.12 C.65 .17 .97 .18 .97 .25 V.95 Q.97 1 .9 1 H.1 Q.03 1 .03 .95 V.25 C.03 .18 .35 .17 .35 .12 Z',
    case:    'M.02 .12 H.98 V.97 Q.98 1 .95 1 H.05 Q.02 1 .02 .97 Z',
    bath:    'M0 .22 H1 V.34 Q1 1 .82 1 H.18 Q0 1 0 .34 Z',
    pool:    'M0 .1 H1 V1 H0 Z',
    dome:    'M0 1 A.5 1 0 0 1 1 1 Z',
  },

  /** 幕 2 のボトル（viewBox 0 0 200 520）。液面の範囲は y=100（500 mL）〜 y=498（0） */
  bottle: {
    path: 'M84 56 L116 56 L116 82 Q116 98 140 110 Q164 122 164 152 L164 238 Q164 256 156 268 Q148 280 148 300 Q148 320 156 332 Q164 344 164 362 L164 468 Q164 498 134 498 L66 498 Q36 498 36 468 L36 362 Q36 344 44 332 Q52 320 52 300 Q52 280 44 268 Q36 256 36 238 L36 152 Q36 122 60 110 Q84 98 84 82 Z',
    yTop: 104, yBottom: 496, capacityML: 500,
  },

  /** 幕 1 の水面: 累計 L を log で 0..1 に写す上限 */
  heroMaxLiters: 1e7,

  /** 幕 3 の既定値 */
  ladderDefault: { perDay: 20, people: 1, days: 30 },
};
