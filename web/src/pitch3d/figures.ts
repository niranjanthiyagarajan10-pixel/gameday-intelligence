import * as THREE from "three";
import { FIG_SCALE, clamp, hash } from "./core";

/** A one-off move a player makes on top of running. */
type MoveKind = "lunge" | "dive" | "celebrate" | "cheer" | "slump";

interface Move {
  kind: MoveKind;
  start: number;
  dur: number;
  dir: number; // dive side, +1 or -1 in the figure's own frame
  yaw: number | null; // which way the figure faces during the move, or null to keep running facing
  size: number;
}

/** A leg or arm: the joint at the body, and the joint halfway down (knee or elbow). */
interface Limb {
  root: THREE.Group;
  mid: THREE.Group;
}

export interface Figure {
  id: string;
  keeper: boolean;
  group: THREE.Group; // position and facing
  body: THREE.Group; // everything that leans, banks, bobs or drops during a move
  hit: THREE.Mesh;
  legs: Limb[];
  arms: Limb[];
  phase: number;
  swing: number;
  lean: number;
  bank: number;
  move: Move | null;
}

/** Shirt design. Patterns stay thin so the club's main colour still reads from the stands. */
export type Pattern = "plain" | "pinstripe" | "hoops" | "sash" | "band" | "yoke";
const PATTERNS: Pattern[] = ["pinstripe", "sash", "band", "hoops", "yoke", "plain"];

/** Each club keeps one shirt design, picked from its id so it never changes between matches. */
export function patternFor(clubId: string): Pattern {
  return PATTERNS[hash(clubId) % PATTERNS.length];
}

export interface KitSpec {
  club: string; // club id, for the crest
  shirt: string;
  trim: string;
  shorts: string;
  socks: string;
  number: number;
  pattern: Pattern;
}

const SKIN = [0xe6bf9c, 0xd0a07a, 0xa87552, 0x7c5238, 0x5a3a26];
const HAIR = [0x16110d, 0x2e2118, 0x4a3324, 0x0b0b0b, 0x6b4a2b];
const ARM_SPLAY = 0.1;
const HIP_Y = 0.82;
const KNEE = 0.42; // hip to knee
const SHOULDER_Y = 1.42;
const ELBOW = 0.29; // shoulder to elbow

// Torso outline from the waist up to the collar, as [radius, height] in metres before scaling.
const TORSO: [number, number][] = [
  [0.185, 0.9], [0.195, 0.98], [0.21, 1.08], [0.235, 1.2], [0.252, 1.31], [0.25, 1.39], [0.215, 1.46], [0.13, 1.51], [0.075, 1.53],
];
const SHORTS: [number, number][] = [[0.215, 0.72], [0.22, 0.8], [0.205, 0.9], [0.19, 0.93]];

// Where things sit on the wrapped shirt canvas. Around the torso, u = 0.25 faces forward (+X) and
// u = 0.75 faces back; the player's left side (-Z) is u = 0.5. The canvas top is the collar.
const TEX_W = 512;
const TEX_H = 256;
const FRONT_X = TEX_W * 0.25;
const BACK_X = TEX_W * 0.75;

function drawPattern(g: CanvasRenderingContext2D, pattern: Pattern, trim: string) {
  g.fillStyle = trim;
  if (pattern === "pinstripe") for (let x = 6; x < TEX_W; x += 30) g.fillRect(x, 0, 5, TEX_H);
  else if (pattern === "hoops") for (let y = 40; y < TEX_H; y += 52) g.fillRect(0, y, TEX_W, 14);
  else if (pattern === "band") g.fillRect(0, 78, TEX_W, 34);
  else if (pattern === "yoke") g.fillRect(0, 0, TEX_W, 46);
  else if (pattern === "sash") {
    // A band from the right shoulder down to the left hip, across the front only.
    g.save();
    g.beginPath();
    g.moveTo(FRONT_X - 70, 0);
    g.lineTo(FRONT_X - 30, 0);
    g.lineTo(FRONT_X + 80, TEX_H);
    g.lineTo(FRONT_X + 40, TEX_H);
    g.closePath();
    g.fill();
    g.restore();
  }
}

/**
 * Low-poly player in full kit: a shaped shirt wrapped in a texture with the club pattern, crest and
 * numbers, shorts, socks, boots, rounded shoulders, and knees and elbows that bend. The figure faces
 * local +X. Geometry is shared; materials are cached per colour, shirts per player.
 */
export class FigureKit {
  geo = {
    torso: new THREE.LatheGeometry(TORSO.map(([r, y]) => new THREE.Vector2(r, y)), 22),
    shorts: new THREE.LatheGeometry(SHORTS.map(([r, y]) => new THREE.Vector2(r, y)), 18),
    shortLeg: new THREE.CylinderGeometry(0.105, 0.098, 0.22, 10),
    thigh: new THREE.CylinderGeometry(0.08, 0.068, 0.24, 8),
    shin: new THREE.CylinderGeometry(0.064, 0.046, 0.36, 8),
    boot: new THREE.BoxGeometry(0.25, 0.075, 0.1),
    delt: new THREE.SphereGeometry(0.08, 10, 8),
    sleeve: new THREE.CylinderGeometry(0.082, 0.072, 0.19, 10),
    cuff: new THREE.CylinderGeometry(0.074, 0.074, 0.035, 10),
    upper: new THREE.CylinderGeometry(0.056, 0.05, 0.12, 8),
    fore: new THREE.CylinderGeometry(0.048, 0.04, 0.26, 8),
    hand: new THREE.SphereGeometry(0.046, 8, 6),
    neck: new THREE.CylinderGeometry(0.055, 0.062, 0.1, 10),
    head: new THREE.SphereGeometry(0.108, 16, 12),
    hair: new THREE.SphereGeometry(0.114, 16, 8, 0, Math.PI * 2, 0, Math.PI * 0.44),
    hit: new THREE.CylinderGeometry(0.5, 0.5, 2.0, 8),
  };
  hitMat = new THREE.MeshBasicMaterial({ visible: false });
  mats = new Map<string, THREE.Material>();
  private shirts = new Map<string, { mat: THREE.MeshLambertMaterial; spec: KitSpec }>();
  private crests = new Map<string, HTMLImageElement | null>();

  /** Crest images, drawn on the chest once loaded. `svg` comes from the Crest component. */
  setCrest(club: string, svg: string) {
    if (this.crests.has(club)) return;
    this.crests.set(club, null);
    const img = new Image();
    img.onload = () => {
      this.crests.set(club, img);
      for (const s of this.shirts.values()) if (s.spec.club === club) this.paint(s.mat, s.spec);
    };
    const markup = svg.includes("xmlns=") ? svg : svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
  }

  mat(color: string | number) {
    const key = String(color);
    let m = this.mats.get(key);
    if (!m) {
      m = new THREE.MeshLambertMaterial({ color });
      this.mats.set(key, m);
    }
    return m;
  }

  /** Draws the whole shirt: base colour, pattern, collar and hem trim, crest, and numbers. */
  private paint(mat: THREE.MeshLambertMaterial, k: KitSpec) {
    const c = (mat.map?.image as HTMLCanvasElement | undefined) ?? document.createElement("canvas");
    c.width = TEX_W;
    c.height = TEX_H;
    const g = c.getContext("2d");
    if (g) {
      g.fillStyle = k.shirt;
      g.fillRect(0, 0, TEX_W, TEX_H);
      drawPattern(g, k.pattern, k.trim);
      g.fillStyle = k.trim;
      g.fillRect(0, 0, TEX_W, 7);
      g.fillRect(0, TEX_H - 8, TEX_W, 8);
      const font = (px: number) => `800 ${px}px 'Barlow Condensed', 'Arial Narrow', sans-serif`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.lineJoin = "round";
      // Big number on the back, outlined in the shirt colour so it reads over any pattern.
      g.font = font(132);
      g.lineWidth = 14;
      g.strokeStyle = k.shirt;
      g.strokeText(String(k.number), BACK_X, 132);
      g.fillStyle = k.trim;
      g.fillText(String(k.number), BACK_X, 132);
      // Small number on the right chest, crest on the left chest.
      g.font = font(40);
      g.lineWidth = 6;
      g.strokeText(String(k.number), FRONT_X - 34, 92);
      g.fillText(String(k.number), FRONT_X - 34, 92);
      const crest = this.crests.get(k.club);
      if (crest) g.drawImage(crest, FRONT_X + 18, 62, 40, 46);
    }
    if (mat.map) mat.map.needsUpdate = true;
    else {
      const t = new THREE.CanvasTexture(c);
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = 4;
      mat.map = t;
      mat.needsUpdate = true;
    }
  }

  private shirt(id: string, k: KitSpec) {
    const mat = new THREE.MeshLambertMaterial();
    this.paint(mat, k);
    this.shirts.set(id, { mat, spec: k });
    return mat;
  }

  private part(geo: THREE.BufferGeometry, mat: THREE.Material, x: number, y: number, z: number, parent: THREE.Object3D) {
    const m = new THREE.Mesh(geo, mat);
    m.position.set(x, y, z);
    m.castShadow = true;
    parent.add(m);
    return m;
  }

  make(id: string, keeper: boolean, kit: KitSpec): Figure {
    const group = new THREE.Group();
    const body = new THREE.Group();
    group.add(body);
    const h = hash(id);
    const skin = this.mat(SKIN[h % SKIN.length]);
    const hair = this.mat(HAIR[(h >> 4) % HAIR.length]);
    const sleeveMat = this.mat(kit.pattern === "yoke" ? kit.trim : kit.shirt);
    const trim = this.mat(kit.trim);
    const g = this.geo;

    const legs = [-0.1, 0.1].map((z) => {
      const root = new THREE.Group();
      root.position.set(0, HIP_Y, z);
      this.part(g.shortLeg, this.mat(kit.shorts), 0, -0.1, 0, root);
      this.part(g.thigh, skin, 0, -0.3, 0, root);
      const mid = new THREE.Group();
      mid.position.y = -KNEE;
      this.part(g.shin, this.mat(kit.socks), 0, -0.18, 0, mid);
      this.part(g.boot, this.mat(0x111111), 0.045, -0.37, 0, mid);
      root.add(mid);
      body.add(root);
      return { root, mid };
    });
    this.part(g.shorts, this.mat(kit.shorts), 0, 0, 0, body).scale.x = 0.78;
    this.part(g.torso, this.shirt(id, kit), 0, 0, 0, body).scale.x = 0.72;
    this.part(g.neck, skin, 0, 1.55, 0, body);
    const head = this.part(g.head, skin, 0.005, 1.67, 0, body);
    head.scale.set(0.94, 1.1, 0.9);
    this.part(g.hair, hair, -0.012, 1.69, 0, body).scale.set(0.96, 1.05, 0.94);
    const arms = [-0.265, 0.265].map((z) => {
      const root = new THREE.Group();
      root.position.set(0, SHOULDER_Y, z);
      this.part(g.delt, sleeveMat, 0, -0.01, 0, root).scale.set(1, 0.85, 1);
      this.part(g.sleeve, sleeveMat, 0, -0.1, 0, root);
      this.part(g.cuff, trim, 0, -0.2, 0, root);
      this.part(g.upper, skin, 0, -0.25, 0, root);
      const mid = new THREE.Group();
      mid.position.y = -ELBOW;
      this.part(g.fore, skin, 0, -0.13, 0, mid);
      this.part(g.hand, skin, 0, -0.28, 0, mid);
      root.add(mid);
      body.add(root);
      return { root, mid };
    });

    const hit = new THREE.Mesh(g.hit, this.hitMat);
    hit.position.y = 1.0;
    hit.userData.id = id;
    group.add(hit);
    group.scale.setScalar(FIG_SCALE);
    return { id, keeper, group, body, hit, legs, arms, phase: (h % 628) / 100, swing: 0, lean: 0, bank: 0, move: null };
  }

  /** A figure is leaving the pitch: free its own shirt. */
  release(id: string) {
    const s = this.shirts.get(id);
    if (!s) return;
    s.mat.map?.dispose();
    s.mat.dispose();
    this.shirts.delete(id);
  }

  dispose() {
    for (const geo of Object.values(this.geo)) geo.dispose();
    this.hitMat.dispose();
    for (const m of this.mats.values()) m.dispose();
    for (const id of [...this.shirts.keys()]) this.release(id);
  }
}

/** A tackle or interception: a quick lunge with the leading leg. */
export function lunge(f: Figure, now: number, size = 1) {
  if (f.move) return;
  f.move = { kind: "lunge", start: now, dur: 650, dir: 1, yaw: null, size };
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

/** After a goal: the scorer jumps with both arms up, team-mates punch the air, the beaten side slumps. */
export function react(f: Figure, now: number, kind: "celebrate" | "cheer" | "slump", delay = 0) {
  if (f.move?.kind === "dive" && now - f.move.start < f.move.dur * 0.7) return;
  f.move = { kind, start: now + delay, dur: kind === "slump" ? 3600 : 4200, dir: 1, yaw: null, size: 1 };
}

/**
 * Running stride with knee and elbow bend, a lean that grows with speed and on the ball, a bank into
 * turns, and any move in progress. `dist` is metres moved this tick and `turn` the change in facing.
 */
export function animate(f: Figure, now: number, dist: number, speed: number, onBall: boolean, turn: number) {
  f.phase += dist * 1.15;
  f.swing += (Math.min(0.75, speed * 0.1) - f.swing) * 0.1;
  const sprint = clamp((speed - 4) / 4, 0, 1);
  const wantLean = -Math.min(0.12, speed * 0.016) - 0.1 * sprint - (onBall && speed > 1 ? 0.1 : 0);
  f.lean += (wantLean - f.lean) * 0.08;
  f.bank += (clamp(-turn * 6, -0.22, 0.22) * Math.min(1, speed / 3) - f.bank) * 0.1;

  const run = f.swing;
  for (let i = 0; i < 2; i++) {
    const p = f.phase + i * Math.PI;
    const s = Math.sin(p) * run;
    // The knee folds most as the leg swings through, and stays a little soft when standing.
    f.legs[i].root.rotation.set(0, 0, s);
    f.legs[i].mid.rotation.set(0, 0, -(0.06 + run * 0.25 + run * 1.3 * Math.max(0, Math.sin(p - 0.7))));
    f.arms[i].root.rotation.set(i === 0 ? ARM_SPLAY : -ARM_SPLAY, 0, -s * 0.85);
    f.arms[i].mid.rotation.set(0, 0, 0.25 + run * 1.25);
  }
  f.body.rotation.set(f.bank, 0, f.lean);
  f.body.position.set(0, Math.abs(Math.sin(f.phase)) * 0.045 * run, 0);

  const m = f.move;
  if (!m || now < m.start) return;
  const t = (now - m.start) / m.dur;
  if (t >= 1) {
    f.move = null;
    return;
  }
  const arms = f.arms;
  const legs = f.legs;
  if (m.kind === "lunge") {
    const k = Math.sin(Math.PI * t) * m.size;
    f.body.rotation.z = f.lean - 0.45 * k;
    f.body.position.y = -0.12 * k;
    legs[0].root.rotation.z = 1.1 * k;
    legs[0].mid.rotation.z = -0.1 * k;
    legs[1].root.rotation.z = -0.35 * k;
    legs[1].mid.rotation.z = -0.9 * k;
    return;
  }
  if (m.kind === "dive") {
    // Launch, stretch out, land, get up.
    const k = t < 0.3 ? Math.sin((t / 0.3) * (Math.PI / 2)) : t < 0.7 ? 1 : 1 - (t - 0.7) / 0.3;
    if (m.yaw !== null) f.group.rotation.y = m.yaw;
    f.body.rotation.x = m.dir * 1.3 * k * m.size;
    f.body.position.z = m.dir * 1.0 * k * m.size;
    f.body.position.y = 0.25 * Math.sin(Math.PI * Math.min(1, t / 0.45)) * m.size;
    arms[0].root.rotation.set(ARM_SPLAY + 2.6 * k, 0, 0);
    arms[1].root.rotation.set(-ARM_SPLAY - 2.6 * k, 0, 0);
    arms[0].mid.rotation.z = arms[1].mid.rotation.z = 0.1;
    legs[0].root.rotation.z = 0.2 * k;
    legs[1].root.rotation.z = -0.2 * k;
    legs[0].mid.rotation.z = legs[1].mid.rotation.z = -0.3 * k;
    return;
  }
  // Fade the pose in over the first fifth of a second and out over the last half second.
  const k = Math.min(1, (now - m.start) / 200, (m.dur - (now - m.start)) / 500);
  if (m.kind === "slump") {
    // Bent over, hands on knees.
    f.body.rotation.z = f.lean - 0.55 * k;
    f.body.position.y = -0.1 * k;
    for (const leg of legs) leg.mid.rotation.z = -0.55 * k;
    for (const leg of legs) leg.root.rotation.z = 0.3 * k;
    for (const arm of arms) {
      arm.root.rotation.z = 0.75 * k;
      arm.mid.rotation.z = 0.15;
    }
    return;
  }
  const secs = (now - m.start) / 1000;
  if (m.kind === "celebrate") {
    // Both arms up in a V, jumping for the first two seconds.
    const hop = secs < 2 ? Math.abs(Math.sin(secs * 7)) * 0.32 : 0;
    f.body.position.y += hop * k;
    f.body.rotation.z = f.lean * (1 - k) + 0.08 * k;
    arms[0].root.rotation.set(ARM_SPLAY + 2.55 * k, 0, 0);
    arms[1].root.rotation.set(-ARM_SPLAY - 2.55 * k, 0, 0);
    arms[0].mid.rotation.z = arms[1].mid.rotation.z = 0.15;
    if (hop > 0.05) for (const leg of legs) leg.mid.rotation.z = -0.5 * k;
    return;
  }
  // Cheer: alternate fist pumps.
  const pump = (i: number) => 1.9 + 0.6 * Math.sin(secs * 9 + i * Math.PI);
  arms[0].root.rotation.set(ARM_SPLAY + pump(0) * k * 0.55, 0, 0.2 * k);
  arms[1].root.rotation.set(-ARM_SPLAY - pump(1) * k * 0.55, 0, 0.2 * k);
  arms[0].mid.rotation.z = arms[1].mid.rotation.z = 0.25 + 1.2 * k;
}
