import * as THREE from 'three';
import type { Hub } from '../data/hubs';
import { latLonToVec3, rng } from './util';

/* 蒸発: 拠点から立ち上って消える粒。位置は頂点シェーダが uTime から計算する。 */
const PER_HUB = 160;

const vert = /* glsl */ `
  attribute vec3 aOrigin; attribute vec3 aDrift; attribute float aPhase; attribute float aSpeed; attribute float aWeight;
  uniform float uTime; uniform float uRate; uniform float uPixelRatio;
  varying float vAlpha;
  void main() {
    float t = fract(aPhase + uTime * aSpeed * (0.6 + 0.8 * uRate));
    vec3 n = normalize(aOrigin);
    vec3 p = aOrigin + n * (t * (0.16 + 0.12 * aWeight)) + aDrift * t * 0.6;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    float show = step(aPhase, 0.25 + 0.75 * uRate);
    gl_PointSize = (1.6 + 2.4 * (1.0 - t)) * uPixelRatio * (2.6 / -mv.z) * show;
    vec3 wn = normalize(mat3(modelMatrix) * n);
    vec3 v = normalize(cameraPosition - (modelMatrix * vec4(p, 1.0)).xyz);
    float facing = smoothstep(-0.15, 0.25, dot(wn, v));
    vAlpha = (1.0 - t) * smoothstep(0.0, 0.15, t) * facing * show * (0.5 + 0.5 * aWeight);
  }`;
const frag = /* glsl */ `
  uniform vec3 uColor; varying float vAlpha;
  void main() {
    vec2 c = gl_PointCoord - 0.5; float d = dot(c, c); if (d > 0.25) discard;
    gl_FragColor = vec4(uColor, smoothstep(0.25, 0.0, d) * vAlpha);
  }`;

export interface Evap { points: THREE.Points; update(t: number, rate: number): void }

export function createEvap(hubs: Hub[], pixelRatio: number): Evap {
  const rand = rng(7);
  const total = hubs.reduce((s, h) => s + h.share, 0);
  const N = hubs.length * PER_HUB;
  const O = new Float32Array(N * 3), D = new Float32Array(N * 3), PH = new Float32Array(N), SP = new Float32Array(N), W = new Float32Array(N);
  let i = 0;
  for (const h of hubs) {
    const o = latLonToVec3(h.lat, h.lon, 1.012);
    const w = Math.sqrt(h.share / total) / Math.sqrt(0.2);
    for (let k = 0; k < PER_HUB; k++, i++) {
      // 拠点の周りに散らす（シェアが大きいほど広く）
      const spread = 0.015 + 0.05 * w;
      const jitter = new THREE.Vector3(rand() - 0.5, rand() - 0.5, rand() - 0.5).multiplyScalar(spread);
      const op = o.clone().add(jitter).normalize().multiplyScalar(1.012);
      O.set([op.x, op.y, op.z], i * 3);
      D.set([(rand() - 0.5) * 0.06, (rand() - 0.5) * 0.06, (rand() - 0.5) * 0.06], i * 3);
      PH[i] = rand(); SP[i] = 0.25 + rand() * 0.25; W[i] = Math.min(1, w);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
  geo.setAttribute('aOrigin', new THREE.BufferAttribute(O, 3)); geo.setAttribute('aDrift', new THREE.BufferAttribute(D, 3));
  geo.setAttribute('aPhase', new THREE.BufferAttribute(PH, 1)); geo.setAttribute('aSpeed', new THREE.BufferAttribute(SP, 1)); geo.setAttribute('aWeight', new THREE.BufferAttribute(W, 1));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 2);
  const mat = new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uRate: { value: 0.5 }, uPixelRatio: { value: pixelRatio }, uColor: { value: new THREE.Color('#dff3ff') } },
    vertexShader: vert, fragmentShader: frag, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  return { points, update(t, rate) { mat.uniforms.uTime!.value = t; mat.uniforms.uRate!.value = rate; } };
}
