// 陸地の点群を world-atlas（Natural Earth 110m）から作り、src/data/land-points.json に書く。
// 実行: npm run data。ランタイムは地図データを読まず、この点群だけを描く。
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { feature } from 'topojson-client';

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const topo = JSON.parse(readFileSync(require.resolve('world-atlas/land-110m.json'), 'utf8'));
type Geom = { type: string; coordinates: unknown };
const fc = feature(topo, topo.objects.land) as unknown as { type: string; geometry?: Geom; features?: { geometry: Geom }[] };
const geoms: Geom[] = fc.features ? fc.features.map((f) => f.geometry) : fc.geometry ? [fc.geometry] : [];
const polys: number[][][][] = [];
for (const g of geoms) {
  if (g.type === 'MultiPolygon') polys.push(...(g.coordinates as number[][][][]));
  else if (g.type === 'Polygon') polys.push(g.coordinates as number[][][]);
}

function inRing(lon: number, lat: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i] as [number, number];
    const [xj, yj] = ring[j] as [number, number];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function onLand(lon: number, lat: number): boolean {
  for (const poly of polys) {
    const outer = poly[0];
    if (!outer || !inRing(lon, lat, outer)) continue;
    let hole = false;
    for (let k = 1; k < poly.length; k++) if (inRing(lon, lat, poly[k] as number[][])) { hole = true; break; }
    if (!hole) return true;
  }
  return false;
}

// フィボナッチ球で均等にサンプルし、陸だけ残す
const N = Number(process.argv[2] || 42000);
const golden = Math.PI * (3 - Math.sqrt(5));
const out: number[] = [];
for (let i = 0; i < N; i++) {
  const y = 1 - (i / (N - 1)) * 2;
  const lat = (Math.asin(y) * 180) / Math.PI;
  const lon = ((((i * golden) % (2 * Math.PI)) * 180) / Math.PI + 180) % 360 - 180;
  if (onLand(lon, lat)) out.push(Math.round(lat * 100), Math.round(lon * 100));
}
const path = resolve(here, '../src/data/land-points.json');
writeFileSync(path, JSON.stringify({ scale: 100, n: out.length / 2, points: out }));
console.log(`land points: ${out.length / 2} / ${N} sampled → ${path}`);
