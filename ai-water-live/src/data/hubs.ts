/* 代表的なデータセンター拠点。シェアは公表されていない仮定（出典 HUB）。wueFactor は気候による施設内 WUE の目安倍率（乾燥・高温 > 1、冷涼 < 1）。 */
export interface Hub { id: string; name: string; region: string; lat: number; lon: number; share: number; wueFactor: number }

export const HUBS: Hub[] = [
  { id: 'iad', name: '北バージニア', region: '米国東部', lat: 39.04, lon: -77.49, share: 20, wueFactor: 1.0 },
  { id: 'pdx', name: 'オレゴン', region: '米国西部', lat: 45.52, lon: -122.99, share: 8, wueFactor: 0.7 },
  { id: 'cbf', name: 'アイオワ', region: '米国中部', lat: 41.26, lon: -95.86, share: 7, wueFactor: 1.0 },
  { id: 'dfw', name: 'ダラス', region: '米国南部', lat: 32.78, lon: -96.80, share: 6, wueFactor: 1.3 },
  { id: 'phx', name: 'フェニックス', region: '米国南西部', lat: 33.45, lon: -112.07, share: 5, wueFactor: 1.5 },
  { id: 'cmh', name: 'オハイオ', region: '米国中西部', lat: 39.96, lon: -83.00, share: 5, wueFactor: 1.0 },
  { id: 'dub', name: 'ダブリン', region: '欧州', lat: 53.35, lon: -6.26, share: 6, wueFactor: 0.6 },
  { id: 'lhr', name: 'ロンドン', region: '欧州', lat: 51.51, lon: -0.13, share: 4, wueFactor: 0.7 },
  { id: 'fra', name: 'フランクフルト', region: '欧州', lat: 50.11, lon: 8.68, share: 5, wueFactor: 0.8 },
  { id: 'ams', name: 'アムステルダム', region: '欧州', lat: 52.37, lon: 4.90, share: 3, wueFactor: 0.7 },
  { id: 'par', name: 'パリ', region: '欧州', lat: 48.86, lon: 2.35, share: 2, wueFactor: 0.8 },
  { id: 'arn', name: 'ストックホルム', region: '北欧', lat: 59.33, lon: 18.07, share: 2, wueFactor: 0.5 },
  { id: 'sin', name: 'シンガポール', region: 'アジア', lat: 1.35, lon: 103.82, share: 5, wueFactor: 1.3 },
  { id: 'tyo', name: '東京', region: '日本', lat: 35.68, lon: 139.69, share: 6, wueFactor: 1.0 },
  { id: 'osa', name: '大阪', region: '日本', lat: 34.69, lon: 135.50, share: 2, wueFactor: 1.0 },
  { id: 'sel', name: 'ソウル', region: 'アジア', lat: 37.57, lon: 126.98, share: 3, wueFactor: 0.9 },
  { id: 'syd', name: 'シドニー', region: 'オセアニア', lat: -33.87, lon: 151.21, share: 3, wueFactor: 1.1 },
  { id: 'bom', name: 'ムンバイ', region: 'インド', lat: 19.08, lon: 72.88, share: 4, wueFactor: 1.4 },
  { id: 'gru', name: 'サンパウロ', region: '南米', lat: -23.55, lon: -46.63, share: 3, wueFactor: 1.1 },
  { id: 'jnb', name: 'ヨハネスブルグ', region: 'アフリカ', lat: -26.20, lon: 28.05, share: 1, wueFactor: 1.2 },
];

export const HUB_SHARE_TOTAL = HUBS.reduce((s, h) => s + h.share, 0);
