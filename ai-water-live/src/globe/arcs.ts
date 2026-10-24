import * as THREE from 'three';
import type { Hub } from '../data/hubs';
import { latLonToVec3, arcControl, rng } from './util';
import landJson from '../data/land-points.json';

/* トークンの流れ: 陸上の出発点 → 拠点 への弧。線（流れるダッシュ）と粒（弧に沿って動く点）。
 * 位置はすべて頂点シェーダが uTime から計算する。CPU は uniform を 2 つ更新するだけ。 */

const ARCS_PER_HUB = 3, SEGS = 40, PARTICLES_PER_ARC = 70;

const lineVert = /* glsl */ `
  attribute float aT; attribute float aPhase;
  varying float vT; varying float vPhase;
  void main() { vT = aT; vPhase = aPhase; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const lineFrag = /* glsl */ `
  uniform float uTime; uniform vec3 uColor; uniform float uIntensity;
  varying float vT; varying float vPhase;
  void main() {
    float dash = fract(vT * 3.0 - uTime * 0.6 + vPhase);
    float a = smoothstep(0.0, 0.5, dash) * smoothstep(1.0, 0.7, dash);
    float ends = smoothstep(0.0, 0.08, vT) * smoothstep(1.0, 0.92, vT);
    gl_FragColor = vec4(uColor, a * ends * (0.18 + 0.35 * uIntensity));
  }`;

const ptVert = /* glsl */ `
  attribute vec3 aP0; attribute vec3 aP1; attribute vec3 aP2; attribute float aPhase; attribute float aSpeed;
  uniform float uTime; uniform float uDensity; uniform float uPixelRatio;
  varying float vAlpha;
  void main() {
    float t = fract(aPhase + uTime * aSpeed);
    float u = 1.0 - t;
    vec3 p = u * u * aP0 + 2.0 * u * t * aP1 + t * t * aP2;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    float show = step(aPhase, uDensity);
    gl_PointSize = (2.2 + 2.0 * t) * uPixelRatio * (2.6 / -mv.z) * show;
    vec3 n = normalize(mat3(modelMatrix) * p);
    vec3 v = normalize(cameraPosition - (modelMatrix * vec4(p, 1.0)).xyz);
    float facing = smoothstep(-0.2, 0.2, dot(n, v));
    vAlpha = (0.35 + 0.65 * t) * facing * show;
  }`;
const ptFrag = /* glsl */ `
  uniform vec3 uColor; varying float vAlpha;
  void main() {
    vec2 c = gl_PointCoord - 0.5; float d = dot(c, c); if (d > 0.25) discard;
    gl_FragColor = vec4(uColor, smoothstep(0.25, 0.05, d) * vAlpha);
  }`;

export interface Arcs { lines: THREE.LineSegments; particles: THREE.Points; update(t: number, density: number): void }

export function createArcs(hubs: Hub[], pixelRatio: number): Arcs {
  const rand = rng(20261021);
  const land = landJson.points as number[], scale = landJson.scale as number, nLand = land.length / 2;
  const total = hubs.reduce((s, h) => s + h.share, 0);

  const arcs: { p0: THREE.Vector3; p1: THREE.Vector3; p2: THREE.Vector3; w: number }[] = [];
  for (const h of hubs) {
    const p2 = latLonToVec3(h.lat, h.lon, 1.01);
    const n = Math.max(1, Math.round(ARCS_PER_HUB * Math.sqrt(h.share / total) * 2.2));
    for (let k = 0; k < n; k++) {
      // 出発点は陸上のどこか（拠点から遠すぎず近すぎず）
      let p0 = p2; let tries = 0;
      do { const i = Math.floor(rand() * nLand); p0 = latLonToVec3((land[i * 2] ?? 0) / scale, (land[i * 2 + 1] ?? 0) / scale, 1.005); tries++; }
      while ((p0.distanceTo(p2) < 0.25 || p0.distanceTo(p2) > 1.4) && tries < 50);
      arcs.push({ p0, p1: arcControl(p0, p2), p2, w: h.share / total });
    }
  }

  // 線
  const lpos: number[] = [], lt: number[] = [], lph: number[] = [];
  arcs.forEach((a, ai) => {
    const ph = rand();
    for (let s = 0; s < SEGS; s++) {
      for (const tt of [s / SEGS, (s + 1) / SEGS]) {
        const u = 1 - tt;
        const x = u * u * a.p0.x + 2 * u * tt * a.p1.x + tt * tt * a.p2.x;
        const y = u * u * a.p0.y + 2 * u * tt * a.p1.y + tt * tt * a.p2.y;
        const z = u * u * a.p0.z + 2 * u * tt * a.p1.z + tt * tt * a.p2.z;
        lpos.push(x, y, z); lt.push(tt); lph.push(ph + ai * 0.37);
      }
    }
  });
  const lgeo = new THREE.BufferGeometry();
  lgeo.setAttribute('position', new THREE.Float32BufferAttribute(lpos, 3));
  lgeo.setAttribute('aT', new THREE.Float32BufferAttribute(lt, 1));
  lgeo.setAttribute('aPhase', new THREE.Float32BufferAttribute(lph, 1));
  const lmat = new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color('#7fb0d8') }, uIntensity: { value: 0.5 } },
    vertexShader: lineVert, fragmentShader: lineFrag, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const lines = new THREE.LineSegments(lgeo, lmat);

  // 粒
  const N = arcs.length * PARTICLES_PER_ARC;
  const P0 = new Float32Array(N * 3), P1 = new Float32Array(N * 3), P2 = new Float32Array(N * 3), PH = new Float32Array(N), SP = new Float32Array(N);
  let i = 0;
  for (const a of arcs) {
    for (let k = 0; k < PARTICLES_PER_ARC; k++, i++) {
      P0.set([a.p0.x, a.p0.y, a.p0.z], i * 3); P1.set([a.p1.x, a.p1.y, a.p1.z], i * 3); P2.set([a.p2.x, a.p2.y, a.p2.z], i * 3);
      PH[i] = rand(); SP[i] = 0.12 + rand() * 0.1;
    }
  }
  const pgeo = new THREE.BufferGeometry();
  pgeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
  pgeo.setAttribute('aP0', new THREE.BufferAttribute(P0, 3)); pgeo.setAttribute('aP1', new THREE.BufferAttribute(P1, 3)); pgeo.setAttribute('aP2', new THREE.BufferAttribute(P2, 3));
  pgeo.setAttribute('aPhase', new THREE.BufferAttribute(PH, 1)); pgeo.setAttribute('aSpeed', new THREE.BufferAttribute(SP, 1));
  pgeo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 2);
  const pmat = new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uDensity: { value: 0.6 }, uPixelRatio: { value: pixelRatio }, uColor: { value: new THREE.Color('#bfe3ff') } },
    vertexShader: ptVert, fragmentShader: ptFrag, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const particles = new THREE.Points(pgeo, pmat);
  particles.frustumCulled = false;

  return {
    lines, particles,
    update(t, density) {
      lmat.uniforms.uTime!.value = t; lmat.uniforms.uIntensity!.value = density;
      pmat.uniforms.uTime!.value = t; pmat.uniforms.uDensity!.value = density;
    },
  };
}
