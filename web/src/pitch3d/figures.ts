import * as THREE from "three";
import { FIG_SCALE, hash } from "./core";

/** A one-off move a player makes on top of running: a tackle lunge or a keeper's dive. */
interface Move {
  kind: "lunge" | "dive";
  start: number;
  dur: number;
  dir: number; // dive side, +1 or -1 in the figure's own frame
  yaw: number; // which way the figure faces during the move
  size: number;
}

export interface Figure {
  id: string;
  keeper: boolean;
  group: THREE.Group; // position and facing
  body: THREE.Group; // everything that leans, rolls or drops during a move
  hit: THREE.Mesh;
  legs: THREE.Group[];
  arms: THREE.Group[];
  phase: number;
  swing: number;
  lean: number;
  move: Move | null;
}

const SKIN = [0xe6bf9c, 0xd0a07a, 0xa87552, 0x7c5238, 0x5a3a26];
const HAIR = [0x16110d, 0x2e2118, 0x4a3324, 0x0b0b0b, 0x6b4a2b];
const ARM_SPLAY = 0.12;

/** Shirt number drawn on a transparent canvas, used as a decal on the back and chest. */
function numberTexture(n: number, color: string, edge: string) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  if (g) {
    g.font = "700 104px 'Barlow Condensed', 'Arial Narrow', sans-serif";
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.lineWidth = 8;
    g.strokeStyle = edge;
    g.strokeText(String(n), 64, 70);
    g.fillStyle = color;
    g.fillText(String(n), 64, 70);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

/**
 * Low-poly player in full kit: shirt with trim collar and cuffs, shorts, socks, boots, and the shirt
 * number on the back and chest. Legs and arms hang from pivots so they swing with running speed.
 * The figure faces local +X. Geometry is shared; materials are cached per colour.
 */
export class FigureKit {
  geo = {
    boot: new THREE.BoxGeometry(0.24, 0.07, 0.1),
    sock: new THREE.CylinderGeometry(0.062, 0.05, 0.42, 8),
    thigh: new THREE.CylinderGeometry(0.085, 0.068, 0.24, 8),
    shorts: new THREE.CylinderGeometry(0.2, 0.225, 0.26, 12),
    torso: new THREE.CylinderGeometry(0.25, 0.2, 0.6, 14),
    collar: new THREE.CylinderGeometry(0.085, 0.1, 0.06, 12),
    neck: new THREE.CylinderGeometry(0.055, 0.06, 0.1, 8),
    sleeve: new THREE.CylinderGeometry(0.08, 0.072, 0.2, 8),
    cuff: new THREE.CylinderGeometry(0.074, 0.074, 0.04, 8),
    arm: new THREE.CylinderGeometry(0.05, 0.042, 0.36, 6),
    head: new THREE.SphereGeometry(0.115, 14, 10),
    hair: new THREE.SphereGeometry(0.122, 14, 6, 0, Math.PI * 2, 0, Math.PI * 0.42),
    backNo: new THREE.PlaneGeometry(0.3, 0.3),
    frontNo: new THREE.PlaneGeometry(0.12, 0.12),
    hit: new THREE.CylinderGeometry(0.5, 0.5, 2.0, 8),
  };
  hitMat = new THREE.MeshBasicMaterial({ visible: false });
  mats = new Map<string, THREE.Material>();

  mat(color: string | number) {
    const key = String(color);
    let m = this.mats.get(key);
    if (!m) {
      m = new THREE.MeshLambertMaterial({ color });
      this.mats.set(key, m);
    }
    return m;
  }

  numberMat(n: number, color: string, edge: string) {
    const key = `no${n}|${color}|${edge}`;
    let m = this.mats.get(key);
    if (!m) {
      m = new THREE.MeshLambertMaterial({ map: numberTexture(n, color, edge), transparent: true, alphaTest: 0.3, depthWrite: false });
      this.mats.set(key, m);
    }
    return m;
  }

  private part(geo: THREE.BufferGeometry, mat: THREE.Material, x: number, y: number, z: number, parent: THREE.Object3D) {
    const m = new THREE.Mesh(geo, mat);
    m.position.set(x, y, z);
    m.castShadow = true;
    parent.add(m);
    return m;
  }

  make(id: string, keeper: boolean, kit: { shirt: string; trim: string; shorts: string; socks: string; number: number }): Figure {
    const group = new THREE.Group();
    const body = new THREE.Group();
    group.add(body);
    const h = hash(id);
    const skin = this.mat(SKIN[h % SKIN.length]);
    const hair = this.mat(HAIR[(h >> 4) % HAIR.length]);
    const shirt = this.mat(kit.shirt);
    const trim = this.mat(kit.trim);
    const g = this.geo;

    const legs = [-0.1, 0.1].map((z) => {
      const hip = new THREE.Group();
      hip.position.set(0, 0.7, z);
      this.part(g.thigh, skin, 0, -0.14, 0, hip);
      this.part(g.sock, this.mat(kit.socks), 0, -0.44, 0, hip);
      this.part(g.boot, this.mat(0x111111), 0.04, -0.665, 0, hip);
      body.add(hip);
      return hip;
    });
    const shorts = this.part(g.shorts, this.mat(kit.shorts), 0, 0.78, 0, body);
    shorts.scale.x = 0.75;
    const torso = this.part(g.torso, shirt, 0, 1.2, 0, body);
    torso.scale.x = 0.68;
    this.part(g.collar, trim, 0, 1.5, 0, body);
    this.part(g.neck, skin, 0, 1.55, 0, body);
    this.part(g.head, skin, 0, 1.67, 0, body);
    this.part(g.hair, hair, -0.01, 1.68, 0, body);
    const arms = [-0.29, 0.29].map((z) => {
      const shoulder = new THREE.Group();
      shoulder.position.set(0, 1.45, z);
      shoulder.rotation.x = z < 0 ? ARM_SPLAY : -ARM_SPLAY;
      this.part(g.sleeve, shirt, 0, -0.08, 0, shoulder);
      this.part(g.cuff, trim, 0, -0.19, 0, shoulder);
      this.part(g.arm, skin, 0, -0.38, 0, shoulder);
      body.add(shoulder);
      return shoulder;
    });
    const back = new THREE.Mesh(g.backNo, this.numberMat(kit.number, kit.trim, kit.shirt));
    back.position.set(-0.168, 1.2, 0);
    back.rotation.y = -Math.PI / 2;
    body.add(back);
    const front = new THREE.Mesh(g.frontNo, this.numberMat(kit.number, kit.trim, kit.shirt));
    front.position.set(0.164, 1.33, 0.08);
    front.rotation.y = Math.PI / 2;
    body.add(front);

    const hit = new THREE.Mesh(g.hit, this.hitMat);
    hit.position.y = 1.0;
    hit.userData.id = id;
    group.add(hit);
    group.scale.setScalar(FIG_SCALE);
    return { id, keeper, group, body, hit, legs, arms, phase: (h % 628) / 100, swing: 0, lean: 0, move: null };
  }

  dispose() {
    for (const geo of Object.values(this.geo)) geo.dispose();
    this.hitMat.dispose();
    for (const m of this.mats.values()) {
      (m as THREE.MeshLambertMaterial).map?.dispose();
      m.dispose();
    }
  }
}

/** A tackle or interception: a quick lunge with the leading leg. */
export function lunge(f: Figure, now: number, size = 1) {
  if (f.move) return;
  f.move = { kind: "lunge", start: now, dur: 650, dir: 1, yaw: f.group.rotation.y, size };
}

/**
 * A keeper's dive toward where the shot is going. `from` is the shooter and `to` the shot's target,
 * both in world X,Z. The keeper turns to face the shooter and goes to whichever side the ball goes.
 */
export function dive(f: Figure, now: number, from: [number, number], to: [number, number]) {
  const kx = f.group.position.x;
  const kz = f.group.position.z;
  const yaw = Math.atan2(-(from[1] - kz), from[0] - kx);
  // Local +Z of a figure turned by yaw points along (sin yaw, cos yaw) in world X,Z.
  const side = (to[0] - kx) * Math.sin(yaw) + (to[1] - kz) * Math.cos(yaw);
  const reach = Math.min(1, Math.abs(side) / 3.5);
  f.move = { kind: "dive", start: now, dur: 1300, dir: side >= 0 ? 1 : -1, yaw, size: 0.45 + 0.55 * reach };
}

/** Running stride, leaning on the ball, and any move in progress. `dist` is metres moved this tick. */
export function animate(f: Figure, now: number, dist: number, speed: number, onBall: boolean) {
  f.phase += dist * 1.1;
  f.swing += (Math.min(0.7, speed * 0.09) - f.swing) * 0.1;
  const want = onBall && speed > 1 ? -0.24 : -Math.min(0.12, speed * 0.014);
  f.lean += (want - f.lean) * 0.08;
  const s = Math.sin(f.phase) * f.swing;
  f.legs[0].rotation.z = s;
  f.legs[1].rotation.z = -s;
  f.arms[0].rotation.set(ARM_SPLAY, 0, -s * 0.8);
  f.arms[1].rotation.set(-ARM_SPLAY, 0, s * 0.8);
  f.body.rotation.set(0, 0, f.lean);
  f.body.position.set(0, 0, 0);

  const m = f.move;
  if (!m) return;
  const t = (now - m.start) / m.dur;
  if (t >= 1) {
    f.move = null;
    return;
  }
  if (m.kind === "lunge") {
    const k = Math.sin(Math.PI * t) * m.size;
    f.body.rotation.z = f.lean - 0.45 * k;
    f.body.position.y = -0.12 * k;
    f.legs[0].rotation.z = 1.1 * k;
    f.legs[1].rotation.z = -0.35 * k;
    return;
  }
  // Dive: launch, stretch out, land, get up.
  const k = t < 0.3 ? Math.sin((t / 0.3) * (Math.PI / 2)) : t < 0.7 ? 1 : 1 - (t - 0.7) / 0.3;
  f.group.rotation.y = m.yaw;
  f.body.rotation.x = m.dir * 1.3 * k * m.size;
  f.body.position.z = m.dir * 1.0 * k * m.size;
  f.body.position.y = 0.25 * Math.sin(Math.PI * Math.min(1, t / 0.45)) * m.size;
  f.arms[0].rotation.set(ARM_SPLAY + 2.6 * k, 0, 0);
  f.arms[1].rotation.set(-ARM_SPLAY - 2.6 * k, 0, 0);
  f.legs[0].rotation.z = 0.2 * k;
  f.legs[1].rotation.z = -0.2 * k;
}
