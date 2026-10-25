/* トークンの水 — 出典と計算式。数値は params.json（Python の集計器と共有）にだけ書く。docs/02 と一致させる。
 * 鎖: トークン → 電力（Wh/1,000 トークン） → 水（施設内 WUE + 発電側の水、L/kWh） */

import params from './params.json';

export type SourceId = 'G1' | 'V1' | 'O1' | 'J1' | 'MR1' | 'URI1' | 'PR1' | 'A1' | 'M1' | 'L1' | 'G2' | 'MS1' | 'MI1' | 'WP1' | 'T1' | 'TD1' | 'HUB' | 'MODELS';

export interface Source {
  id: SourceId;
  title: string;
  org: string;
  year: string;
  url: string;
  value: string;
  note?: string;
}

export const SOURCES: Record<SourceId, Source> = {
  G1: { id: 'G1', title: 'Measuring the environmental impact of AI inference', org: 'Google', year: '2025-08', url: 'https://www.techrepublic.com/article/news-google-gemini-ai-environmental-impact-methodology/', value: 'Gemini アプリの中央値テキストプロンプト 1 回 = 0.24 Wh、0.26 mL（施設内）', note: 'トークン数は非公開。1,000 トークン ≈ 0.3 Wh は本アプリの換算' },
  V1: { id: 'V1', title: 'GPT-4o の 1,000 トークンのやり取りの環境負荷推計', org: 'Vanderbilt Young Scientist Journal', year: '2025', url: 'https://wp0.vanderbilt.edu/youngscientistjournal/?p=7246', value: '1,000 トークン ≈ 1.1 Wh、3.6 mL、0.38 gCO2', note: '学生誌の推計。O1 と桁が合う' },
  O1: { id: 'O1', title: 'The Gentle Singularity', org: 'OpenAI（S. Altman）', year: '2025-06', url: 'https://davidmytton.blog/chatgpt-energy-usage-is-0-34-wh-per-query/', value: '平均的なクエリ 1 回 = 0.34 Wh、約 0.32 mL', note: '方法は非公開' },
  J1: { id: 'J1', title: 'How Hungry is AI? Benchmarking Energy, Water, and Carbon Footprint of LLM Inference', org: 'Jegham ら（arXiv 2505.09598）', year: '2025', url: 'https://arxiv.org/abs/2505.09598', value: '推論モデルの長文プロンプト 1 回 > 29 Wh。短いクエリ 0.42 Wh', note: '30 モデルの API 計測から推計' },
  MR1: { id: 'MR1', title: 'Energy Use of AI Inference: Efficiency Pathways and Test-Time Compute', org: 'Microsoft Research（Oviedo ら、Joule 掲載）', year: '2025-09 / 2026', url: 'https://arxiv.org/abs/2509.20241', value: '最前線級モデルの典型クエリ 中央値 0.31 Wh（四分位 0.16〜0.60）。15 倍長い推論クエリで 3.91 Wh（約 13 倍）', note: 'H100 ノードでのボトムアップ推計。推論はトークン数が増えることで効き、トークンあたりはモデルの大きさで決まる' },
  URI1: { id: 'URI1', title: 'GPT-5 の 1,000 トークン応答の電力推計', org: 'University of Rhode Island（DCD 報道）', year: '2025-08', url: 'https://www.datacenterdynamics.com/en/news/gpt-5-could-require-significantly-more-energy-per-chatgpt-response-compared-to-prior-versions-report/', value: '約 1,000 トークンの応答で平均 18 Wh 超、最大 40 Wh', note: '多くの仮定を含む推計。上限の目安として使う' },
  MODELS: { id: 'MODELS', title: 'モデル名の例示', org: '各社の公表と報道（2026-10 時点）', year: '2026-10', url: 'methodology.html#models', value: 'Claude Opus 5.5 / Sonnet 5.5 / Haiku 5.5 / Fable 5.1、GPT-6 Astra / Sol / Luna / Instant、GPT-6.1 Sol、Gemini 4 Argon / 3.8 Flash / 3.5 Flash-Lite / 3.1 Pro、DeepSeek V4.1 Flash、Kimi K3、Muse Wonder', note: '例示は時点のもので、各モデルの実測値ではない。級の電力は MR1 / G1 / J1 / URI1 から置いた' },
  PR1: { id: 'PR1', title: 'Pricing / Prompt caching', org: 'Anthropic', year: '2026-10', url: 'https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching', value: 'キャッシュ読み 0.1 倍、5 分書き 1.25 倍、1 時間書き 2 倍（入力価格比）。出力は入力の 5 倍', note: '価格を計算量の目安として使う（本アプリの仮定）。キャッシュ読みは計算をほぼ省くので安い' },
  A1: { id: 'A1', title: 'データセンターの水使用量の開示', org: 'Amazon（AWS）', year: '2024', url: 'https://www.inkl.com/news/amazon-reveals-exactly-how-much-water-its-data-centers-used-last-year-and-claims-its-2-5-billion-gallons-puts-it-below-the-industry-average', value: 'WUE 0.15 L/kWh（2024）、業界平均 0.84 L/kWh', note: '事業者の自己申告' },
  M1: { id: 'M1', title: 'Measuring energy and water efficiency for Microsoft datacenters', org: 'Microsoft', year: 'FY24–FY25', url: 'https://datacenters.microsoft.com/sustainability/efficiency/', value: 'WUE 0.30 L/kWh（FY24）、0.27（FY25）', note: '自社所有の施設のみ' },
  L1: { id: 'L1', title: '2024 United States Data Center Energy Usage Report', org: 'LBNL（ローレンス・バークレー国立研究所）', year: '2024-12', url: 'https://eta-publications.lbl.gov/publications/2024-lbnl-data-center-energy-usage-report', value: '2023 年: 電力 176 TWh、施設内の水 660 億 L、発電側の水 約 8,000 億 L', note: '本アプリの 0.375 L/kWh（施設内）と 4.5 L/kWh（発電側）はこの比から計算' },
  G2: { id: 'G2', title: 'Google が月 1.3 京トークンを処理', org: 'Google（S. Pichai / D. Hassabis）', year: '2025-10', url: 'https://the-decoder.com/google-boasts-1-3-quadrillion-tokens-each-month-but-the-figure-is-mostly-window-dressing/', value: '1.3 × 10^15 トークン/月 ≈ 4.9 億トークン/秒', note: '推論モデルの内部トークンを含むため、利用量より計算負荷に近い' },
  MS1: { id: 'MS1', title: 'Microsoft FY25 Q4 決算説明', org: 'Microsoft', year: '2025-07', url: 'https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/TranscriptQandAFY25q4', value: 'Foundry API で年 500 兆トークン超 ≈ 0.16 億トークン/秒', note: 'Azure 上の API 経由分のみ' },
  MI1: { id: 'MI1', title: 'Our contribution to a global environmental standard for AI', org: 'Mistral AI', year: '2025-07', url: 'https://mistral.ai/news/our-contribution-to-a-global-environmental-standard-for-ai', value: 'Mistral Large 2 の 400 トークン応答 1 回 = 45 mL、1.14 gCO2e', note: '第三者レビュー済み LCA。学習の按分を含む' },
  WP1: { id: 'WP1', title: 'GPT-4 で 100 語のメール 1 通に約 519 mL', org: 'Washington Post × UC Riverside', year: '2024-09', url: 'https://www.yahoo.com/news/using-gpt-4-generate-100-120051801.html', value: '1 通 = 519 mL（州により 235〜1,408 mL）', note: '後に研究者が約 15 mL/回へ下方修正と報道' },
  T1: { id: 'T1', title: '用途別使用量の目安（シャワー）', org: '東京都水道局', year: '2023', url: 'https://www.waterworks.metro.tokyo.lg.jp/documents/d/waterworks/bunkyo_202312', value: 'シャワー 1 分 ≈ 12 L' },
  TD1: { id: 'TD1', title: '東京ドームの容積', org: '東京ドームシティ', year: '公式 FAQ', url: 'https://www.tokyo-dome.co.jp/faq/dome/', value: '124 万 m³' },
  HUB: { id: 'HUB', title: '代表的なデータセンター拠点と想定シェア', org: '本アプリの仮定', year: '2026', url: 'methodology.html#hubs', value: '20 拠点。シェアは公表されていないため、主要クラウドのリージョン分布から置いた仮定', note: '実測ではない' },
};

export type Level = 'low' | 'mid' | 'high';

/** 出典 ID のない数は画面に出さない */
export interface Quantity {
  value: number;
  low?: number;
  high?: number;
  unit: string;
  sourceIds: SourceId[];
}

/** 利用者が動かせる前提 */
export interface Assumptions {
  whPerKTok: number;      // Wh / 1,000 トークン（世界ティッカー用の平均）
  wue: number;            // 施設内の冷却水 L/kWh
  offsite: number;        // 発電側の水 L/kWh
  worldMultiplier: number; // Google + Microsoft の公表値に掛ける「その他」の倍率
}

type Preset = Assumptions & { label: string; sourceIds: SourceId[] };
export const PRESETS = params.presets as Record<Level, Preset>;

/** スライダーの範囲 */
export const RANGES = params.ranges as Record<keyof Assumptions, { min: number; max: number; step: number; unit: string }>;

/** 「あなたのトークン」のモデルの級。
 * 級はモデルの大きさ（価格帯）で分ける。推論（思考）はトークン数が増えることで効くので、
 * 思考トークンは出力トークンとして課金される分をトークン数に含めればよい（MR1）。
 * 例示は modelsAsOf 時点（MODELS）。 */
export type ModelClass = 'light' | 'standard' | 'frontier' | 'upper';
export interface ModelClassDef { label: string; examples: string[]; whPerKTok: number; sourceIds: SourceId[] }
export const MODELS_AS_OF: string = params.modelsAsOf;
export const MODEL_CLASSES = params.modelClasses as Record<ModelClass, ModelClassDef>;

/** トークンの重み（価格比 = 計算量の目安、PR1） */
export const TOKEN_WEIGHTS = params.tokenWeights as { input: number; cacheWrite5m: number; cacheWrite1h: number; cacheRead: number; output: number; sourceIds: SourceId[] };
export function classForModelId(id: string | undefined | null): ModelClass {
  const m = (id ?? '').toLowerCase();
  for (const r of params.modelIdToClass) if (m.includes(r.match)) return r.class as ModelClass;
  return params.defaultModelClass as ModelClass;
}

/** 世界のトークン量の土台（トークン/秒） */
export const WORLD_BASE = {
  google: params.world.googleTokensPerMonth / ((365.25 / 12) * 86400),
  microsoft: params.world.microsoftTokensPerYear / (365.25 * 86400),
  sourceIds: params.world.sourceIds as SourceId[],
};
export const WORLD_BASE_TPS = WORLD_BASE.google + WORLD_BASE.microsoft;

/** 換算対象（L） */
export const COMPARISONS = params.comparisons as { id: string; name: string; unit: string; liters: number; sourceIds: SourceId[] }[];
export const BOTTLE_LITERS: number = params.bottleLiters;

export interface WaterResult {
  tokens: number;
  kWh: Quantity;
  onsiteL: Quantity;
  offsiteL: Quantity;
  totalL: Quantity;
}

/** トークン数 → 電力と水 */
export function waterFor(tokens: number, whPerKTok: number, wue: number, offsite: number, sourceIds: SourceId[]): WaterResult {
  const kWh = (tokens / 1000) * whPerKTok / 1000;
  const onsiteL = kWh * wue;
  const offsiteL = kWh * offsite;
  return {
    tokens,
    kWh: { value: kWh, unit: 'kWh', sourceIds },
    onsiteL: { value: onsiteL, unit: 'L', sourceIds },
    offsiteL: { value: offsiteL, unit: 'L', sourceIds: ['L1'] },
    totalL: { value: onsiteL + offsiteL, unit: 'L', sourceIds: [...sourceIds, 'L1'] },
  };
}

export interface WorldRates {
  tokensPerSec: number;
  watts: number;          // 平均電力 W
  litersPerSecOnsite: number;
  litersPerSecTotal: number;
}

/** 世界の毎秒の量 */
export function worldRates(a: Assumptions): WorldRates {
  const tokensPerSec = WORLD_BASE_TPS * a.worldMultiplier;
  const watts = tokensPerSec * (a.whPerKTok / 1000) * 3600; // Wh/s → W
  const kW = watts / 1000;
  return {
    tokensPerSec,
    watts,
    litersPerSecOnsite: (kW * a.wue) / 3600,
    litersPerSecTotal: (kW * (a.wue + a.offsite)) / 3600,
  };
}

/** 開いてからの累計。足し込まず、経過秒から毎回計算する */
export function worldSince(elapsedSec: number, a: Assumptions) {
  const r = worldRates(a);
  return { tokens: r.tokensPerSec * elapsedSec, litersOnsite: r.litersPerSecOnsite * elapsedSec, litersTotal: r.litersPerSecTotal * elapsedSec };
}

/** 1 回のプロンプトあたりの水（他の公表値と並べるための換算。1 回 ≈ 300 トークンと置く） */
export const TOKENS_PER_PROMPT: number = params.tokensPerPrompt;

/** 器（寸法は m、実寸比）と梯子の目盛り */
export interface Vessel { id: 'bottle' | 'bath' | 'pool' | 'dome'; name: string; unit: string; liters: number; w: number; h: number; maxCopies: number }
export const VESSELS = params.vessels as Vessel[];
export type LadderScale = 'now' | 'week' | 'year' | 'world';
export const LADDER_SCALES = params.ladderScales as { id: LadderScale; label: string; help: string }[];

/** 量に合う器: 個数が上限に収まる最初の器（ボトルは 2 本以上ならまず浴槽を検討しない＝棚で見せる） */
export function chooseVessel(liters: number): { vessel: Vessel; count: number; full: number; partial: number } {
  let v = VESSELS[VESSELS.length - 1]!;
  for (const x of VESSELS) { if (Math.ceil(liters / x.liters) <= x.maxCopies) { v = x; break; } }
  const n = liters / v.liters;
  return { vessel: v, count: n, full: Math.floor(n), partial: n - Math.floor(n) };
}

/** 梯子の目盛りの量（L）。today/week は実ログ（無ければ 0）、world は前提から */
export function ladderLiters(scale: LadderScale, todayL: number, weekL: number, a: Assumptions): number {
  switch (scale) {
    case 'now': return todayL;
    case 'week': return weekL;
    case 'year': return todayL * 365;
    case 'world': return worldRates(a).litersPerSecTotal * 86400;
  }
}

/** トークンの内訳（Claude Code の usage と同じ区分） */
export interface UsageTokens { input: number; cw5m: number; cw1h: number; cr: number; out: number }

/** 内訳 → 加重トークン・kWh・L（scripts/water_meter.py と同じ式。前提の幅は 中 に対する Wh の比で掛ける） */
export function usageWater(t: UsageTokens, cls: ModelClass, level: Level, opts: { noCache?: boolean } = {}) {
  const w = TOKEN_WEIGHTS;
  const weighted = opts.noCache
    ? (t.input + t.cw5m + t.cw1h + t.cr) * 1 + t.out * w.output
    : t.input * w.input + t.cw5m * w.cacheWrite5m + t.cw1h * w.cacheWrite1h + t.cr * w.cacheRead + t.out * w.output;
  const p = PRESETS[level];
  const kWh = (weighted / 1000) * MODEL_CLASSES[cls].whPerKTok * (p.whPerKTok / PRESETS.mid.whPerKTok) / 1000;
  return { weighted, kWh, liters: kWh * (p.wue + p.offsite) };
}
