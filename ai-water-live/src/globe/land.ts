import * as THREE from 'three';
import { latLonToVec3 } from './util';
import landJson from '../data/land-points.json';

const vert = /* glsl */ `
  uniform float uSize; uniform float uPixelRatio;
  varying float vFade;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = uSize * uPixelRatio * (2.6 / -mv.z);
    // 球の裏側は薄く（法線と視線の向き）
    vec3 n = normalize(mat3(modelMatrix) * position);
    vec3 v = normalize(cameraPosition - (modelMatrix * vec4(position, 1.0)).xyz);
    vFade = smoothstep(-0.1, 0.35, dot(n, v));
  }`;
const frag = /* glsl */ `
  uniform vec3 uColor; varying float vFade;
  void main() {
    vec2 c = gl_PointCoord - 0.5; float d = dot(c, c);
    if (d > 0.25) discard;
    float a = smoothstep(0.25, 0.12, d) * vFade;
    gl_FragColor = vec4(uColor, a * 0.9);
  }`;

export function createLand(color: THREE.ColorRepresentation, pixelRatio: number): THREE.Points {
  const pts = landJson.points as number[], scale = landJson.scale as number;
  const n = pts.length / 2;
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const v = latLonToVec3((pts[i * 2] ?? 0) / scale, (pts[i * 2 + 1] ?? 0) / scale, 1.004);
    pos[i * 3] = v.x; pos[i * 3 + 1] = v.y; pos[i * 3 + 2] = v.z;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.ShaderMaterial({
    uniforms: { uSize: { value: 2.2 }, uPixelRatio: { value: pixelRatio }, uColor: { value: new THREE.Color(color) } },
    vertexShader: vert, fragmentShader: frag, transparent: true, depthWrite: false,
  });
  return new THREE.Points(geo, mat);
}
