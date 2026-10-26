import * as THREE from "three";
import type { Roster, Side } from "../types";
import { L, W, wx, wz } from "./core";

export type Layer = "shape" | "passing" | "control";

const OPEN_M = 2.5; // a lane is open when no opponent is closer than this to the line of the pass
const PASS_RANGE_M = 40;
const CONTROL_EVERY_MS = 150;
const CELL = 2.5;
const RUN_MS = 7; // assumed running speed for time to reach a spot
const CONTROL_SPREAD_S = 0.45;

type Pos = Map<string, number[]>; // pitch metres: x, y, ...

/** Distance from point p to the segment a-b, all in pitch metres. */
function segDist(p: number[], a: number[], b: number[]) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy || 1;
  const u = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2));
  return Math.hypot(p[0] - a[0] - u * dx, p[1] - a[1] - u * dy);
}

/**
 * Tactical drawings on the grass, computed each frame from player positions. These are geometry for
 * the eye (who lines up with whom, which passing lanes are clear, who is nearer to each patch of
 * grass), not engine statistics.
 */
export class TacticalLayers {
  readonly group = new THREE.Group();
  on = new Set<Layer>();
  private segGeo = new THREE.PlaneGeometry(1, 1);
  private segs: THREE.Mesh[] = [];
  private used = 0;
  private mats = new Map<string, THREE.MeshBasicMaterial>();
  private control: THREE.Mesh;
  private controlTex: THREE.DataTexture;
  private controlAt = 0;
  private cols = Math.round(L / CELL);
  private rows = Math.round(W / CELL);

  constructor() {
    const data = new Uint8Array(this.cols * this.rows * 4);
    this.controlTex = new THREE.DataTexture(data, this.cols, this.rows, THREE.RGBAFormat);
    this.controlTex.colorSpace = THREE.SRGBColorSpace;
    this.controlTex.magFilter = THREE.LinearFilter;
    this.controlTex.minFilter = THREE.LinearFilter;
    this.control = new THREE.Mesh(
      new THREE.PlaneGeometry(L, W),
      new THREE.MeshBasicMaterial({ map: this.controlTex, transparent: true, depthWrite: false }),
    );
    this.control.rotation.x = -Math.PI / 2;
    this.control.position.y = 0.012;
    this.control.visible = false;
    this.group.add(this.control);
  }

  private mat(color: string, opacity: number) {
    const key = `${color}|${opacity}`;
    let m = this.mats.get(key);
    if (!m) {
      m = new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3 });
      this.mats.set(key, m);
    }
    return m;
  }

  /** Places the next pooled flat strip between two pitch points. */
  private seg(a: number[], b: number[], width: number, mat: THREE.Material) {
    let m = this.segs[this.used];
    if (!m) {
      m = new THREE.Mesh(this.segGeo, mat);
      m.rotation.order = "YXZ";
      this.segs.push(m);
      this.group.add(m);
    }
    this.used++;
    const ax = wx(a[0]);
    const az = wz(a[1]);
    const bx = wx(b[0]);
    const bz = wz(b[1]);
    m.material = mat;
    m.visible = true;
    m.position.set((ax + bx) / 2, 0.05, (az + bz) / 2);
    m.rotation.set(-Math.PI / 2, -Math.atan2(bz - az, bx - ax), 0);
    m.scale.set(Math.hypot(bx - ax, bz - az), width, 1);
  }

  update(now: number, pos: Pos, roster: Roster, carrier: string | null) {
    this.used = 0;
    if (this.on.has("shape")) this.shape(pos, roster);
    if (this.on.has("passing") && carrier) this.passing(pos, roster, carrier);
    for (let i = this.used; i < this.segs.length; i++) this.segs[i].visible = false;
    this.control.visible = this.on.has("control");
    if (this.control.visible && now - this.controlAt > CONTROL_EVERY_MS) {
      this.controlAt = now;
      this.controlMap(pos, roster);
    }
  }

  /** Lines through each unit: back line, midfield and front line, left to right across the pitch. */
  private shape(pos: Pos, roster: Roster) {
    for (const side of ["home", "away"] as Side[]) {
      const color = roster.clubs[side].primary;
      for (const unit of ["DF", "MF", "FW"] as const) {
        const pts = [...pos]
          .filter(([id]) => roster.players[id]?.side === side && roster.players[id]?.position === unit)
          .map(([, p]) => p)
          .sort((a, b) => a[1] - b[1]);
        for (let i = 0; i + 1 < pts.length; i++) this.seg(pts[i], pts[i + 1], 0.32, this.mat(color, 0.8));
      }
    }
  }

  /** Lanes from the player on the ball to each team-mate in range: solid when clear, faint when cut out. */
  private passing(pos: Pos, roster: Roster, carrier: string) {
    const me = roster.players[carrier];
    const from = pos.get(carrier);
    if (!me || !from) return;
    const color = roster.clubs[me.side].primary;
    const opponents = [...pos].filter(([id]) => roster.players[id] && roster.players[id].side !== me.side).map(([, p]) => p);
    for (const [id, p] of pos) {
      if (id === carrier || roster.players[id]?.side !== me.side) continue;
      if (Math.hypot(p[0] - from[0], p[1] - from[1]) > PASS_RANGE_M) continue;
      const open = opponents.every((o) => segDist(o, from, p) > OPEN_M);
      this.seg(from, p, open ? 0.3 : 0.14, open ? this.mat(color, 0.85) : this.mat("#f4f4f1", 0.22));
    }
  }

  /** Nearest-in-time map: each patch of grass in the colour of the side that would get there first. */
  private controlMap(pos: Pos, roster: Roster) {
    const home = new THREE.Color(roster.clubs.home.primary);
    const away = new THREE.Color(roster.clubs.away.primary);
    const mix = new THREE.Color();
    const sides = [...pos].filter(([id]) => roster.players[id]).map(([id, p]) => [p[0], p[1], roster.players[id].side === "home" ? 1 : 0]);
    const data = this.controlTex.image.data as Uint8Array;
    for (let r = 0; r < this.rows; r++) {
      // Texture row 0 is the bottom of the plane, which lies at the far touchline once laid flat.
      const y = W - (r + 0.5) * CELL;
      for (let c = 0; c < this.cols; c++) {
        const x = (c + 0.5) * CELL;
        let th = Infinity;
        let ta = Infinity;
        for (const [sx, sy, isHome] of sides) {
          const t = Math.hypot(sx - x, sy - y) / RUN_MS;
          if (isHome) th = Math.min(th, t);
          else ta = Math.min(ta, t);
        }
        const p = 1 / (1 + Math.exp(-(ta - th) / CONTROL_SPREAD_S)); // home's share of this patch
        mix.copy(away).lerp(home, p);
        const o = (r * this.cols + c) * 4;
        const srgb = mix.clone().convertLinearToSRGB();
        data[o] = Math.round(srgb.r * 255);
        data[o + 1] = Math.round(srgb.g * 255);
        data[o + 2] = Math.round(srgb.b * 255);
        data[o + 3] = Math.round((0.1 + 0.32 * Math.abs(2 * p - 1)) * 255);
      }
    }
    this.controlTex.needsUpdate = true;
  }

  dispose() {
    this.segGeo.dispose();
    for (const m of this.mats.values()) m.dispose();
    this.control.geometry.dispose();
    (this.control.material as THREE.Material).dispose();
    this.controlTex.dispose();
  }
}
