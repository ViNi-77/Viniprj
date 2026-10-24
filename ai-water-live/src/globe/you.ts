import * as THREE from 'three';
import { latLonToVec3, rng } from './util';

/* あなたの水: 選んだ拠点から、強調色の粒が柱のように立ち上る。速さと密度は自分の L/時 に比例。 */
const N = 1400;

const vert = /* glsl */ `
  attribute vec3 aJitter; attribute float aPhase; attribute float aSpeed;
  uniform vec3 uOrigin; uniform float uTime; uniform float uRate; uniform float uPixelRatio;
  varying float vAlpha;
  void main() {
    float t = fract(aPhase + uTime * aSpeed * (0.5 + uRate));
    vec3 n = normalize(uOrigin);
    vec3 p = uOrigin + aJitter * (0.6 + t * 1.6) + n * (t * (0.22 + 0.4 * uRate));
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    float show = step(aPhase, 0.15 + 0.85 * uRate) * step(0.001, uRate);
    gl_PointSize = (3.0 + 4.0 * (1.0 - t)) * uPixelRatio * (2.6 / -mv.z) * show;
    vec3 wn = normalize(mat3(modelMatrix) * n);
    vec3 v = normalize(cameraPosition - (modelMatrix * vec4(p, 1.0)).xyz);
    vAlpha = (1.0 - t) * smoothstep(0.0, 0.1, t) * smoothstep(-0.15, 0.25, dot(wn, v)) * show;
  }`;
const frag = /* glsl */ `
  uniform vec3 uColor; varying float vAlpha;
  void main() {
    vec2 c = gl_PointCoord - 0.5; float d = dot(c, c); if (d > 0.25) discard;
    gl_FragColor = vec4(uColor, smoothstep(0.25, 0.0, d) * vAlpha);
  }`;

export interface You { points: THREE.Points; update(t: number): void; setHub(lat: number, lon: number): void; setRate(r: number): void }

export function createYou(pixelRatio: number): You {
  const rand = rng(42);
  const J = new Float32Array(N * 3), PH = new Float32Array(N), SP = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    J.set([(rand() - 0.5) * 0.018, (rand() - 0.5) * 0.018, (rand() - 0.5) * 0.018], i * 3);
    PH[i] = rand(); SP[i] = 0.18 + rand() * 0.2;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
  geo.setAttribute('aJitter', new THREE.BufferAttribute(J, 3));
  geo.setAttribute('aPhase', new THREE.BufferAttribute(PH, 1));
  geo.setAttribute('aSpeed', new THREE.BufferAttribute(SP, 1));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 2);
  const mat = new THREE.ShaderMaterial({
    uniforms: { uOrigin: { value: latLonToVec3(35.68, 139.69, 1.012) }, uTime: { value: 0 }, uRate: { value: 0 }, uPixelRatio: { value: pixelRatio }, uColor: { value: new THREE.Color('#f0905f') } },
    vertexShader: vert, fragmentShader: frag, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  return {
    points,
    update(t) { mat.uniforms.uTime!.value = t; },
    setHub(lat, lon) { (mat.uniforms.uOrigin!.value as THREE.Vector3).copy(latLonToVec3(lat, lon, 1.012)); },
    setRate(r) { mat.uniforms.uRate!.value = Math.max(0, Math.min(1, r)); },
  };
}
