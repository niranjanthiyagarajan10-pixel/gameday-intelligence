import * as THREE from "three";
import { arc, disc, disposeTree, flatMat, strip, wx, wz } from "./core";

/** A spot on the pitch in metres, a player id, or "ball". */
export type Spot = { x: number; y: number } | string;

export interface OverlayStyle {
  color?: string; // CSS colour, default the signal colour
  width?: number; // metres
  opacity?: number;
}

interface Overlay {
  obj: THREE.Object3D;
  follow?: string; // player id or "ball" the overlay sticks to
  until?: number; // removed after this time (performance.now())
}

const Y = 0.06;

/**
 * Telestration on the grass: arrows, lines, rings, shaded zones and wedges, in pitch metres. Rings and
 * zones placed on a player or the ball follow them. Every draw returns an id for `remove`.
 */
export class Telestrator {
  readonly group = new THREE.Group();
  private items = new Map<string, Overlay>();
  private seq = 0;

  constructor(
    private signal: string,
    private resolve: (s: Spot) => [number, number] | null,
  ) {}

  private at(s: Spot): [number, number] {
    return this.resolve(s) ?? [52.5, 34];
  }

  private style(s?: OverlayStyle) {
    return { color: s?.color ?? this.signal, width: s?.width ?? 0.45, opacity: s?.opacity ?? 0.9 };
  }

  add(obj: THREE.Object3D, follow?: string, life?: number) {
    const id = `ov${++this.seq}`;
    this.group.add(obj);
    this.items.set(id, { obj, follow, until: life ? performance.now() + life : undefined });
    return id;
  }

  private line(a: [number, number], b: [number, number], s: ReturnType<Telestrator["style"]>, head: boolean) {
    const g = new THREE.Group();
    const mat = flatMat(s.color, s.opacity);
    const [ax, az, bx, bz] = [wx(a[0]), wz(a[1]), wx(b[0]), wz(b[1])];
    const len = Math.hypot(bx - ax, bz - az) || 0.001;
    const ux = (bx - ax) / len;
    const uz = (bz - az) / len;
    const hl = head ? Math.min(len * 0.4, s.width * 5) : 0;
    g.add(strip(ax, az, bx - ux * hl, bz - uz * hl, s.width, mat, Y));
    if (head) {
      const hw = s.width * 2.4;
      const shape = new THREE.Shape([new THREE.Vector2(0, 0), new THREE.Vector2(-hl, hw), new THREE.Vector2(-hl, -hw)]);
      const tri = new THREE.Mesh(new THREE.ShapeGeometry(shape), mat);
      tri.rotation.x = -Math.PI / 2;
      tri.rotation.z = -Math.atan2(bz - az, bx - ax);
      tri.position.set(bx, Y, bz);
      g.add(tri);
    }
    return g;
  }

  arrow(a: Spot, b: Spot, s?: OverlayStyle, life?: number) {
    return this.add(this.line(this.at(a), this.at(b), this.style(s), true), undefined, life);
  }

  lineBetween(a: Spot, b: Spot, s?: OverlayStyle, life?: number) {
    return this.add(this.line(this.at(a), this.at(b), this.style(s), false), undefined, life);
  }

  ring(at: Spot, radius = 2.2, s?: OverlayStyle) {
    const st = this.style(s);
    const c = this.at(at);
    const o = arc(wx(c[0]), wz(c[1]), radius, st.width * 0.6, 0, Math.PI * 2, flatMat(st.color, st.opacity), Y);
    return this.add(o, typeof at === "string" ? at : undefined);
  }

  zone(at: Spot, radius: number, s?: OverlayStyle) {
    const st = this.style(s);
    const c = this.at(at);
    const o = disc(wx(c[0]), wz(c[1]), radius, flatMat(st.color, s?.opacity ?? 0.22), Y - 0.01);
    return this.add(o, typeof at === "string" ? at : undefined);
  }

  /** A shaded triangle, e.g. the shooter's view of the goal between the posts. */
  wedge(apex: Spot, a: Spot, b: Spot, s?: OverlayStyle) {
    const st = this.style(s);
    const [p, q, r] = [this.at(apex), this.at(a), this.at(b)];
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute([wx(p[0]), Y, wz(p[1]), wx(q[0]), Y, wz(q[1]), wx(r[0]), Y, wz(r[1])], 3));
    return this.add(new THREE.Mesh(geo, flatMat(st.color, s?.opacity ?? 0.2)));
  }

  remove(id: string) {
    const o = this.items.get(id);
    if (!o) return;
    this.group.remove(o.obj);
    disposeTree(o.obj);
    this.items.delete(id);
  }

  clear() {
    for (const id of [...this.items.keys()]) this.remove(id);
  }

  update(now: number) {
    for (const [id, o] of this.items) {
      if (o.until !== undefined && now > o.until) {
        this.remove(id);
        continue;
      }
      if (!o.follow) continue;
      const p = this.resolve(o.follow);
      if (p) o.obj.position.set(wx(p[0]), o.obj.position.y, wz(p[1]));
    }
  }
}
