import * as THREE from 'three';

/** 緯度経度 → 単位球上の座標（経度は東向きに増える） */
export function latLonToVec3(lat: number, lon: number, r = 1): THREE.Vector3 {
  const phi = (lat * Math.PI) / 180, lam = (lon * Math.PI) / 180;
  return new THREE.Vector3(r * Math.cos(phi) * Math.cos(lam), r * Math.sin(phi), -r * Math.cos(phi) * Math.sin(lam));
}

/** 決定論的な疑似乱数（mulberry32） */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 2 点を結ぶ大圏の弧。中点を distance に応じて持ち上げる（2 次ベジェの制御点） */
export function arcControl(a: THREE.Vector3, b: THREE.Vector3): THREE.Vector3 {
  const mid = a.clone().add(b).multiplyScalar(0.5);
  const d = a.distanceTo(b);
  const lift = 1 + 0.12 + d * 0.35;
  return mid.normalize().multiplyScalar(lift);
}
