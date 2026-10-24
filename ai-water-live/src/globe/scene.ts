import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { HUBS, type Hub } from '../data/hubs';
import { createLand } from './land';
import { createHubs } from './hubs';
import { createArcs } from './arcs';
import { createEvap } from './evap';
import { createYou } from './you';
import { latLonToVec3 } from './util';

export interface Globe {
  render(t: number, dt: number): void;
  readCenter(): number;
  setIntensity(tokens: number, water: number): void; // 0..1 の相対値
  setHover(id: string | null): void;
  setReduced(v: boolean): void;
  setYou(hubId: string, rate: number): void;
  faceHub(hubId: string): void;
  resize(): void;
  pickHub(clientX: number, clientY: number): Hub | null;
  hubScreen(id: string): { x: number; y: number; visible: boolean } | null;
  dispose(): void;
}

const atmoVert = /* glsl */ `varying vec3 vN; varying vec3 vP; void main(){ vN = normalize(normalMatrix * normal); vP = (modelViewMatrix * vec4(position,1.0)).xyz; gl_Position = projectionMatrix * vec4(vP, 1.0); }`;
const atmoFrag = /* glsl */ `uniform vec3 uColor; varying vec3 vN; varying vec3 vP; void main(){ float f = 1.0 - abs(dot(normalize(vN), normalize(-vP))); float a = pow(f, 3.2) * 0.9; gl_FragColor = vec4(uColor, a); }`;

export interface GlobeLayout { right: number; top: number; bottom: number }
export function createGlobe(canvas: HTMLCanvasElement, layout: () => GlobeLayout = () => ({ right: 0, top: 0, bottom: 0 })): Globe {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  const pr = Math.min(window.devicePixelRatio || 1, 1.5);
  renderer.setPixelRatio(pr);
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 50);
  camera.position.set(0, 0.45, 3.4);

  const controls = new OrbitControls(camera, canvas);
  controls.enablePan = false; controls.enableDamping = true; controls.dampingFactor = 0.08;
  controls.minDistance = 2.0; controls.maxDistance = 5.5; controls.rotateSpeed = 0.5; controls.zoomSpeed = 0.6;
  controls.autoRotate = true; controls.autoRotateSpeed = 0.35;
  controls.enableZoom = matchMedia('(pointer: fine)').matches;

  const world = new THREE.Group();
  scene.add(world);
  // 球体（裏側を隠す）
  const sphere = new THREE.Mesh(new THREE.SphereGeometry(0.995, 64, 48), new THREE.MeshBasicMaterial({ color: 0x0b1118 }));
  world.add(sphere);
  // 大気
  const atmo = new THREE.Mesh(new THREE.SphereGeometry(1.03, 64, 48), new THREE.ShaderMaterial({ uniforms: { uColor: { value: new THREE.Color('#2f6fa5') } }, vertexShader: atmoVert, fragmentShader: atmoFrag, transparent: true, side: THREE.FrontSide, depthWrite: false, blending: THREE.AdditiveBlending }));
  world.add(atmo);
  // 経線緯線（薄く）
  const grid = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.SphereGeometry(1.0, 24, 12)), new THREE.LineBasicMaterial({ color: 0x1f2d3a, transparent: true, opacity: 0.35 }));
  world.add(grid);

  const land = createLand('#5a85a8', pr); world.add(land);
  const hubs = createHubs(HUBS); world.add(hubs.group);
  const arcs = createArcs(HUBS, pr); world.add(arcs.lines); world.add(arcs.particles);
  const evap = createEvap(HUBS, pr); world.add(evap.points);
  const you = createYou(pr); world.add(you.points);

  let tokensI = 0.5, waterI = 0.5, reduced = false;
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();

  function resize() {
    const w = canvas.clientWidth || 1, h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // 右パネル・上のティッカー・左下のカードを避けて、空いている領域の中心に球を置く。
    // 視野を (w+P)×(h+|T-B|) に広げ、その一部を描くと中心がずれる（回転の中心は球のまま）
    const { right, top, bottom } = layout();
    const P = Math.max(0, Math.min(right, w * 0.6));
    const T = Math.max(0, Math.min(top, h * 0.6)), B = Math.max(0, Math.min(bottom, h * 0.6));
    const dy = T - B;
    camera.aspect = (w + P) / (h + Math.abs(dy)); // 投影は広げた全体に対して決まる（球が潰れないように）
    camera.setViewOffset(w + P, h + Math.abs(dy), P, dy < 0 ? -dy : 0, w, h);
    const free = Math.min(w - P, h - T - B);
    // 球の見かけの直径が空き領域の約 90% になる距離（fov 38°: 半径 px ≈ 1.45 h / d）
    camera.position.setLength(Math.max(2.6, Math.min(8, 3.1 * h / Math.max(free, 1))));
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener('resize', resize);

  return {
    render(t) {
      if (!reduced) { controls.update(); hubs.update(t, tokensI); arcs.update(t, tokensI); evap.update(t, waterI); you.update(t); }
      renderer.render(scene, camera);
    },
    setIntensity(tk, wt) { tokensI = Math.max(0, Math.min(1, tk)); waterI = Math.max(0, Math.min(1, wt)); },
    setHover(id) { hubs.setHover(id); },
    setReduced(v) {
      reduced = v; controls.autoRotate = !v;
      arcs.particles.visible = !v; evap.points.visible = !v; you.points.visible = !v;
      if (v) { arcs.update(0, 0.4); hubs.update(0, 0.5); renderer.render(scene, camera); }
    },
    readCenter() {
      // 検査用: 1 フレーム描いた直後に中央 64×64 を読み、背景でない画素を数える
      renderer.render(scene, camera);
      const gl = renderer.getContext();
      const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
      const px = new Uint8Array(4 * 64 * 64);
      gl.readPixels(Math.floor(w / 2 - 32), Math.floor(h / 2 - 32), 64, 64, gl.RGBA, gl.UNSIGNED_BYTE, px);
      let n = 0; for (let i = 0; i < px.length; i += 4) if ((px[i]! + px[i + 1]! + px[i + 2]!) > 40) n++;
      return n;
    },
    faceHub(hubId) {
      // カメラを拠点の真上（少し赤道寄り）に置く。回転の中心は球の中心のまま
      const h = HUBS.find((x) => x.id === hubId); if (!h) return;
      const d = camera.position.length();
      camera.position.copy(latLonToVec3(h.lat * 0.8, h.lon, 1).normalize().multiplyScalar(d));
      controls.update();
    },
    setYou(hubId, rate) {
      const h = HUBS.find((x) => x.id === hubId);
      if (h) you.setHub(h.lat, h.lon);
      you.setRate(rate);
    },
    resize,
    pickHub(cx, cy) {
      const r = canvas.getBoundingClientRect();
      ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(hubs.sprites, false);
      for (const h of hits) {
        const id = (h.object.userData as { id: string }).id;
        // 球の裏側は無視
        const p = h.object.getWorldPosition(new THREE.Vector3());
        if (p.normalize().dot(camera.position.clone().normalize()) < 0.05) continue;
        return HUBS.find((x) => x.id === id) ?? null;
      }
      return null;
    },
    hubScreen(id) {
      const i = HUBS.findIndex((h) => h.id === id); if (i < 0) return null;
      const sp = hubs.sprites[i]!;
      const p = sp.getWorldPosition(new THREE.Vector3());
      const visible = p.clone().normalize().dot(camera.position.clone().normalize()) > 0.05;
      p.project(camera);
      const r = canvas.getBoundingClientRect();
      return { x: r.left + ((p.x + 1) / 2) * r.width, y: r.top + ((1 - p.y) / 2) * r.height, visible };
    },
    dispose() { controls.dispose(); renderer.dispose(); window.removeEventListener('resize', resize); },
  };
}
