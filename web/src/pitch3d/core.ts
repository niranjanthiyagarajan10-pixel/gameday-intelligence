import * as THREE from "three";

/**
 * Shared units and helpers for the 3D pitch. Pitch metres map to world units: x 0..105 runs along
 * world X, y 0..68 along world Z, and up is Y. The centre spot is the world origin.
 */

export const L = 105;
export const W = 68;
export const FIG_SCALE = 2.25; // figures larger than life so they read as people at broadcast distance
export const BALL_R = 0.34;
export const GROUND = 0.02;
export const HEAD_Y = 1.67 * FIG_SCALE;

export const wx = (x: number) => x - L / 2;
export const wz = (y: number) => y - W / 2;
export const px = (x: number) => x + L / 2; // world X back to pitch metres
export const pz = (z: number) => z + W / 2;

export const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function cssColor(name: string, fallback: string) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch {
    return fallback;
  }
}

/** Deterministic random numbers for decoration, so the stadium looks the same on every load. */
export function seeded(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Stable small hash so each synthetic player keeps the same look in every session. */
export function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

/** Flat shapes on the grass share one style: unlit, no depth write, drawn over the turf. */
export function flatMat(color: THREE.ColorRepresentation, opacity = 1) {
  return new THREE.MeshBasicMaterial({
    color,
    transparent: opacity < 1,
    opacity,
    depthWrite: false,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    side: THREE.DoubleSide,
  });
}

export function strip(x1: number, z1: number, x2: number, z2: number, w: number, mat: THREE.Material, y = GROUND) {
  const len = Math.hypot(x2 - x1, z2 - z1);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(len, w), mat);
  m.rotation.x = -Math.PI / 2;
  m.rotation.z = -Math.atan2(z2 - z1, x2 - x1);
  m.position.set((x1 + x2) / 2, y, (z1 + z2) / 2);
  return m;
}

export function arc(cx: number, cz: number, r: number, w: number, start: number, len: number, mat: THREE.Material, y = GROUND) {
  const m = new THREE.Mesh(new THREE.RingGeometry(r - w / 2, r + w / 2, 96, 1, start, len), mat);
  m.rotation.x = -Math.PI / 2;
  m.position.set(cx, y, cz);
  return m;
}

export function disc(cx: number, cz: number, r: number, mat: THREE.Material, y = GROUND) {
  const m = new THREE.Mesh(new THREE.CircleGeometry(r, 48), mat);
  m.rotation.x = -Math.PI / 2;
  m.position.set(cx, y, cz);
  return m;
}

/** Frees every geometry, material and texture under an object. Shared ones may be freed twice; three allows that. */
export function disposeTree(o: THREE.Object3D) {
  o.traverse((c) => {
    const m = c as THREE.Mesh;
    m.geometry?.dispose();
    const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
    for (const mat of mats) {
      (mat as THREE.MeshBasicMaterial).map?.dispose();
      mat.dispose();
    }
  });
}

/** A canvas texture in sRGB, or null when 2D canvas is unavailable. */
export function canvasTexture(w: number, h: number, draw: (g: CanvasRenderingContext2D) => void) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const g = c.getContext("2d");
  if (g) draw(g);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
