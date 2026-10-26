import * as THREE from "three";
import { BALL_R } from "./core";

/**
 * Equirectangular texture for a classic black and white football: 12 black pentagons and 20 white
 * hexagons with dark seams. Each texel takes the nearest panel centre; pentagon distances are scaled
 * up a little because pentagons are smaller panels than hexagons.
 */
export function footballTexture() {
  const phi = (1 + Math.sqrt(5)) / 2;
  const ico = [
    [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
    [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
    [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
  ].map((v) => new THREE.Vector3(...v).normalize());
  const faces: THREE.Vector3[] = [];
  for (let i = 0; i < 12; i++)
    for (let j = i + 1; j < 12; j++)
      for (let k = j + 1; k < 12; k++) {
        const close = (a: number, b: number) => ico[a].dot(ico[b]) > 0.4;
        if (close(i, j) && close(j, k) && close(i, k)) faces.push(ico[i].clone().add(ico[j]).add(ico[k]).normalize());
      }
  const W = 512;
  const H = 256;
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const g = c.getContext("2d");
  if (g) {
    const img = g.createImageData(W, H);
    const d = new THREE.Vector3();
    for (let y = 0; y < H; y++) {
      const th = ((y + 0.5) / H) * Math.PI;
      for (let x = 0; x < W; x++) {
        const ph = ((x + 0.5) / W) * Math.PI * 2;
        d.set(-Math.cos(ph) * Math.sin(th), Math.cos(th), Math.sin(ph) * Math.sin(th));
        let best = Infinity;
        let second = Infinity;
        let pent = false;
        for (let i = 0; i < 32; i++) {
          const p = i < 12;
          const a = Math.acos(Math.min(1, d.dot(p ? ico[i] : faces[i - 12]))) * (p ? 1.2 : 1);
          if (a < best) {
            second = best;
            best = a;
            pent = p;
          } else if (a < second) second = a;
        }
        const v = second - best < 0.025 ? 70 : pent ? 22 : 238;
        const o = (y * W + x) * 4;
        img.data[o] = img.data[o + 1] = img.data[o + 2] = v;
        img.data[o + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

const TRAIL_N = 12;
const TRAIL_MS = 220;

/** A short comet trail behind the ball: shrinking beads along its last fraction of a second. */
export class BallTrail {
  readonly mesh: THREE.InstancedMesh;
  private pts: { p: THREE.Vector3; t: number }[] = [];
  private m = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private s = new THREE.Vector3();
  private v = new THREE.Vector3();

  constructor() {
    this.mesh = new THREE.InstancedMesh(
      new THREE.SphereGeometry(BALL_R * 0.8, 8, 6),
      new THREE.MeshBasicMaterial({ color: 0xf4f4f1, transparent: true, opacity: 0.28, depthWrite: false }),
      TRAIL_N,
    );
    this.mesh.frustumCulled = false;
    this.mesh.count = 0;
  }

  update(ball: THREE.Vector3, now: number) {
    const last = this.pts[this.pts.length - 1];
    if (!last || last.p.distanceToSquared(ball) > 0.04) this.pts.push({ p: ball.clone(), t: now });
    this.pts = this.pts.filter((p) => now - p.t < TRAIL_MS);
    // Beads spread evenly along the recent path, biggest next to the ball.
    const n = this.pts.length;
    let k = 0;
    if (n >= 2) {
      for (let i = 0; i < TRAIL_N; i++) {
        const u = i / TRAIL_N;
        const f = (n - 1) * (1 - u);
        const a = this.pts[Math.floor(f)].p;
        const b = this.pts[Math.min(n - 1, Math.floor(f) + 1)].p;
        this.v.lerpVectors(a, b, f - Math.floor(f));
        if (this.v.distanceToSquared(ball) < (BALL_R * 1.4) ** 2) continue;
        this.s.setScalar(1 - u * 0.85);
        this.m.compose(this.v, this.q, this.s);
        this.mesh.setMatrixAt(k++, this.m);
      }
    }
    this.mesh.count = k;
    this.mesh.instanceMatrix.needsUpdate = true;
  }

  reset() {
    this.pts = [];
    this.mesh.count = 0;
  }
}

interface Flight {
  pts: THREE.Vector3[];
  mesh: THREE.Mesh | null;
  mat: THREE.MeshBasicMaterial;
  shot: boolean;
  until: number; // shots record for a fixed time even along the ground
  landed: number; // when it finished, or 0 while still in the air
  built: number;
}

const FADE_MS = 1800;
const MIN_LONG_M = 18; // shorter airborne balls (headers, chips) leave no path

/**
 * Paths of the ball through the air, drawn as thin tubes at their real height: long balls in white,
 * shots in the shooting team's colour. They fade out after the ball comes down.
 */
export class FlightPaths {
  readonly group = new THREE.Group();
  private live: Flight | null = null;
  private done: Flight[] = [];
  private lastGround = new THREE.Vector3();

  /** A shot was struck: follow the ball for the next moments whatever its height. */
  shot(color: string, from: THREE.Vector3, now: number) {
    this.finish(now);
    this.live = this.make(true, color, from, now + 1600);
  }

  private make(shot: boolean, color: string, from: THREE.Vector3, until: number): Flight {
    const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: shot ? 0.85 : 0.5, depthWrite: false });
    return { pts: [from.clone()], mesh: null, mat, shot, until, landed: 0, built: 0 };
  }

  private finish(now: number) {
    const f = this.live;
    if (!f) return;
    this.live = null;
    const a = f.pts[0];
    const b = f.pts[f.pts.length - 1];
    if (!f.shot && Math.hypot(b.x - a.x, b.z - a.z) < MIN_LONG_M) {
      this.drop(f);
      return;
    }
    this.rebuild(f);
    f.landed = now;
    this.done.push(f);
  }

  private drop(f: Flight) {
    if (f.mesh) {
      this.group.remove(f.mesh);
      f.mesh.geometry.dispose();
    }
    f.mat.dispose();
  }

  private rebuild(f: Flight) {
    if (f.pts.length < 2) return;
    const curve = new THREE.CatmullRomCurve3(f.pts);
    const geo = new THREE.TubeGeometry(curve, Math.min(160, f.pts.length * 3), f.shot ? 0.11 : 0.08, 5, false);
    if (f.mesh) {
      f.mesh.geometry.dispose();
      f.mesh.geometry = geo;
    } else {
      f.mesh = new THREE.Mesh(geo, f.mat);
      this.group.add(f.mesh);
    }
  }

  update(ball: THREE.Vector3, height: number, now: number) {
    const f = this.live;
    if (!f) {
      if (height > 1.2) this.live = this.make(false, "#f4f4f1", this.lastGround, Infinity);
    } else {
      if (f.pts[f.pts.length - 1].distanceToSquared(ball) > 0.25) f.pts.push(ball.clone());
      if (now - f.built > 80) {
        this.rebuild(f);
        f.built = now;
      }
      const over = f.shot ? now > f.until : height < 0.3;
      if (over || f.pts.length > 400) this.finish(now);
    }
    if (height < 0.3) this.lastGround.copy(ball);
    for (const d of this.done) d.mat.opacity = (d.shot ? 0.85 : 0.5) * Math.max(0, 1 - (now - d.landed) / FADE_MS);
    const keep: Flight[] = [];
    for (const d of this.done) {
      if (now - d.landed > FADE_MS) this.drop(d);
      else keep.push(d);
    }
    this.done = keep;
  }

  clear() {
    if (this.live) this.drop(this.live);
    this.live = null;
    for (const d of this.done) this.drop(d);
    this.done = [];
  }
}
