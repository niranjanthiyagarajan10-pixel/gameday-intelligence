import * as THREE from "three";
import type { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { HEAD_Y, L, clamp, ease } from "./core";
import type { Figure } from "./figures";

export type Preset = "broadcast" | "goal" | "tactical" | "follow" | "player" | "eye" | "auto";

export const PRESET_LABEL: Record<Preset, string> = {
  broadcast: "Broadcast",
  goal: "Behind goal",
  tactical: "Tactical",
  follow: "Follow ball",
  player: "Player cam",
  eye: "Eye line",
  auto: "Director",
};

/** What the camera needs to know about the match this frame, in world units. */
export interface CamContext {
  ball: THREE.Vector3; // y is the ball's height
  focus: Figure | null;
}

interface Flight {
  p0: THREE.Vector3;
  t0: THREE.Vector3;
  p1: THREE.Vector3;
  t1: THREE.Vector3;
  start: number;
  dur: number;
}

/** A rig either tracks a moving point at a kept offset (the viewer can orbit it), or sets an exact pose. */
type Rig = { target: THREE.Vector3; offset: THREE.Vector3 } | { pos: THREE.Vector3; look: THREE.Vector3; k: number; kLook: number };

type Shot = "wide" | "attack" | "end";

const FLY_MS = 1100;
const GOAL_HOLD_MS = 4200;
const CUT_HOLD_MS = 4000;
const END_HOLD_MS = 3500;
const FINAL_THIRD_X = 24; // world X beyond which the director treats play as an attack

const v3 = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

/**
 * Decides where the camera is each frame. Presets ease between each other; tracking presets follow
 * the ball or a player while keeping whatever angle the viewer orbits to; Player cam and Eye line set
 * the pose outright; the Director cuts between angles like a broadcast. A goal briefly takes over
 * with a view from behind the net, and a scripted replay can take over for as long as it runs.
 */
export class Director {
  mode: Preset = "broadcast";
  private fly: Flight | null = null;
  private goalEnd = -1; // which end the Behind goal preset uses, -1 for the left goal
  private hold: { kind: "goal" | "script"; until: number } | null = null;
  private shot: Shot = "wide";
  private shotSince = 0;
  private shotEnd = 1;
  private yaw = 0;

  constructor(
    private camera: THREE.PerspectiveCamera,
    private controls: OrbitControls,
    private still: boolean,
  ) {}

  /** Exact pose modes drive the camera directly; orbit controls stay out of their way. */
  get manual() {
    return !this.hold && (this.mode === "player" || this.mode === "eye");
  }

  private flyTo(pos: THREE.Vector3, target: THREE.Vector3, now: number, dur = FLY_MS) {
    this.fly = {
      p0: this.camera.position.clone(),
      t0: this.controls.target.clone(),
      p1: pos.clone(),
      t1: target.clone(),
      start: now,
      dur: this.still ? 1 : Math.max(1, dur),
    };
  }

  private cut(rig: Rig) {
    this.fly = null;
    if ("offset" in rig) {
      this.controls.target.copy(rig.target);
      this.camera.position.copy(rig.target).add(rig.offset);
    } else {
      this.controls.target.copy(rig.look);
      this.camera.position.copy(rig.pos);
    }
  }

  setMode(mode: Preset, now: number, ctx: CamContext) {
    this.mode = mode;
    this.hold = null;
    if (mode === "goal") this.goalEnd = ctx.ball.x >= 0 ? 1 : -1;
    if (mode === "auto") {
      this.shot = Math.abs(ctx.ball.x) > FINAL_THIRD_X ? "attack" : "wide";
      this.shotSince = now;
    }
    const rig = this.rig(ctx);
    if ("offset" in rig) this.flyTo(rig.target.clone().add(rig.offset), rig.target, now);
    else this.flyTo(rig.pos, rig.look, now);
  }

  /** The viewer started dragging: stop any flight so the controls never fight it. */
  userStart() {
    this.fly = null;
  }

  /** A goal: look back at the pitch through the net it went into, then return to the chosen view. */
  goal(end: number, now: number) {
    if (this.hold?.kind === "script") return;
    this.hold = { kind: "goal", until: now + GOAL_HOLD_MS };
    const gx = end * (L / 2);
    this.flyTo(v3(gx + end * 6.5, 3.4, 2.2), v3(gx - end * 12, 1.2, 0), now, 700);
  }

  /** A shot: the Director cuts to the end it was aimed at. */
  shotAt(end: number, now: number) {
    if (this.mode !== "auto" || this.hold) return;
    this.shot = "end";
    this.shotEnd = end;
    this.shotSince = now;
    this.cut(this.rig(null));
  }

  /** Scripted camera for a replay: fly to an exact pose and stay there until released. */
  script(pos: THREE.Vector3, target: THREE.Vector3, now: number, dur = 900) {
    this.hold = { kind: "script", until: Infinity };
    this.flyTo(pos, target, now, dur);
  }

  release(now: number, ctx: CamContext) {
    this.hold = null;
    this.setMode(this.mode, now, ctx);
  }

  private rig(ctx: CamContext | null): Rig {
    const ball = ctx?.ball ?? this.controls.target;
    const at = (x: number, z: number) => v3(x, 0, z);
    switch (this.mode === "auto" ? this.autoShot() : this.mode) {
      case "goal":
        return { target: at(this.goalEnd * (L / 2 - 22), ball.z * 0.4), offset: v3(this.goalEnd * 40, 12, 0) };
      case "end":
        return { target: at(this.shotEnd * (L / 2 - 20), ball.z * 0.4), offset: v3(this.shotEnd * 34, 9, 0) };
      case "tactical":
        return { target: at(0, 0), offset: v3(0, 112, 0.1) };
      case "follow":
        return { target: at(ball.x, ball.z), offset: v3(0, 13, 20) };
      case "attack": {
        const side = ball.x >= 0 ? 1 : -1;
        return { target: at(ball.x, ball.z), offset: v3(-side * 8, 9, 19) };
      }
      case "player":
      case "eye": {
        const f = ctx?.focus;
        if (!f) return { target: at(ball.x, ball.z), offset: v3(0, 13, 20) };
        const p = f.group.position;
        const fwd = v3(Math.cos(this.yaw), 0, -Math.sin(this.yaw));
        if (this.mode === "eye") {
          const eye = p.clone().add(fwd.clone().multiplyScalar(0.5)).setY(HEAD_Y + 0.15);
          return { pos: eye, look: ball.clone(), k: 0.3, kLook: 0.12 };
        }
        return { pos: p.clone().addScaledVector(fwd, -12).setY(7), look: p.clone().addScaledVector(fwd, 8).setY(1), k: 0.06, kLook: 0.08 };
      }
      default:
        // Broadcast: high in the main stand, panning with play along the touchline.
        return { target: at(clamp(ball.x, -30, 30), clamp(ball.z * 0.35, -8, 8)), offset: v3(0, 20, 42) };
    }
  }

  private autoShot(): "wide" | "attack" | "end" | "broadcast" {
    return this.shot === "wide" ? "broadcast" : this.shot;
  }

  update(now: number, ctx: CamContext) {
    if (this.hold?.kind === "goal" && now > this.hold.until) {
      this.hold = null;
      this.setMode(this.mode, now, ctx);
    }
    if (ctx.focus) {
      // Smooth the focused player's facing so Player cam does not swing with every step.
      let d = ctx.focus.group.rotation.y - this.yaw;
      d = ((((d + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)) - Math.PI;
      this.yaw += d * 0.04;
    }
    if (this.mode === "auto" && !this.hold) {
      const want: Shot = Math.abs(ctx.ball.x) > FINAL_THIRD_X ? "attack" : "wide";
      const holdFor = this.shot === "end" ? END_HOLD_MS : CUT_HOLD_MS;
      if (want !== this.shot && now - this.shotSince > holdFor) {
        this.shot = want;
        this.shotSince = now;
        this.cut(this.rig(ctx));
      }
    }

    const rig = this.hold ? null : this.rig(ctx);
    const fl = this.fly;
    if (fl) {
      if (rig && "offset" in rig) {
        fl.t1.copy(rig.target);
        fl.p1.copy(rig.target).add(rig.offset);
      } else if (rig) {
        fl.t1.copy(rig.look);
        fl.p1.copy(rig.pos);
      }
      const k = ease(Math.min(1, (now - fl.start) / fl.dur));
      this.camera.position.lerpVectors(fl.p0, fl.p1, k);
      this.controls.target.lerpVectors(fl.t0, fl.t1, k);
      if (k >= 1) this.fly = null;
    } else if (rig && "offset" in rig) {
      // Track the moving point and keep the viewer's own angle and zoom.
      const step = rig.target.clone().sub(this.controls.target).multiplyScalar(0.08);
      this.controls.target.add(step);
      this.camera.position.add(step);
    } else if (rig) {
      this.camera.position.lerp(rig.pos, rig.k);
      this.controls.target.lerp(rig.look, rig.kLook);
    }
    const driven = this.manual || this.hold !== null;
    this.controls.enabled = !driven; // drags here would pile up and jump the view on release
    if (driven) {
      this.camera.lookAt(this.controls.target);
    } else {
      this.controls.update();
    }
  }
}
