import * as THREE from 'three';
import type { Hub } from '../data/hubs';
import { latLonToVec3 } from './util';

function glowTexture(): THREE.Texture {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d')!;
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, 'rgba(255,255,255,1)'); grad.addColorStop(0.18, 'rgba(160,215,255,0.9)');
  grad.addColorStop(0.45, 'rgba(79,155,214,0.35)'); grad.addColorStop(1, 'rgba(79,155,214,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

export interface HubSprites { group: THREE.Group; sprites: THREE.Sprite[]; positions: THREE.Vector3[]; update(t: number, intensity: number): void; setHover(id: string | null): void }

export function createHubs(hubs: Hub[]): HubSprites {
  const tex = glowTexture();
  const group = new THREE.Group();
  const sprites: THREE.Sprite[] = [], positions: THREE.Vector3[] = [];
  const total = hubs.reduce((s, h) => s + h.share, 0);
  hubs.forEach((h, i) => {
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.95 });
    const sp = new THREE.Sprite(mat);
    const p = latLonToVec3(h.lat, h.lon, 1.01);
    sp.position.copy(p);
    const base = 0.07 + Math.sqrt(h.share / total) * 0.32;
    sp.userData = { id: h.id, base, phase: i * 1.7, hover: false };
    sp.scale.setScalar(base);
    group.add(sp); sprites.push(sp); positions.push(p);
  });
  let hoverId: string | null = null;
  return {
    group, sprites, positions,
    update(t, intensity) {
      for (const sp of sprites) {
        const u = sp.userData as { base: number; phase: number; id: string };
        const pulse = 1 + 0.12 * Math.sin(t * 2.4 + u.phase) * intensity;
        const hv = hoverId === u.id ? 1.35 : 1;
        sp.scale.setScalar(u.base * pulse * hv * (0.85 + 0.3 * intensity));
      }
    },
    setHover(id) { hoverId = id; },
  };
}
