import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { outerProfile, innerProfile, innerRadiusAt, levelY, NECK_TOP, BOTTLE_H, BOTTLE_R } from './profile';
import { VESSELS, chooseVessel, BOTTLE_LITERS, type Vessel } from '../data/model';

/* ボトル画面の 3D 舞台。単位は m（実寸）。
 * 「いま」: 手前に 500 mL ボトル 1 本。注がれた水が満ちると棚（後ろの壁）へ移り、新しいボトルが出る。
 * 「7 日」: 棚が 7 つの塊（1 日 1 塊）になり、カメラが引く。
 * 「1 年換算」「世界の 1 日」: 量に合う器（浴槽・プール・東京ドーム）を実寸で並べ、カメラが大きく引く。 */

export type BottleMode = 'now' | 'week' | 'ladder';
export interface WeekDay { day: string; liters: number }
export interface LadderInfo { vessel: Vessel; count: number; shown: number; hidden: number }

export interface BottleScene {
  render(t: number, dt: number): void;
  resize(): void;
  /** 今日の累計 L（実ログ）。増えた分は注ぐ演出で追いつく */
  setToday(liters: number, opts?: { instant?: boolean }): void;
  /** 1 回で注ぐ（静的配信の「送信した」） */
  pour(liters: number): void;
  setWeek(days: WeekDay[]): void;
  setMode(mode: BottleMode, ladderLiters?: number): LadderInfo | null;
  setReduced(v: boolean): void;
  /** 検査用 */
  displayLiters(): number;
  cameraDone(): boolean;
  readCenter(): number;
  blockScreen(i: number): { x: number; y: number; visible: boolean } | null;
  dispose(): void;
}

const SHELF_COLS = 40, SHELF_MAX = 300, WEEK_COLS = 10, DX = 0.072, DY = 0.235, SHELF_Z = -2.6;

const surfaceVert = /* glsl */ `
  uniform float uTime; uniform float uR; uniform vec3 uRip[8]; uniform float uAmp;
  varying float vH; varying vec2 vXY;
  void main() {
    vec3 p = position;
    vec2 xy = p.xy * uR;
    float h = uAmp * (sin(xy.x * 260.0 + uTime * 2.3) * 0.5 + sin(xy.y * 310.0 - uTime * 1.7) * 0.5);
    for (int i = 0; i < 8; i++) {
      float age = uTime - uRip[i].z;
      if (age < 0.0 || age > 2.5) continue;
      float d = distance(xy, uRip[i].xy);
      float front = age * 0.09;
      h += 0.0016 * exp(-age * 2.2) * sin((d - front) * 420.0) * smoothstep(front + 0.01, front - 0.002, d);
    }
    vH = h; vXY = xy;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(xy, h, 1.0);
  }`;
const surfaceFrag = /* glsl */ `
  uniform vec3 uDeep; uniform vec3 uLight; uniform float uR;
  varying float vH; varying vec2 vXY;
  void main() {
    float rim = smoothstep(uR * 0.55, uR, length(vXY));
    vec3 c = mix(uDeep, uLight, clamp(0.45 + vH * 260.0, 0.0, 1.0));
    c += vec3(0.35) * pow(clamp(0.5 + vH * 300.0, 0.0, 1.0), 6.0);
    gl_FragColor = vec4(c + rim * 0.12, 0.93);
  }`;

export interface StageLayout { left?: number; right: number; top: number; bottom: number }
export function createBottleScene(canvas: HTMLCanvasElement, layout: () => StageLayout): BottleScene {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, logarithmicDepthBuffer: true, powerPreference: 'high-performance' });
  const pr = Math.min(window.devicePixelRatio || 1, 1.5);
  renderer.setPixelRatio(pr);
  renderer.setClearColor(0x000000, 0);
  renderer.localClippingEnabled = true;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

  const camera = new THREE.PerspectiveCamera(32, 1, 0.005, 6000);
  camera.position.set(0.12, 0.17, 0.62);
  const controls = new OrbitControls(camera, canvas);
  controls.enablePan = false; controls.enableDamping = true; controls.dampingFactor = 0.08; controls.rotateSpeed = 0.5;
  controls.enableZoom = false;
  controls.minPolarAngle = 0.35; controls.maxPolarAngle = 1.62;
  controls.target.set(0, BOTTLE_H * 0.5, 0);

  const key = new THREE.DirectionalLight(0xffffff, 1.4); key.position.set(0.6, 1.2, 0.8); scene.add(key);
  const rimL = new THREE.DirectionalLight(0x8cc3ea, 0.8); rimL.position.set(-0.8, 0.4, -0.6); scene.add(rimL);

  // 床（中心だけ薄く明るい）
  const floorTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 256;
    const g = c.getContext('2d')!; const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    gr.addColorStop(0, 'rgba(79,155,214,0.22)'); gr.addColorStop(0.5, 'rgba(79,155,214,0.06)'); gr.addColorStop(1, 'rgba(79,155,214,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: floorTex, transparent: true, depthWrite: false }));
  floor.rotation.x = -Math.PI / 2; floor.scale.setScalar(1.2); scene.add(floor);

  // ---------------------------------------------------------------- 手前のボトル
  const outerGeo = new THREE.LatheGeometry(outerProfile(), 72);
  const innerGeo = new THREE.LatheGeometry(innerProfile(), 72);
  // 屈折（transmission）は使わない: 内蔵 GPU で重く、半透明の水を透かせない。薄い反射ガラスで見せる
  const glass = new THREE.MeshPhysicalMaterial({ color: 0xdfefff, metalness: 0, roughness: 0.03, clearcoat: 1, clearcoatRoughness: 0.03, envMapIntensity: 1.8, specularIntensity: 1, transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide });
  const clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
  const waterMat = new THREE.MeshPhysicalMaterial({ color: 0x2a7fc4, roughness: 0.08, metalness: 0, clearcoat: 0.6, transparent: true, opacity: 0.94, clippingPlanes: [clip], envMapIntensity: 1.0, side: THREE.DoubleSide, emissive: 0x0b2c48, emissiveIntensity: 0.6 });
  const capMat = new THREE.MeshStandardMaterial({ color: 0xece6da, roughness: 0.45, metalness: 0 });

  const bottle = new THREE.Group();
  const glassMesh = new THREE.Mesh(outerGeo, glass); glassMesh.renderOrder = 2;
  const waterMesh = new THREE.Mesh(innerGeo, waterMat); waterMesh.renderOrder = 1;
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.0155, 0.0155, 0.014, 40), capMat);
  cap.position.y = NECK_TOP + 0.006;
  const surface = new THREE.Mesh(new THREE.CircleGeometry(1, 72), new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uR: { value: 0.02 }, uRip: { value: Array.from({ length: 8 }, () => new THREE.Vector3(0, 0, -99)) }, uAmp: { value: 0.0003 }, uDeep: { value: new THREE.Color('#1d5f97') }, uLight: { value: new THREE.Color('#9fd2f5') } },
    vertexShader: surfaceVert, fragmentShader: surfaceFrag, transparent: true, depthWrite: false, side: THREE.DoubleSide,
  }));
  surface.rotation.x = -Math.PI / 2;
  // ガラスの縁: 視線に対して寝ている面だけ白く光らせる（フレネル）
  const rimMat = new THREE.ShaderMaterial({
    vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }',
    fragmentShader: 'varying vec3 vN; varying vec3 vV; void main(){ float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.6); gl_FragColor = vec4(vec3(0.85,0.93,1.0), f * 0.75); }',
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  });
  const rimMesh = new THREE.Mesh(outerGeo, rimMat); rimMesh.renderOrder = 3;
  bottle.add(waterMesh, surface, glassMesh, rimMesh, cap);
  scene.add(bottle);

  // 満ちたボトルが棚へ飛ぶときの身代わり
  const filledMat = new THREE.MeshPhysicalMaterial({ color: 0x3a8fd0, roughness: 0.18, metalness: 0, clearcoat: 0.8, envMapIntensity: 1.0, transparent: true, opacity: 0.95 });
  const shelfDimMat = new THREE.MeshPhysicalMaterial({ color: 0x1f5f90, roughness: 0.3, metalness: 0, envMapIntensity: 0.5, transparent: true, opacity: 0.55, depthWrite: false });
  const flyer = new THREE.Mesh(outerGeo, filledMat); flyer.visible = false; scene.add(flyer);

  // ---------------------------------------------------------------- 注ぐ水（粒）
  const DROP_N = 90;
  const dropGeo = new THREE.SphereGeometry(0.0028, 12, 10);
  const dropMat = new THREE.MeshPhysicalMaterial({ color: 0x9fd2f5, roughness: 0.05, metalness: 0, clearcoat: 1, envMapIntensity: 1.4 });
  const drops = new THREE.InstancedMesh(dropGeo, dropMat, DROP_N);
  drops.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  drops.frustumCulled = false;
  scene.add(drops);
  const dropState = Array.from({ length: DROP_N }, () => ({ on: false, y: 0, v: 0, x: 0, z: 0 }));
  const m4 = new THREE.Matrix4(), hidden = new THREE.Matrix4().makeScale(0, 0, 0);
  for (let i = 0; i < DROP_N; i++) drops.setMatrixAt(i, hidden);
  let ripI = 0;
  const rip = (surface.material as THREE.ShaderMaterial).uniforms.uRip!.value as THREE.Vector3[];

  // ---------------------------------------------------------------- 棚（今日 / 7 日）
  const shelfCap = SHELF_MAX * 7;
  const shelf = new THREE.InstancedMesh(outerGeo, filledMat, shelfCap);
  shelf.count = 0; shelf.frustumCulled = false;
  scene.add(shelf);
  let weekDays: WeekDay[] = [];
  const blockCenters: THREE.Vector3[] = [];

  function layoutShelf(todayFull: number) {
    blockCenters.length = 0;
    let n = 0;
    if (mode === 'now') {
      const cnt = Math.min(todayFull, SHELF_MAX);
      const width = SHELF_COLS * DX;
      for (let i = 0; i < cnt; i++) {
        const c = i % SHELF_COLS, r = Math.floor(i / SHELF_COLS);
        m4.makeTranslation(-width / 2 + c * DX + DX / 2, r * DY, SHELF_Z);
        shelf.setMatrixAt(n++, m4);
      }
      blockCenters.push(new THREE.Vector3(0, Math.ceil(cnt / SHELF_COLS) * DY + 0.05, SHELF_Z));
    } else if (mode === 'week') {
      const blockW = WEEK_COLS * DX, gap = 0.35;
      const total = weekDays.length * blockW + (weekDays.length - 1) * gap;
      weekDays.forEach((d, bi) => {
        const cnt = Math.min(Math.floor(d.liters / BOTTLE_LITERS), SHELF_MAX);
        const x0 = -total / 2 + bi * (blockW + gap);
        for (let i = 0; i < cnt; i++) {
          const c = i % WEEK_COLS, r = Math.floor(i / WEEK_COLS);
          m4.makeTranslation(x0 + c * DX + DX / 2, r * DY, 0);
          shelf.setMatrixAt(n++, m4);
        }
        blockCenters.push(new THREE.Vector3(x0 + blockW / 2, Math.max(1, Math.ceil(cnt / WEEK_COLS)) * DY + 0.08, 0));
      });
    }
    shelf.count = n;
    shelf.instanceMatrix.needsUpdate = true;
  }

  // ---------------------------------------------------------------- 器の梯子
  const ladder = new THREE.Group(); scene.add(ladder);
  const edgeMat = new THREE.LineBasicMaterial({ color: 0xc8d3dc, transparent: true, opacity: 0.55 });
  const shellMat = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.1, transmission: 0.6, thickness: 0.02, transparent: true, opacity: 0.25, side: THREE.DoubleSide, depthWrite: false });
  const ladWater = new THREE.MeshPhysicalMaterial({ color: 0x2f86c9, roughness: 0.2, metalness: 0, transparent: true, opacity: 0.88, envMapIntensity: 0.8 });

  function vesselGeometry(v: Vessel): { shell: THREE.BufferGeometry; water: THREE.BufferGeometry; depth: number } {
    if (v.id === 'dome') {
      const g = new THREE.SphereGeometry(1, 64, 24, 0, Math.PI * 2, 0, Math.PI / 2);
      g.scale(v.w / 2, v.h, v.w / 2);
      return { shell: g, water: g.clone().scale(0.985, 0.985, 0.985), depth: v.w };
    }
    const depth = v.id === 'pool' ? 13 : v.id === 'bath' ? 0.8 : v.w;
    const g = new THREE.BoxGeometry(v.w, v.h, depth); g.translate(0, v.h / 2, 0);
    const wg = new THREE.BoxGeometry(v.w * 0.97, v.h * 0.97, depth * 0.97); wg.translate(0, (v.h * 0.97) / 2, 0);
    return { shell: g, water: wg, depth };
  }

  function buildLadder(liters: number): LadderInfo {
    ladder.clear();
    const choice = chooseVessel(liters);
    const v = choice.vessel;
    ladderVessel = v.id;
    const shown = Math.max(1, Math.min(Math.ceil(choice.count), v.maxCopies));
    const { shell, water, depth } = vesselGeometry(v);
    const cols = Math.max(1, Math.round(Math.sqrt(shown * 1.6)));
    const gapX = v.w * 0.18, gapZ = depth * 0.25;
    const rows = Math.ceil(shown / cols);
    const totalW = cols * v.w + (cols - 1) * gapX, totalD = rows * depth + (rows - 1) * gapZ;
    for (let i = 0; i < shown; i++) {
      const c = i % cols, r = Math.floor(i / cols);
      const x = -totalW / 2 + c * (v.w + gapX) + v.w / 2, z = -r * (depth + gapZ);
      const fill = i < choice.full ? 1 : i === choice.full ? choice.partial : 0;
      const sh = new THREE.Mesh(shell, shellMat); sh.position.set(x, 0, z); ladder.add(sh);
      const ed = new THREE.LineSegments(new THREE.EdgesGeometry(shell, 30), edgeMat); ed.position.copy(sh.position); ladder.add(ed);
      if (fill > 0.0005) {
        const mat = fill < 1 ? ladWater.clone() : ladWater;
        if (fill < 1) mat.clippingPlanes = [new THREE.Plane(new THREE.Vector3(0, -1, 0), v.h * fill)];
        const w = new THREE.Mesh(water, mat); w.position.set(x, 0, z); ladder.add(w);
      }
    }
    // 同じ縮尺の比較: ひとつ前の器と、手前のボトル
    const idx = VESSELS.indexOf(v);
    if (idx > 0) {
      const pv = VESSELS[idx - 1]!; const pg = vesselGeometry(pv);
      const ref = new THREE.Mesh(pg.water, ladWater); ref.position.set(-totalW / 2 - pv.w * 1.2 - v.w * 0.15, 0, depth * 0.3); ladder.add(ref);
      const re = new THREE.LineSegments(new THREE.EdgesGeometry(pg.shell, 30), edgeMat); re.position.copy(ref.position); ladder.add(re);
    }
    frameBox.set(new THREE.Vector3(-totalW / 2 - (idx > 0 ? VESSELS[idx - 1]!.w * 1.6 : 0), 0, -totalD + depth / 2), new THREE.Vector3(totalW / 2, v.h, depth / 2));
    return { vessel: v, count: choice.count, shown, hidden: Math.max(0, Math.ceil(choice.count) - shown) };
  }

  // ---------------------------------------------------------------- カメラ
  let mode: BottleMode = 'now';
  const frameBox = new THREE.Box3();
  const camFrom = { dist: 0.62, target: new THREE.Vector3(0, BOTTLE_H * 0.5, 0) };
  const camTo = { dist: 0.62, target: new THREE.Vector3(0, BOTTLE_H * 0.5, 0) };
  let camT = 1;

  function frameFor(): { dist: number; target: THREE.Vector3 } {
    const tan = Math.tan((camera.fov * Math.PI) / 360);
    // 箱（幅 bw × 高さ bh）が空き領域（全体の freeX × freeY）に収まる距離
    const fit = (bw: number, bh: number) => Math.max(bh / (2 * tan * freeY), bw / (2 * tan * camera.aspect * freeX)) * 1.12;
    if (mode === 'now') return { dist: fit(BOTTLE_H * 0.62, BOTTLE_H * 1.25), target: new THREE.Vector3(0, BOTTLE_H * 0.52, 0) };
    // 器の段・7 日は、箱を包む球が空き領域に収まる距離（見下ろす角度でも切れない）
    const center = frameBox.getCenter(new THREE.Vector3());
    const r = frameBox.getSize(new THREE.Vector3()).length() / 2;
    return { dist: Math.max(0.6, (r / (tan * Math.min(freeY, freeX * camera.aspect))) * 1.02), target: center };
  }
  const VIEW_DIR: Record<BottleMode, THREE.Vector3> = {
    now: new THREE.Vector3(0.2, 0.22, 1).normalize(),
    week: new THREE.Vector3(0.12, 0.28, 1).normalize(),
    ladder: new THREE.Vector3(0.35, 0.8, 1).normalize(),
  };
  const LADDER_DIR: Record<Vessel['id'], THREE.Vector3> = {
    bottle: new THREE.Vector3(0.2, 0.25, 1).normalize(),
    bath: new THREE.Vector3(0.45, 0.55, 1).normalize(),
    pool: new THREE.Vector3(0.35, 0.8, 1).normalize(),
    dome: new THREE.Vector3(0.3, 0.32, 1).normalize(),
  };
  let ladderVessel: Vessel['id'] = 'pool';
  const dirFrom = new THREE.Vector3(), dirTo = new THREE.Vector3();
  function startCamera() {
    dirFrom.copy(camera.position).sub(controls.target).normalize(); dirTo.copy(mode === 'ladder' ? LADDER_DIR[ladderVessel] : VIEW_DIR[mode]);
    camFrom.dist = camera.position.distanceTo(controls.target); camFrom.target.copy(controls.target);
    const f = frameFor(); camTo.dist = f.dist; camTo.target.copy(f.target);
    camT = reduced ? 1 : 0;
    if (reduced) applyCamera(1);
  }
  function applyCamera(p: number) {
    const e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
    const d = Math.exp(Math.log(camFrom.dist) + (Math.log(camTo.dist) - Math.log(camFrom.dist)) * e);
    controls.target.lerpVectors(camFrom.target, camTo.target, e);
    const dir = dirFrom.lengthSq() > 0.5 ? dirFrom.clone().lerp(dirTo, e).normalize() : VIEW_DIR[mode].clone();
    camera.position.copy(controls.target).addScaledVector(dir, d);
    floor.scale.setScalar(Math.max(1.2, d * 3));
  }

  // ---------------------------------------------------------------- 水の量
  let target = 0, shown = 0, reduced = false, lastFull = -1;
  let flyT = 1;
  const flyFrom = new THREE.Vector3(), flyTo = new THREE.Vector3();

  function updateLevel() {
    const frac = (shown % BOTTLE_LITERS) / BOTTLE_LITERS;
    const y = levelY(frac);
    clip.constant = y;
    surface.position.y = y;
    const r = innerRadiusAt(y);
    (surface.material as THREE.ShaderMaterial).uniforms.uR!.value = r;
    surface.visible = frac > 0.002;
    waterMesh.visible = frac > 0.002;
    const full = Math.floor(shown / BOTTLE_LITERS + 1e-9);
    if (full !== lastFull) {
      if (full > lastFull && lastFull >= 0 && mode === 'now' && !reduced) {
        // 満ちた 1 本を棚へ飛ばす
        const i = Math.min(full - 1, SHELF_MAX - 1);
        const c = i % SHELF_COLS, row = Math.floor(i / SHELF_COLS);
        flyFrom.set(0, 0, 0); flyTo.set(-(SHELF_COLS * DX) / 2 + c * DX + DX / 2, row * DY, SHELF_Z);
        flyT = 0; flyer.visible = true;
      }
      lastFull = full;
      layoutShelf(full);
    }
  }

  let lastDrop = 0;
  function spawnDrop(t: number) {
    const d = dropState.find((x) => !x.on); if (!d) return;
    d.on = true; d.y = NECK_TOP + 0.09 + Math.random() * 0.02; d.v = 0.3; d.x = (Math.random() - 0.5) * 0.004; d.z = (Math.random() - 0.5) * 0.004;
    lastDrop = t;
  }

  function resize() {
    const w = canvas.clientWidth || 1, h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // 空き領域（左 L・右 P・上 T・下 B を除いた部分）の中心に舞台を置く。
    // 視野を広げた全体の中心が空き領域の中心に来るよう、その一部を描く
    const lay = layout();
    const P = Math.max(0, Math.min(lay.right, w * 0.6)), L = Math.max(0, Math.min(lay.left ?? 0, w * 0.6));
    const T = Math.max(0, Math.min(lay.top, h * 0.6)), B = Math.max(0, Math.min(lay.bottom, h * 0.6));
    const dx = P - L, dy = T - B;
    const fw = w + Math.abs(dx), fh = h + Math.abs(dy);
    camera.aspect = fw / fh; // 投影は「広げた全体」に対して決まるので、縦横比も全体のもの
    camera.setViewOffset(fw, fh, dx > 0 ? dx : 0, dy < 0 ? -dy : 0, w, h);
    camera.updateProjectionMatrix();
    freeX = Math.max(0.1, (w - P - L) / fw); freeY = Math.max(0.1, (h - T - B) / fh);
    if (camT >= 1 && typeof dirFrom !== 'undefined') { const f = frameFor(); camFrom.dist = camTo.dist = f.dist; camFrom.target.copy(f.target); camTo.target.copy(f.target); dirFrom.copy(camera.position).sub(controls.target).normalize(); dirTo.copy(dirFrom); applyCamera(1); }
  }
  let freeX = 1, freeY = 1;
  resize();
  window.addEventListener('resize', resize);
  updateLevel();
  { const f = frameFor(); camFrom.dist = camTo.dist = f.dist; camFrom.target.copy(f.target); camTo.target.copy(f.target); dirFrom.copy(VIEW_DIR.now); dirTo.copy(VIEW_DIR.now); applyCamera(1); }

  let lastT = -1;
  return {
    render(t, _dt) {
      // 経過時間はフレームではなく実時間で（遅い GPU でも注ぎ終わる秒数を変えない。最大 0.5 秒）
      const dt = lastT < 0 ? 16 : Math.min(500, Math.max(0, (t - lastT) * 1000));
      lastT = t;
      // 注ぐ: 目標に追いつく（1 秒でボトル 1 本、差が大きいときは 3 秒以内に追いつく）
      if (shown < target) {
        if (reduced) shown = target;
        else {
          const rate = Math.max(BOTTLE_LITERS, (target - shown) / 3);
          shown = Math.min(target, shown + rate * (dt / 1000));
          if (t - lastDrop > 0.03 && mode === 'now') spawnDrop(t);
        }
        updateLevel();
      } else if (shown > target) { shown = target; updateLevel(); }
      // 粒
      const ly = surface.position.y;
      for (let i = 0; i < DROP_N; i++) {
        const d = dropState[i]!;
        if (!d.on) { drops.setMatrixAt(i, hidden); continue; }
        d.v += 9.8 * (dt / 1000); d.y -= d.v * (dt / 1000);
        const floorY = surface.visible ? ly : levelY(0);
        if (d.y <= floorY) {
          d.on = false; drops.setMatrixAt(i, hidden);
          rip[ripI % 8]!.set(d.x, -d.z, t); ripI++;
          continue;
        }
        const s = 1 + Math.min(1.5, d.v * 0.6);
        m4.makeScale(1, s, 1).setPosition(d.x, d.y, d.z);
        drops.setMatrixAt(i, m4);
      }
      drops.instanceMatrix.needsUpdate = true;
      // 棚へ飛ぶ 1 本
      if (flyT < 1) {
        flyT = Math.min(1, flyT + dt / 700);
        const e = 1 - Math.pow(1 - flyT, 3);
        flyer.position.lerpVectors(flyFrom, flyTo, e);
        flyer.position.y += Math.sin(e * Math.PI) * 0.12;
        if (flyT >= 1) flyer.visible = false;
      }
      // カメラ
      if (camT < 1) { camT = Math.min(1, camT + dt / 1200); applyCamera(camT); }
      (surface.material as THREE.ShaderMaterial).uniforms.uTime!.value = t;
      (surface.material as THREE.ShaderMaterial).uniforms.uAmp!.value = reduced ? 0 : 0.00025;
      controls.update();
      renderer.render(scene, camera);
    },
    resize,
    setToday(l, opts) {
      target = Math.max(0, l);
      if (opts?.instant || shown === 0 && lastFull <= 0) { shown = target; lastFull = Math.floor(shown / BOTTLE_LITERS + 1e-9); layoutShelf(lastFull); updateLevel(); }
    },
    pour(l) { target += Math.max(0, l); },
    setWeek(days) { weekDays = days.slice(-7); if (mode === 'week') layoutShelf(lastFull); },
    setMode(m, ladderLiters) {
      const prevMode = mode, prevVessel = ladderVessel;
      mode = m;
      let info: LadderInfo | null = null;
      bottle.visible = m !== 'week';
      ladder.visible = m === 'ladder';
      shelf.visible = m !== 'ladder';
      shelf.material = m === 'now' ? shelfDimMat : filledMat;
      if (m === 'ladder') info = buildLadder(ladderLiters ?? 0);
      else if (m === 'week') {
        layoutShelf(lastFull);
        const blockW = WEEK_COLS * DX, gap = 0.35, n = Math.max(1, weekDays.length);
        const total = n * blockW + (n - 1) * gap;
        const maxRows = Math.max(1, ...weekDays.map((d) => Math.ceil(Math.min(SHELF_MAX, d.liters / BOTTLE_LITERS) / WEEK_COLS)));
        frameBox.set(new THREE.Vector3(-total / 2, 0, -0.1), new THREE.Vector3(total / 2, maxRows * DY + 0.1, 0.1));
      } else layoutShelf(lastFull);
      // 同じ段・同じ器なら中身だけ更新し、カメラは動かさない（実ログの取り直しのたびに揺れないように）
      if (m !== prevMode || (m === 'ladder' && ladderVessel !== prevVessel)) startCamera();
      else if (camT >= 1) { const f = frameFor(); camTo.dist = f.dist; camTo.target.copy(f.target); camFrom.dist = camera.position.distanceTo(controls.target); camFrom.target.copy(controls.target); dirFrom.copy(camera.position).sub(controls.target).normalize(); dirTo.copy(dirFrom); camT = 0; }
      return info;
    },
    setReduced(v) { reduced = v; controls.autoRotate = false; },
    displayLiters() { return shown; },
    cameraDone() { return camT >= 1; },
    readCenter() {
      renderer.render(scene, camera);
      const gl = renderer.getContext();
      const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
      // ボトルは空き領域の中心に立つので、画面全体を間引いて数える（16 画素に 1 つ）
      const px = new Uint8Array(4 * w * h);
      gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
      let n = 0; for (let i = 0; i < px.length; i += 4 * 16) if ((px[i]! + px[i + 1]! + px[i + 2]!) > 40 || px[i + 3]! > 30) n++;
      return n;
    },
    blockScreen(i) {
      const p = blockCenters[i]; if (!p) return null;
      const v = p.clone().project(camera);
      const r = canvas.getBoundingClientRect();
      return { x: r.left + ((v.x + 1) / 2) * r.width, y: r.top + ((1 - v.y) / 2) * r.height, visible: v.z < 1 };
    },
    dispose() { controls.dispose(); renderer.dispose(); pmrem.dispose(); window.removeEventListener('resize', resize); },
  };
}

export const _BOTTLE_R = BOTTLE_R;
