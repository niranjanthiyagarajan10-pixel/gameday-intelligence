import * as THREE from "three";
import { GROUND, L, W, arc, disc, flatMat, strip, wx, wz } from "./core";

const GOAL_H = 2.44;
const GOAL_HALF = 7.32 / 2;
const NET_DEPTH = 2;
const BULGE_MS = 2200;

/** One goal's net. `bulge` pushes it out where the ball hit, then it settles. */
export class Net {
  readonly lines: THREE.LineSegments;
  private base: Float32Array;
  private hit: { y: number; z: number; start: number } | null = null;

  constructor(lines: THREE.LineSegments) {
    this.lines = lines;
    this.base = Float32Array.from(lines.geometry.getAttribute("position").array as Float32Array);
  }

  /** `z` is across the goal mouth in the goal's own frame, `y` the height, both in metres. */
  bulge(z: number, y: number, now: number) {
    this.hit = { z: Math.max(-GOAL_HALF, Math.min(GOAL_HALF, z)), y: Math.max(0.2, Math.min(GOAL_H, y)), start: now };
  }

  update(now: number) {
    if (!this.hit) return;
    const t = (now - this.hit.start) / 1000;
    const attr = this.lines.geometry.getAttribute("position") as THREE.BufferAttribute;
    const pos = attr.array as Float32Array;
    const done = t * 1000 > BULGE_MS;
    // A push that springs back: strong at first, then a damped wobble.
    const amp = done ? 0 : 1.1 * Math.exp(-t / 0.45) * Math.cos(t * 9);
    for (let i = 0; i < pos.length; i += 3) {
      const bx = this.base[i];
      const by = this.base[i + 1];
      const bz = this.base[i + 2];
      const depth = -bx / NET_DEPTH; // 0 at the goal line, 1 at the back
      const d2 = (bz - this.hit.z) ** 2 + (by - this.hit.y) ** 2;
      const push = amp * depth * Math.exp(-d2 / 3.2);
      pos[i] = bx - push;
      pos[i + 1] = by;
      pos[i + 2] = bz;
    }
    attr.needsUpdate = true;
    if (done) this.hit = null;
  }
}

/** Grass with mowing stripes, the standard markings, and both goals with nets. */
export function buildPitch(): { group: THREE.Group; nets: [Net, Net] } {
  const g = new THREE.Group();
  const apron = new THREE.Mesh(new THREE.PlaneGeometry(L + 34, W + 30), new THREE.MeshLambertMaterial({ color: 0x0a120d }));
  apron.rotation.x = -Math.PI / 2;
  apron.position.y = -0.01;
  apron.receiveShadow = true;
  g.add(apron);
  const grass = new THREE.Mesh(new THREE.PlaneGeometry(L + 6, W + 6), new THREE.MeshLambertMaterial({ color: 0x0e1a12 }));
  grass.rotation.x = -Math.PI / 2;
  grass.receiveShadow = true;
  g.add(grass);
  const stripe = new THREE.MeshLambertMaterial({ color: 0x13241a, polygonOffset: true, polygonOffsetFactor: -1 });
  const sw = L / 18;
  for (let i = 0; i < 18; i += 2) {
    const s = new THREE.Mesh(new THREE.PlaneGeometry(sw, W + 6), stripe);
    s.rotation.x = -Math.PI / 2;
    s.position.set(wx(i * sw + sw / 2), 0.005, 0);
    s.receiveShadow = true;
    g.add(s);
  }

  const line = flatMat(0xdfe3dc, 0.55);
  const lw = 0.12;
  const rect = (x0: number, y0: number, x1: number, y1: number) => {
    g.add(strip(wx(x0), wz(y0), wx(x1), wz(y0), lw, line));
    g.add(strip(wx(x0), wz(y1), wx(x1), wz(y1), lw, line));
    g.add(strip(wx(x0), wz(y0), wx(x0), wz(y1), lw, line));
    g.add(strip(wx(x1), wz(y0), wx(x1), wz(y1), lw, line));
  };
  rect(0, 0, L, W);
  g.add(strip(0, wz(0), 0, wz(W), lw, line));
  g.add(arc(0, 0, 9.15, lw, 0, Math.PI * 2, line));
  const spot = flatMat(0xdfe3dc, 0.7);
  g.add(disc(0, 0, 0.25, spot, GROUND));
  const penAng = Math.acos(5.5 / 9.15);
  const nets: Net[] = [];
  for (const left of [true, false]) {
    const x0 = left ? 0 : L;
    const s = left ? 1 : -1;
    rect(Math.min(x0, x0 + s * 16.5), 13.84, Math.max(x0, x0 + s * 16.5), 54.16);
    rect(Math.min(x0, x0 + s * 5.5), 24.84, Math.max(x0, x0 + s * 5.5), 43.16);
    const sx = wx(left ? 11 : 94);
    g.add(disc(sx, 0, 0.22, spot));
    // RingGeometry angles run counterclockwise from +X in its own plane; laid flat, the arc at
    // angle a sits at (cos a, -sin a) in world X,Z, symmetric about the pitch axis either way.
    g.add(arc(sx, 0, 9.15, lw, left ? -penAng : Math.PI - penAng, 2 * penAng, line));
    const goal = buildGoal(left);
    g.add(goal.group);
    nets.push(goal.net);
  }
  for (const [cx, cz, start] of [
    [0, 0, -Math.PI / 2],
    [L, 0, Math.PI],
    [0, W, 0],
    [L, W, Math.PI / 2],
  ] as const) {
    g.add(arc(wx(cx), wz(cz), 1, lw, start, Math.PI / 2, line));
  }
  return { group: g, nets: [nets[0], nets[1]] };
}

/** Posts, bar and net. The goal's own frame has the net running toward -X; the right goal is turned round. */
function buildGoal(left: boolean): { group: THREE.Group; net: Net } {
  const g = new THREE.Group();
  const h = GOAL_H;
  const half = GOAL_HALF;
  const depth = NET_DEPTH;
  const post = new THREE.MeshLambertMaterial({ color: 0xf4f4f1 });
  const r = 0.07;
  for (const z of [-half, half]) {
    const p = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 10), post);
    p.position.set(0, h / 2, z);
    p.castShadow = true;
    g.add(p);
  }
  const bar = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 7.32 + 2 * r, 10), post);
  bar.rotation.x = Math.PI / 2;
  bar.position.set(0, h, 0);
  bar.castShadow = true;
  g.add(bar);

  // Net as a grid of short segments (back, roof and sides), fine enough to bend when it bulges.
  const pts: number[] = [];
  const seg = (a: number[], b: number[]) => pts.push(...a, ...b);
  const step = 0.35;
  const roofY = (d: number) => h - (0.2 * h * d) / depth;
  for (let z = -half; z < half - 1e-6; z += step) {
    for (let y = 0; y < h * 0.8 - 1e-6; y += step) {
      seg([-depth, y, z], [-depth, y, Math.min(half, z + step)]);
      seg([-depth, y, z], [-depth, Math.min(h * 0.8, y + step), z]);
    }
    for (let d = 0; d < depth - 1e-6; d += step) {
      const d2 = Math.min(depth, d + step);
      seg([-d, roofY(d), z], [-d, roofY(d), Math.min(half, z + step)]);
      seg([-d, roofY(d), z], [-d2, roofY(d2), z]);
    }
  }
  seg([-depth, h * 0.8, -half], [-depth, h * 0.8, half]);
  for (const z of [-half, half]) {
    for (let y = 0; y <= h + 1e-6; y += step) {
      const back = y <= h * 0.8 ? depth : (depth * (h - y)) / (0.2 * h);
      seg([0, y, z], [-back, y, z]);
    }
    for (let d = 0; d <= depth + 1e-6; d += step) seg([-d, 0, z], [-d, roofY(d), z]);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  const lines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.32 }));
  g.add(lines);
  g.position.set(wx(left ? 0 : L), 0, 0);
  if (!left) g.rotation.y = Math.PI;
  return { group: g, net: new Net(lines) };
}
