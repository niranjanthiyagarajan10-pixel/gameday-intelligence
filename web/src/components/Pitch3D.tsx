import { Component, forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { ReactNode } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Frame, FxEvent, Roster } from "../types";
import { Pitch } from "./Pitch";

/**
 * Interactive 3D pitch for the Live tab. Same props as the 2D Pitch, plus `onSelect` for click to
 * focus. Pitch metres map to world units: x 0..105 runs along world X, y 0..68 along world Z, up is Y.
 * If WebGL is missing or the scene throws, the 2D Pitch renders instead.
 */

export interface Pitch3DProps {
  frame: Frame | null;
  roster: Roster;
  focus: string | null;
  tagged: Set<string>;
  speed: number;
  fx: FxEvent[];
  labels?: Record<string, string>;
  onSelect?: (id: string) => void;
}

/** A spot on the pitch in metres, a player id, or "ball". */
export type Spot = { x: number; y: number } | string;
export type Preset = "broadcast" | "goal" | "tactical" | "follow";

export interface OverlayStyle {
  color?: string; // CSS colour, default the signal colour
  width?: number; // metres
  opacity?: number;
}

/** Imperative API for telestration. Every draw call returns an id for removeOverlay. */
export interface Pitch3DApi {
  flyTo(target: Spot, duration?: number, opts?: { distance?: number; height?: number }): void;
  setPreset(p: Preset): void;
  drawArrow(a: Spot, b: Spot, style?: OverlayStyle): string;
  drawLine(a: Spot, b: Spot, style?: OverlayStyle): string;
  drawRing(at: Spot, radius?: number, style?: OverlayStyle): string;
  drawZone(at: Spot, radius: number, style?: OverlayStyle): string;
  removeOverlay(id: string): void;
  clearOverlays(): void;
}

const L = 105;
const W = 68;
const FIG_SCALE = 1.5; // figures a bit larger than life so they read at broadcast distance
const BALL_R = 0.26;
const GROUND = 0.02;
const PRESET_LABEL: Record<Preset, string> = { broadcast: "Broadcast", goal: "Behind goal", tactical: "Tactical", follow: "Follow ball" };
const VIEW_KEY = "gdi.pitch3d.preset";

const wx = (x: number) => x - L / 2;
const wz = (y: number) => y - W / 2;

export function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

function cssColor(name: string, fallback: string) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch {
    return fallback;
  }
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

/** Flat shapes on the grass. Everything shares one material style: unlit, no depth write. */
function flatMat(color: string | number, opacity = 1) {
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

function strip(x1: number, z1: number, x2: number, z2: number, w: number, mat: THREE.Material, y = GROUND) {
  const len = Math.hypot(x2 - x1, z2 - z1);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(len, w), mat);
  m.rotation.x = -Math.PI / 2;
  m.rotation.z = -Math.atan2(z2 - z1, x2 - x1);
  m.position.set((x1 + x2) / 2, y, (z1 + z2) / 2);
  return m;
}

function arc(cx: number, cz: number, r: number, w: number, start: number, len: number, mat: THREE.Material, y = GROUND) {
  const m = new THREE.Mesh(new THREE.RingGeometry(r - w / 2, r + w / 2, 96, 1, start, len), mat);
  m.rotation.x = -Math.PI / 2;
  m.position.set(cx, y, cz);
  return m;
}

function disc(cx: number, cz: number, r: number, mat: THREE.Material, y = GROUND) {
  const m = new THREE.Mesh(new THREE.CircleGeometry(r, 48), mat);
  m.rotation.x = -Math.PI / 2;
  m.position.set(cx, y, cz);
  return m;
}

/** Grass with mowing stripes, the standard markings, and both goals with nets. */
function buildPitch(): THREE.Group {
  const g = new THREE.Group();
  const surround = new THREE.Mesh(new THREE.PlaneGeometry(L + 30, W + 24), new THREE.MeshLambertMaterial({ color: 0x0a120d }));
  surround.rotation.x = -Math.PI / 2;
  surround.position.y = -0.01;
  surround.receiveShadow = true;
  g.add(surround);
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
  g.add(disc(0, 0, 0.25, spot));
  const penAng = Math.acos(5.5 / 9.15);
  for (const left of [true, false]) {
    const x0 = left ? 0 : L;
    const s = left ? 1 : -1;
    rect(Math.min(x0, x0 + s * 16.5), 13.84, Math.max(x0, x0 + s * 16.5), 54.16);
    rect(Math.min(x0, x0 + s * 5.5), 24.84, Math.max(x0, x0 + s * 5.5), 43.16);
    const px = wx(left ? 11 : 94);
    g.add(disc(px, 0, 0.22, spot));
    // RingGeometry angles run counterclockwise from +X in its own plane; after laying it flat the
    // arc at angle a sits at (cos a, -sin a) in world X,Z, symmetric about the axis either way.
    g.add(arc(px, 0, 9.15, lw, left ? -penAng : Math.PI - penAng, 2 * penAng, line));
    g.add(buildGoal(left));
  }
  for (const [cx, cz, start] of [
    [0, 0, -Math.PI / 2],
    [L, 0, Math.PI],
    [0, W, 0],
    [L, W, Math.PI / 2],
  ] as const) {
    g.add(arc(wx(cx), wz(cz), 1, lw, start, Math.PI / 2, line));
  }
  return g;
}

function buildGoal(left: boolean): THREE.Group {
  const g = new THREE.Group();
  const h = 2.44;
  const half = 7.32 / 2;
  const depth = 2;
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

  // Net as a grid of line segments: back, roof and two sides. Depth runs toward -X here.
  const pts: number[] = [];
  const seg = (a: number[], b: number[]) => pts.push(...a, ...b);
  const step = 0.35;
  for (let z = -half; z <= half + 1e-6; z += step) {
    seg([0, h, z], [-depth, h * 0.8, z]);
    seg([-depth, h * 0.8, z], [-depth, 0, z]);
  }
  for (let y = 0; y <= h * 0.8 + 1e-6; y += step) seg([-depth, y, -half], [-depth, y, half]);
  for (let d = 0; d <= depth + 1e-6; d += step) {
    const y = h - (0.2 * h * d) / depth;
    seg([-d, y, -half], [-d, y, half]);
    for (const z of [-half, half]) seg([-d, 0, z], [-d, y, z]);
  }
  for (let y = 0; y <= h + 1e-6; y += step) {
    // Side panels: the roof slopes down from the bar to 80% height at the back.
    const back = y <= h * 0.8 ? depth : (depth * (h - y)) / (0.2 * h);
    for (const z of [-half, half]) seg([0, y, z], [-back, y, z]);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  g.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.32 })));
  g.position.set(wx(left ? 0 : L), 0, 0);
  if (!left) g.rotation.y = Math.PI;
  return g;
}

interface Figure {
  group: THREE.Group;
  hit: THREE.Mesh;
  legs: THREE.Group[];
  arms: THREE.Group[];
  phase: number;
  swing: number;
}

const SKIN = [0xe6bf9c, 0xd0a07a, 0xa87552, 0x7c5238, 0x5a3a26];
const HAIR = [0x16110d, 0x2e2118, 0x4a3324, 0x0b0b0b, 0x6b4a2b];

/** Stable small hash so each synthetic player keeps the same look in every session. */
function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

/** Shirt number drawn on a transparent canvas, used as a decal on the back and chest. */
function numberTexture(n: number, color: string, edge: string) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  if (g) {
    g.font = "700 96px 'Barlow Condensed', 'Arial Narrow', sans-serif";
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.lineWidth = 6;
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
 * number on the back and chest. Legs and arms hang from pivots so they can swing with running speed.
 * The figure faces local +X. Geometry is shared; materials are cached per colour.
 */
class FigureKit {
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
    backNo: new THREE.PlaneGeometry(0.26, 0.26),
    frontNo: new THREE.PlaneGeometry(0.11, 0.11),
    hit: new THREE.CylinderGeometry(0.6, 0.6, 2.2, 8),
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

  part(geo: THREE.BufferGeometry, mat: THREE.Material, x: number, y: number, z: number, parent: THREE.Object3D) {
    const m = new THREE.Mesh(geo, mat);
    m.position.set(x, y, z);
    m.castShadow = true;
    parent.add(m);
    return m;
  }

  make(id: string, kit: { shirt: string; trim: string; shorts: string; socks: string; number: number }): Figure {
    const group = new THREE.Group();
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
      group.add(hip);
      return hip;
    });
    const shorts = this.part(g.shorts, this.mat(kit.shorts), 0, 0.78, 0, group);
    shorts.scale.x = 0.75;
    const torso = this.part(g.torso, shirt, 0, 1.2, 0, group);
    torso.scale.x = 0.68;
    this.part(g.collar, trim, 0, 1.5, 0, group);
    this.part(g.neck, skin, 0, 1.55, 0, group);
    this.part(g.head, skin, 0, 1.67, 0, group);
    this.part(g.hair, hair, -0.01, 1.68, 0, group);
    const arms = [-0.29, 0.29].map((z) => {
      const shoulder = new THREE.Group();
      shoulder.position.set(0, 1.45, z);
      shoulder.rotation.x = z < 0 ? 0.12 : -0.12;
      this.part(g.sleeve, shirt, 0, -0.08, 0, shoulder);
      this.part(g.cuff, trim, 0, -0.19, 0, shoulder);
      this.part(g.arm, skin, 0, -0.38, 0, shoulder);
      group.add(shoulder);
      return shoulder;
    });
    const back = new THREE.Mesh(g.backNo, this.numberMat(kit.number, kit.trim, kit.shirt));
    back.position.set(-0.165, 1.2, 0);
    back.rotation.y = -Math.PI / 2;
    group.add(back);
    const front = new THREE.Mesh(g.frontNo, this.numberMat(kit.number, kit.trim, kit.shirt));
    front.position.set(0.162, 1.33, 0.08);
    front.rotation.y = Math.PI / 2;
    group.add(front);

    const hit = new THREE.Mesh(g.hit, this.hitMat);
    hit.position.y = 1.1;
    hit.userData.id = id;
    group.add(hit);
    group.scale.setScalar(FIG_SCALE);
    return { group, hit, legs, arms, phase: (h % 628) / 100, swing: 0 };
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

/**
 * Equirectangular texture for a classic black and white football: 12 black pentagons and 20 white
 * hexagons with dark seams. Each texel takes the nearest panel centre; pentagon distances are scaled
 * up a little because pentagons are smaller panels than hexagons.
 */
function footballTexture() {
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
        const seam = second - best < 0.025;
        const v = seam ? 70 : pent ? 22 : 238;
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

interface Overlay {
  obj: THREE.Object3D;
  follow?: string; // player id or "ball" the overlay sticks to
}

interface Fly {
  p0: THREE.Vector3;
  t0: THREE.Vector3;
  p1: THREE.Vector3;
  t1: THREE.Vector3;
  start: number;
  dur: number;
}

const PRESETS: Record<Exclude<Preset, "follow">, { pos: [number, number, number]; target: [number, number, number] }> = {
  broadcast: { pos: [0, 50, 80], target: [0, 0, 4] },
  goal: { pos: [-L / 2 - 26, 20, 0], target: [6, 0, 0] },
  tactical: { pos: [0, 112, 0.1], target: [0, 0, 0] },
};
const FOLLOW_OFFSET = new THREE.Vector3(0, 26, 34);

/**
 * The live scene. Built once per mount; frames, focus and fx flow in through refs so React renders
 * never rebuild WebGL state. Calls onFail if anything in setup or the render loop throws.
 */
const Scene = forwardRef<Pitch3DApi, Pitch3DProps & { onFail: () => void }>(function Scene(props, ref) {
  const host = useRef<HTMLDivElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const api = useRef<Pitch3DApi | null>(null);
  const live = useRef(props);
  live.current = props;
  const [preset, setPresetState] = useState<Preset>(() => {
    try {
      const v = localStorage.getItem(VIEW_KEY);
      return v && v in PRESET_LABEL ? (v as Preset) : "broadcast";
    } catch {
      return "broadcast";
    }
  });
  const frameIn = useRef<((f: Frame) => void) | null>(null);

  useImperativeHandle(ref, () => ({
    flyTo: (...a) => api.current?.flyTo(...a),
    setPreset: (p) => setPresetState(p),
    drawArrow: (...a) => api.current?.drawArrow(...a) ?? "",
    drawLine: (...a) => api.current?.drawLine(...a) ?? "",
    drawRing: (...a) => api.current?.drawRing(...a) ?? "",
    drawZone: (...a) => api.current?.drawZone(...a) ?? "",
    removeOverlay: (id) => api.current?.removeOverlay(id),
    clearOverlays: () => api.current?.clearOverlays(),
  }));

  useEffect(() => {
    if (props.frame) frameIn.current?.(props.frame);
  }, [props.frame]);

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_KEY, preset);
    } catch {
      /* storage blocked: the preset just is not remembered */
    }
    if (preset !== "follow") {
      const p = PRESETS[preset];
      apiPreset.current?.(new THREE.Vector3(...p.pos), new THREE.Vector3(...p.target), false);
    } else apiPreset.current?.(null, null, true);
  }, [preset]);
  const apiPreset = useRef<((pos: THREE.Vector3 | null, target: THREE.Vector3 | null, follow: boolean) => void) | null>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    } catch {
      props.onFail();
      return;
    }
    const failed = { v: false };
    const fail = () => {
      if (failed.v) return;
      failed.v = true;
      props.onFail();
    };
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.setClearColor(0x000000, 1);
    el.appendChild(renderer.domElement);
    renderer.domElement.addEventListener("webglcontextlost", fail);

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x000000, 140, 260);
    const camera = new THREE.PerspectiveCamera(38, 1, 0.5, 600);
    const start = PRESETS[preset === "follow" ? "broadcast" : preset];
    camera.position.set(...start.pos);

    scene.add(new THREE.HemisphereLight(0xffffff, 0x1a2a1e, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-30, 70, 40);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.radius = 4;
    sun.shadow.bias = -0.0005;
    Object.assign(sun.shadow.camera, { left: -65, right: 65, top: 45, bottom: -45, near: 10, far: 200 });
    scene.add(sun);
    scene.add(buildPitch());

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(...start.target);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 12;
    controls.maxDistance = 170;
    controls.maxPolarAngle = Math.PI / 2 - 0.06; // never below the grass
    controls.update();

    const signal = cssColor("--signal", "#e8ff3a");
    const kit = new FigureKit();
    const figures = new Map<string, Figure>();
    const players = new THREE.Group();
    scene.add(players);
    const ringGeo = new THREE.RingGeometry(1.5, 1.75, 48);
    const tagGeo = new THREE.RingGeometry(1.3, 1.42, 48);
    const ringMat = flatMat(signal, 0.95);
    const tagMat = flatMat(signal, 0.6);
    const rings = new Map<string, THREE.Mesh>();

    const ball = new THREE.Mesh(new THREE.SphereGeometry(BALL_R, 24, 16), new THREE.MeshLambertMaterial({ map: footballTexture() }));
    ball.castShadow = true;
    ball.visible = false;
    scene.add(ball);
    const ballShadow = disc(0, 0, BALL_R * 1.6, flatMat(0x000000, 0.45), 0.03);
    ballShadow.visible = false;
    scene.add(ballShadow);

    // Glide between frames, the same way the 2D pitch does.
    let from = new Map<string, number[]>();
    let to = new Map<string, number[]>();
    const drawn = new Map<string, number[]>();
    let glideStart = 0;
    let gap = 200;
    let last = 0;
    frameIn.current = (f) => {
      const now = performance.now();
      if (last) gap = Math.min(500, Math.max(60, 0.7 * gap + 0.3 * (now - last)));
      last = now;
      const next = new Map<string, number[]>(f.players.map((p) => [p[0], [p[1], p[2], p[3]]])); // x, y, speed
      next.set("ball", [f.ball[0], f.ball[1], f.ball[2] ?? 0]);
      from = new Map(drawn);
      to = next;
      glideStart = now;
    };
    if (live.current.frame) frameIn.current(live.current.frame);

    const pos = (s: Spot): [number, number] | null => {
      if (typeof s !== "string") return [s.x, s.y];
      const p = drawn.get(s) ?? to.get(s);
      return p ? [p[0], p[1]] : null;
    };

    // Overlays drawn on the grass for telestration.
    const overlays = new Map<string, Overlay>();
    const overlayRoot = new THREE.Group();
    scene.add(overlayRoot);
    let seq = 0;
    const addOverlay = (obj: THREE.Object3D, follow?: string) => {
      const id = `ov${++seq}`;
      overlayRoot.add(obj);
      overlays.set(id, { obj, follow });
      return id;
    };
    const disposeObj = (o: THREE.Object3D) =>
      o.traverse((c) => {
        const m = c as THREE.Mesh;
        m.geometry?.dispose();
        const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
        for (const mat of mats) {
          (mat as THREE.MeshLambertMaterial).map?.dispose();
          mat.dispose();
        }
      });
    const removeOverlay = (id: string) => {
      const o = overlays.get(id);
      if (!o) return;
      overlayRoot.remove(o.obj);
      disposeObj(o.obj);
      overlays.delete(id);
    };
    const styleOf = (s?: OverlayStyle) => ({ color: s?.color ?? signal, width: s?.width ?? 0.45, opacity: s?.opacity ?? 0.9 });
    const lineObj = (a: [number, number], b: [number, number], s: ReturnType<typeof styleOf>, head: boolean) => {
      const g = new THREE.Group();
      const mat = flatMat(s.color, s.opacity);
      const [ax, az, bx, bz] = [wx(a[0]), wz(a[1]), wx(b[0]), wz(b[1])];
      const len = Math.hypot(bx - ax, bz - az) || 0.001;
      const ux = (bx - ax) / len;
      const uz = (bz - az) / len;
      const hl = head ? Math.min(len * 0.4, s.width * 5) : 0;
      g.add(strip(ax, az, bx - ux * hl, bz - uz * hl, s.width, mat, 0.04));
      if (head) {
        const hw = s.width * 2.4;
        const shape = new THREE.Shape([new THREE.Vector2(0, 0), new THREE.Vector2(-hl, hw), new THREE.Vector2(-hl, -hw)]);
        const tri = new THREE.Mesh(new THREE.ShapeGeometry(shape), mat);
        tri.rotation.x = -Math.PI / 2;
        tri.rotation.z = -Math.atan2(bz - az, bx - ax);
        tri.position.set(bx, 0.04, bz);
        g.add(tri);
      }
      return g;
    };
    const center = (at: Spot) => pos(at) ?? [L / 2, W / 2];
    const follows = (at: Spot) => (typeof at === "string" ? at : undefined);

    const fly: { cur: Fly | null } = { cur: null };
    let following = preset === "follow";
    const flyCam = (p1: THREE.Vector3, t1: THREE.Vector3, dur: number) => {
      fly.cur = { p0: camera.position.clone(), t0: controls.target.clone(), p1, t1, start: performance.now(), dur: Math.max(1, dur) };
    };

    api.current = {
      flyTo(target, duration = 1200, opts = {}) {
        const c = center(target);
        const t1 = new THREE.Vector3(wx(c[0]), 0, wz(c[1]));
        const dir = camera.position.clone().sub(controls.target).setY(0);
        if (dir.lengthSq() < 1e-3) dir.set(0, 0, 1);
        dir.normalize().multiplyScalar(opts.distance ?? 26);
        const p1 = t1.clone().add(dir).setY(opts.height ?? 16);
        following = false;
        flyCam(p1, t1, duration);
      },
      setPreset: () => undefined,
      drawArrow: (a, b, s) => addOverlay(lineObj(center(a), center(b), styleOf(s), true)),
      drawLine: (a, b, s) => addOverlay(lineObj(center(a), center(b), styleOf(s), false)),
      drawRing(at, radius = 2.2, s) {
        const st = styleOf(s);
        const c = center(at);
        return addOverlay(arc(wx(c[0]), wz(c[1]), radius, st.width * 0.6, 0, Math.PI * 2, flatMat(st.color, st.opacity), 0.04), follows(at));
      },
      drawZone(at, radius, s) {
        const st = styleOf(s);
        const c = center(at);
        return addOverlay(disc(wx(c[0]), wz(c[1]), radius, flatMat(st.color, s?.opacity ?? 0.22), 0.035), follows(at));
      },
      removeOverlay,
      clearOverlays: () => [...overlays.keys()].forEach(removeOverlay),
    };
    apiPreset.current = (p, t, follow) => {
      following = follow;
      if (follow) {
        const b = drawn.get("ball") ?? [L / 2, W / 2];
        const t1 = new THREE.Vector3(wx(b[0]), 0, wz(b[1]));
        flyCam(t1.clone().add(FOLLOW_OFFSET), t1, 1100);
      } else if (p && t) flyCam(p, t, 1100);
    };

    // Short-lived pass and shot lines from the fx feed.
    const seen = new Set<string>();
    const fxLife = new Map<string, number>();
    const syncFx = (now: number) => {
      const { fx, roster } = live.current;
      for (const e of fx) {
        if (seen.has(e.id) || now - e.at > 1500) continue;
        seen.add(e.id);
        if ((e.type !== "pass" && e.type !== "shot") || e.end_x === null || e.end_y === null) continue;
        const color = e.type === "pass" && e.outcome !== "complete" ? "#ffffff" : roster.clubs[e.team].primary;
        const id = addOverlay(lineObj([e.x, e.y], [e.end_x, e.end_y], { color, width: e.type === "shot" ? 0.3 : 0.18, opacity: 0.7 }, e.type === "shot"));
        fxLife.set(id, now + (e.type === "shot" ? 2000 : 1200));
      }
      for (const [id, until] of fxLife) {
        if (now > until) {
          removeOverlay(id);
          fxLife.delete(id);
        }
      }
      if (seen.size > 2000) seen.clear();
    };

    const syncFigures = () => {
      const { roster, focus, tagged } = live.current;
      for (const id of to.keys()) {
        if (id === "ball" || figures.has(id)) continue;
        const info = roster.players[id];
        if (!info) continue;
        const club = roster.clubs[info.side];
        // Keepers wear a dark kit trimmed in the club colour, as on the 2D pitch.
        const f = info.position === "GK"
          ? kit.make(id, { shirt: "#16181b", trim: club.primary, shorts: "#16181b", socks: "#16181b", number: info.number })
          : kit.make(id, { shirt: club.primary, trim: club.secondary, shorts: club.secondary, socks: club.primary, number: info.number });
        figures.set(id, f);
        players.add(f.group);
      }
      for (const [id, f] of figures) {
        if (!to.has(id)) {
          players.remove(f.group);
          figures.delete(id);
        }
      }
      for (const [id, f] of figures) {
        const want = id === focus ? ringGeo : tagged.has(id) ? tagGeo : null;
        let r = rings.get(id);
        if (!want) {
          if (r) {
            scene.remove(r);
            rings.delete(id);
          }
          continue;
        }
        if (!r) {
          r = new THREE.Mesh(want, want === ringGeo ? ringMat : tagMat);
          r.rotation.x = -Math.PI / 2;
          scene.add(r);
          rings.set(id, r);
        }
        r.geometry = want;
        r.material = want === ringGeo ? ringMat : tagMat;
        r.position.set(f.group.position.x, 0.045, f.group.position.z);
      }
    };

    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const lastBall = new THREE.Vector3();
    const rollAxis = new THREE.Vector3();
    const tick = () => {
      if (failed.v) return;
      try {
        const now = performance.now();
        const a = still ? 1 : Math.min(1, (now - glideStart) / gap);
        for (const [id, target] of to) {
          const f = from.get(id);
          const v = target.map((t, k) => (f && f[k] !== undefined ? f[k] + (t - f[k]) * a : t));
          const prev = drawn.get(id);
          drawn.set(id, v);
          if (id === "ball") {
            const z = Math.min(Math.max(v[2] ?? 0, 0), 25);
            ball.visible = ballShadow.visible = true;
            ball.position.set(wx(v[0]), BALL_R + z, wz(v[1]));
            ballShadow.position.set(wx(v[0]), 0.03, wz(v[1]));
            ballShadow.scale.setScalar(Math.max(0.5, 1 - z * 0.06));
            (ballShadow.material as THREE.MeshBasicMaterial).opacity = Math.max(0.15, 0.45 - z * 0.025);
            if (prev) {
              // Roll about the horizontal axis at right angles to the direction of travel.
              const dx = v[0] - prev[0];
              const dz = v[1] - prev[1];
              const d = Math.hypot(dx, dz);
              if (d > 1e-4 && z < 0.5) ball.rotateOnWorldAxis(rollAxis.set(dz / d, 0, -dx / d), d / BALL_R);
            }
            continue;
          }
          const fig = figures.get(id);
          if (!fig) continue;
          if (prev && (v[0] - prev[0]) ** 2 + (v[1] - prev[1]) ** 2 > 1e-5) {
            const want = Math.atan2(-(v[1] - prev[1]), v[0] - prev[0]);
            let d = want - fig.group.rotation.y;
            d = ((d + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
            fig.group.rotation.y += d * 0.2;
          }
          fig.group.position.set(wx(v[0]), 0, wz(v[1]));
          // Running cycle: stride follows distance covered, swing grows with speed.
          if (prev) fig.phase += Math.hypot(v[0] - prev[0], v[1] - prev[1]) * 2.4;
          fig.swing += (Math.min(0.7, (v[2] ?? 0) * 0.09) - fig.swing) * 0.1;
          const s = Math.sin(fig.phase) * fig.swing;
          fig.legs[0].rotation.z = s;
          fig.legs[1].rotation.z = -s;
          fig.arms[0].rotation.z = -s * 0.8;
          fig.arms[1].rotation.z = s * 0.8;
        }
        syncFigures();
        syncFx(now);
        for (const o of overlays.values()) {
          if (!o.follow) continue;
          const p = drawn.get(o.follow);
          if (p) o.obj.position.set(wx(p[0]), o.obj.position.y, wz(p[1]));
        }

        const fl = fly.cur;
        if (fl) {
          const k = ease(Math.min(1, (now - fl.start) / fl.dur));
          camera.position.lerpVectors(fl.p0, fl.p1, k);
          controls.target.lerpVectors(fl.t0, fl.t1, k);
          if (k >= 1) fly.cur = null;
        }
        if (following && ball.visible) {
          const bt = new THREE.Vector3(ball.position.x, 0, ball.position.z);
          if (fl) {
            fl.t1.copy(bt);
            fl.p1.copy(bt).add(FOLLOW_OFFSET);
          } else if (lastBall.lengthSq() > 0) {
            // Move with the ball but keep whatever angle the viewer orbited to.
            const step = bt.clone().sub(controls.target).multiplyScalar(0.12);
            controls.target.add(step);
            camera.position.add(step);
          }
          lastBall.copy(bt).setY(1);
        }
        controls.update();
        renderer.render(scene, camera);
      } catch {
        fail();
      }
    };
    renderer.setAnimationLoop(tick);
    if (preset === "follow") apiPreset.current(null, null, true);

    const resize = () => {
      const w = el.clientWidth || 1;
      const h = el.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    // Hover shows the shirt number; a click without a drag focuses that player.
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const pick = (ev: PointerEvent): string | null => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hits = ray.intersectObjects([...figures.values()].map((f) => f.hit), false);
      return (hits[0]?.object.userData.id as string | undefined) ?? null;
    };
    const onMove = (ev: PointerEvent) => {
      const t = tip.current;
      if (!t) return;
      if (ev.buttons) {
        t.style.display = "none";
        return;
      }
      const id = pick(ev);
      const info = id ? live.current.roster.players[id] : undefined;
      renderer.domElement.style.cursor = info ? "pointer" : "grab";
      if (!info) {
        t.style.display = "none";
        return;
      }
      const r = el.getBoundingClientRect();
      t.textContent = `#${info.number} ${info.short}`;
      t.style.display = "block";
      t.style.left = `${ev.clientX - r.left + 12}px`;
      t.style.top = `${ev.clientY - r.top - 28}px`;
    };
    let down: [number, number] | null = null;
    const onDown = (ev: PointerEvent) => {
      down = [ev.clientX, ev.clientY];
    };
    const onUp = (ev: PointerEvent) => {
      if (!down || Math.hypot(ev.clientX - down[0], ev.clientY - down[1]) > 5) return;
      down = null;
      const id = pick(ev);
      if (id) live.current.onSelect?.(id);
    };
    const onLeave = () => {
      if (tip.current) tip.current.style.display = "none";
    };
    // A user drag ends any camera flight so the controls never fight the tween.
    const onStart = () => {
      fly.cur = null;
    };
    controls.addEventListener("start", onStart);
    const cv = renderer.domElement;
    cv.addEventListener("pointermove", onMove);
    cv.addEventListener("pointerdown", onDown);
    cv.addEventListener("pointerup", onUp);
    cv.addEventListener("pointerleave", onLeave);

    return () => {
      renderer.setAnimationLoop(null);
      ro.disconnect();
      controls.removeEventListener("start", onStart);
      controls.dispose();
      cv.removeEventListener("pointermove", onMove);
      cv.removeEventListener("pointerdown", onDown);
      cv.removeEventListener("pointerup", onUp);
      cv.removeEventListener("pointerleave", onLeave);
      cv.removeEventListener("webglcontextlost", fail);
      frameIn.current = null;
      api.current = null;
      apiPreset.current = null;
      disposeObj(scene);
      for (const g of [ringGeo, tagGeo]) g.dispose();
      for (const m of [ringMat, tagMat]) m.dispose();
      kit.dispose();
      renderer.dispose();
      cv.remove();
    };
    // Built once per mount. Live props arrive through refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="pitch3d">
      <div ref={host} className="p3-canvas" />
      <div ref={tip} className="p3-tip" />
      <div className="p3-presets" role="group" aria-label="Camera">
        {(Object.keys(PRESET_LABEL) as Preset[]).map((p) => (
          <button key={p} className={p === preset ? "on" : ""} onClick={() => setPresetState(p)}>
            {PRESET_LABEL[p]}
          </button>
        ))}
      </div>
      <div className="p3-hint label">Drag to orbit. Scroll to zoom. Click a player to focus.</div>
    </div>
  );
});

class Boundary extends Component<{ onFail: () => void; children: ReactNode }, { bad: boolean }> {
  state = { bad: false };
  static getDerivedStateFromError() {
    return { bad: true };
  }
  componentDidCatch() {
    this.props.onFail();
  }
  render() {
    return this.state.bad ? null : this.props.children;
  }
}

/** The 3D pitch with its safety net: no WebGL or any scene error shows the 2D pitch. */
const Pitch3D = forwardRef<Pitch3DApi, Pitch3DProps>(function Pitch3D(props, ref) {
  const [ok, setOk] = useState(webglAvailable);
  const { onSelect: _onSelect, ...flat } = props;
  if (!ok) return <Pitch {...flat} />;
  return (
    <Boundary onFail={() => setOk(false)}>
      <Scene ref={ref} {...props} onFail={() => setOk(false)} />
    </Boundary>
  );
});

export default Pitch3D;
