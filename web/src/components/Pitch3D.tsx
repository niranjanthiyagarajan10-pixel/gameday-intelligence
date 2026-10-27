import { Component, createElement, forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import type { CSSProperties, ReactNode } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Frame, FxEvent, Roster } from "../types";
import { webglAvailable } from "../webgl";
import { Pitch } from "./Pitch";
import { Crest } from "./Crest";
import { clock } from "../format";
import { BALL_R, HEAD_Y, L, cssColor, disc, disposeTree, flatMat, hash, wx, wz } from "../pitch3d/core";
import { buildPitch } from "../pitch3d/pitch";
import { FigureKit, animate, dive, lunge, patternFor, react, type Figure } from "../pitch3d/figures";
import { BallTrail, FlightPaths, footballTexture } from "../pitch3d/ball";
import { buildStadium } from "../pitch3d/stadium";
import { TacticalLayers, type Layer } from "../pitch3d/layers";
import { Director, PRESET_LABEL, type CamContext, type Preset } from "../pitch3d/camera";
import { Telestrator, type OverlayStyle, type Spot } from "../pitch3d/overlays";
import { buildScript, type Beat, type Caption, type ExplainRequest, type Script } from "../pitch3d/explain";

/**
 * Interactive 3D pitch for the Live tab. Same props as the 2D Pitch, plus `onSelect` for click to
 * focus and `explain` for the telestrated replay of a shot. If WebGL is missing or the scene throws,
 * the 2D Pitch renders instead.
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
  explain?: ExplainRequest | null;
  onExplainEnd?: () => void;
  score?: [number, number]; // for the score bug
  clock?: number; // match seconds, for the score bug
}

export type { Preset, Spot, OverlayStyle, ExplainRequest };

/** Imperative API for telestration. Draw calls return an id for removeOverlay. */
export interface Pitch3DApi {
  /** Fly to look at a spot and hold there until setPreset is called. */
  flyTo(target: Spot, duration?: number, opts?: { distance?: number; height?: number }): void;
  setPreset(p: Preset): void;
  drawArrow(a: Spot, b: Spot, style?: OverlayStyle): string;
  drawLine(a: Spot, b: Spot, style?: OverlayStyle): string;
  drawRing(at: Spot, radius?: number, style?: OverlayStyle): string;
  drawZone(at: Spot, radius: number, style?: OverlayStyle): string;
  drawWedge(apex: Spot, a: Spot, b: Spot, style?: OverlayStyle): string;
  removeOverlay(id: string): void;
  clearOverlays(): void;
  explain(req: ExplainRequest): void;
  stopExplain(): void;
}

const PRESET_KEY = "gdi.pitch3d.preset";
const LAYER_KEY = "gdi.pitch3d.layers";
const LAYER_LABEL: Record<Layer, string> = { shape: "Shape", passing: "Passing", control: "Control" };
const CARRIER_M = 2.0;
const REPLAY_HOLD_MS = 1600; // the last caption stays up this long after the clip ends
const LOWER_MS = 3800;
const CARD_COLOR = { yellow: "#f5c518", red: "#ff4d4d" } as const;

/**
 * A club's crest as SVG markup, rendered from the same Crest component the rest of the app uses.
 * Runs from the animation loop, outside React's own rendering, so flushSync is safe here.
 */
function crestMarkup(club: Roster["clubs"]["home"]): string {
  const div = document.createElement("div");
  const root = createRoot(div);
  try {
    flushSync(() => root.render(createElement(Crest, { club, size: 80 })));
    return div.innerHTML;
  } finally {
    root.unmount();
  }
}

interface Lower {
  key: number;
  kind: string;
  title: string;
  sub: string;
  color: string;
}

function readPreset(): Preset {
  try {
    const v = localStorage.getItem(PRESET_KEY);
    return v && v in PRESET_LABEL ? (v as Preset) : "broadcast";
  } catch {
    return "broadcast";
  }
}

function readLayers(): Set<Layer> {
  try {
    const v = JSON.parse(localStorage.getItem(LAYER_KEY) ?? "[]");
    return new Set(Array.isArray(v) ? v.filter((l): l is Layer => l in LAYER_LABEL) : []);
  } catch {
    return new Set();
  }
}

function save(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the choice lasts for this visit only */
  }
}

/** What the mounted scene exposes to React. */
interface Engine {
  frame(f: Frame): void;
  preset(p: Preset): void;
  layers(on: Set<Layer>): void;
  explain(req: ExplainRequest): void;
  stopExplain(): void;
  api: Omit<Pitch3DApi, "setPreset" | "explain" | "stopExplain">;
}

type Positions = Map<string, number[]>; // pitch metres: players x, y, speed; ball x, y, z

interface Replay {
  req: ExplainRequest;
  script: Script;
  t: number;
  rate: number;
  beat: number;
  cursor: number;
  last: number;
  endedAt: number;
  netDone: boolean;
}

const Scene = forwardRef<Pitch3DApi, Pitch3DProps & { onFail: () => void }>(function Scene(props, ref) {
  const host = useRef<HTMLDivElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const tagLayer = useRef<HTMLDivElement>(null);
  const engine = useRef<Engine | null>(null);
  const live = useRef(props);
  live.current = props;
  const [preset, setPreset] = useState<Preset>(readPreset);
  const [layers, setLayers] = useState<Set<Layer>>(readLayers);
  const [caption, setCaption] = useState<Caption | null>(null);
  const [replaying, setReplaying] = useState(false);
  const [wipe, setWipe] = useState<{ key: number; color: string } | null>(null);
  const [lower, setLower] = useState<Lower | null>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    } catch {
      live.current.onFail();
      return;
    }
    const failed = { v: false };
    const fail = () => {
      if (failed.v) return;
      failed.v = true;
      live.current.onFail();
    };
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.setClearColor(0x000000, 1);
    el.appendChild(renderer.domElement);
    const cv = renderer.domElement;
    cv.addEventListener("webglcontextlost", fail);

    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x000000, 150, 280);
    const camera = new THREE.PerspectiveCamera(38, 1, 0.3, 700);
    camera.position.set(0, 20, 42);

    scene.add(new THREE.HemisphereLight(0xffffff, 0x1a2a1e, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-30, 70, 40);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.radius = 4;
    sun.shadow.bias = -0.0005;
    Object.assign(sun.shadow.camera, { left: -65, right: 65, top: 45, bottom: -45, near: 10, far: 200 });
    scene.add(sun);
    const pitch = buildPitch();
    scene.add(pitch.group);
    const clubsKey = (r: Roster) => r.clubs.home.id + r.clubs.away.id;
    let stadium = buildStadium(live.current.roster);
    let stadiumFor = clubsKey(live.current.roster);
    scene.add(stadium);

    const controls = new OrbitControls(camera, cv);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 10;
    controls.maxDistance = 130;
    controls.maxPolarAngle = Math.PI / 2 - 0.05; // never below the grass
    const director = new Director(camera, controls, still);
    director.onWipe = (end) => {
      const r = live.current.roster;
      setWipe({ key: performance.now(), color: r.clubs[end > 0 ? "home" : "away"].primary });
    };
    let lowerTimer = 0;
    const showLower = (l: Omit<Lower, "key">) => {
      window.clearTimeout(lowerTimer);
      setLower({ ...l, key: performance.now() });
      lowerTimer = window.setTimeout(() => setLower(null), LOWER_MS);
    };
    /** After a goal: the scorer celebrates, team-mates near them cheer, the beaten keeper and defence slump. */
    const celebrate = (scorerId: string | null, team: "home" | "away", end: number, now: number) => {
      const roster = live.current.roster;
      const scorer = scorerId ? figures.get(scorerId) : undefined;
      for (const f of figures.values()) {
        const info = roster.players[f.id];
        if (!info) continue;
        if (f === scorer) react(f, now, "celebrate", 250);
        else if (info.side === team) {
          if (!scorer || f.group.position.distanceTo(scorer.group.position) < 35) react(f, now, "cheer", 350 + (hash(f.id) % 500));
        } else if (f.keeper || Math.abs(f.group.position.x - (end * L) / 2) < 25) react(f, now, "slump", 300 + (hash(f.id) % 300));
      }
    };

    const signal = cssColor("--signal", "#e8ff3a");
    const kit = new FigureKit();
    const figures = new Map<string, Figure>();
    const players = new THREE.Group();
    scene.add(players);
    const ringGeo = new THREE.RingGeometry(2.2, 2.55, 48);
    const tagGeo = new THREE.RingGeometry(1.95, 2.12, 48);
    const ringMat = flatMat(signal, 0.95);
    const tagMat = flatMat(signal, 0.6);
    const rings = new Map<string, THREE.Mesh>();

    const ball = new THREE.Mesh(new THREE.SphereGeometry(BALL_R, 24, 16), new THREE.MeshLambertMaterial({ map: footballTexture() }));
    ball.castShadow = true;
    ball.visible = false;
    scene.add(ball);
    const ballShadow = disc(0, 0, BALL_R * 1.5, flatMat(0x000000, 0.45), 0.03);
    ballShadow.visible = false;
    scene.add(ballShadow);
    const trail = new BallTrail();
    scene.add(trail.mesh);
    const flights = new FlightPaths();
    scene.add(flights.group);
    const tactics = new TacticalLayers();
    scene.add(tactics.group);

    // Glide between frames, the same way the 2D pitch does.
    let from: Positions = new Map();
    let to: Positions = new Map();
    const drawn: Positions = new Map();
    let glideStart = 0;
    let gap = 200;
    let last = 0;
    let latest: Frame | null = null;
    const toPositions = (f: { ball: number[]; players: [string, number, number, number][] }) => {
      const m: Positions = new Map(f.players.map((p) => [p[0], [p[1], p[2], p[3]]]));
      m.set("ball", [f.ball[0], f.ball[1], f.ball[2] ?? 0]);
      return m;
    };
    const glideTo = (next: Positions, now: number) => {
      from = new Map(drawn);
      to = next;
      glideStart = now;
    };

    const resolve = (s: Spot): [number, number] | null => {
      if (typeof s !== "string") return [s.x, s.y];
      const p = drawn.get(s) ?? to.get(s);
      return p ? [p[0], p[1]] : null;
    };
    const tele = new Telestrator(signal, resolve);
    scene.add(tele.group);

    const ctx: CamContext = { ball: new THREE.Vector3(), focus: null };

    /** Bulge a net at the ball, or at the middle of the goal if the ball is not there yet. */
    const goalAt = (end: number, now: number) => {
      const near = Math.abs(ball.position.x) > L / 2 - 2;
      const z = near ? ball.position.z : 0;
      const y = near ? ball.position.y : 1.2;
      // The right goal is turned round, so its own z runs the other way.
      if (end > 0) pitch.nets[1].bulge(-z, y, now);
      else pitch.nets[0].bulge(z, y, now);
    };

    // Explain this moment: plays a shot's clip with telestration, then hands back to live.
    let replay: Replay | null = null;
    const frameAt = (r: Replay, t: number): Positions => {
      const fr = r.req.clip.frames;
      while (r.cursor < fr.length - 2 && fr[r.cursor + 1].t <= t) r.cursor++;
      const a = fr[r.cursor];
      const b = fr[Math.min(r.cursor + 1, fr.length - 1)];
      const u = b.t > a.t ? Math.min(1, Math.max(0, (t - a.t) / (b.t - a.t))) : 0;
      const pa = toPositions(a);
      const pb = toPositions(b);
      for (const [id, va] of pa) {
        const vb = pb.get(id);
        if (vb) pa.set(id, va.map((x, k) => x + ((vb[k] ?? x) - x) * u));
      }
      return pa;
    };
    const applyBeat = (r: Replay, beat: Beat, now: number) => {
      if (beat.caption) setCaption(beat.caption);
      if (beat.rate) r.rate = beat.rate;
      for (const d of beat.draw ?? []) {
        if (d.type === "arrow") tele.arrow(d.a, d.b, { color: d.color, width: d.width, opacity: d.opacity });
        else if (d.type === "line") tele.lineBetween(d.a, d.b, { color: d.color, width: d.width, opacity: d.opacity });
        else if (d.type === "ring") tele.ring(d.at, d.radius, { color: d.color, width: 0.5 });
        else tele.wedge(d.apex, d.a, d.b, { color: d.color, opacity: 0.18 });
      }
      const shooter = drawn.get(r.req.shot.player);
      if (beat.cam === "shooter" && shooter) {
        // Low, just behind the shooter, looking down the line of the shot at the goal.
        const s = new THREE.Vector3(wx(shooter[0]), 0, wz(shooter[1]));
        const goal = new THREE.Vector3((r.script.goalEnd * L) / 2, 0, 0);
        const dir = goal.clone().sub(s).setY(0).normalize();
        const side = new THREE.Vector3(-dir.z, 0, dir.x).multiplyScalar(5);
        const pos = s.clone().addScaledVector(dir, -18).add(side).setY(10);
        const look = s.clone().lerp(goal, 0.45).setY(0.5);
        director.script(pos, look, now, 900);
      }
      if (beat.strike) flights.shot(live.current.roster.clubs[r.req.shot.team].primary, ball.position, now);
    };
    const startReplay = (req: ExplainRequest) => {
      const now = performance.now();
      const script = buildScript(req, live.current.roster, signal);
      if (!script) {
        live.current.onExplainEnd?.();
        return;
      }
      tele.clear();
      flights.clear();
      trail.reset();
      const r: Replay = { req, script, t: script.start, rate: 1, beat: 0, cursor: 0, last: now, endedAt: 0, netDone: false };
      replay = r;
      glideTo(frameAt(r, r.t), now);
      setCaption(null);
      setReplaying(true);
    };
    const endReplay = () => {
      if (!replay) return;
      replay = null;
      const now = performance.now();
      tele.clear();
      flights.clear();
      trail.reset();
      setCaption(null);
      setReplaying(false);
      director.release(now, ctx);
      if (latest) glideTo(toPositions(latest), now);
      live.current.onExplainEnd?.();
    };
    const advanceReplay = (r: Replay, now: number) => {
      const dt = Math.min(0.1, (now - r.last) / 1000);
      r.last = now;
      if (!r.endedAt) r.t = Math.min(r.script.end, r.t + dt * r.rate);
      while (r.beat < r.script.beats.length && r.script.beats[r.beat].t <= r.t) applyBeat(r, r.script.beats[r.beat++], now);
      if (r.t >= r.script.end && !r.endedAt) r.endedAt = now;
      if (r.endedAt && now - r.endedAt > REPLAY_HOLD_MS) {
        endReplay();
        return;
      }
      const m = frameAt(r, r.t);
      from = m;
      to = m;
    };

    // Short-lived pass lines, shot flights, reactions and goals from the live event feed.
    const seen = new Set<string>();
    const syncFx = (now: number) => {
      const { fx, roster } = live.current;
      for (const e of fx) {
        if (seen.has(e.id)) continue;
        seen.add(e.id);
        if (now - e.at > 1500) continue;
        const end = e.team === "home" ? 1 : -1; // home always attacks toward x = 105
        const color = roster.clubs[e.team].primary;
        if (e.type === "pass" && e.end_x !== null && e.end_y !== null) {
          const ok = e.outcome === "complete";
          tele.lineBetween({ x: e.x, y: e.y }, { x: e.end_x, y: e.end_y }, { color: ok ? color : "#ffffff", width: 0.18, opacity: 0.65 }, 1200);
        } else if (e.type === "shot") {
          flights.shot(color, ball.position, now);
          director.shotAt(end, now);
          if (e.end_x !== null && e.end_y !== null && Math.abs(e.end_y - 34) < 7.5) {
            for (const f of figures.values()) {
              const info = roster.players[f.id];
              if (!f.keeper || !info || info.side === e.team) continue;
              if (Math.abs(f.group.position.x - (end * L) / 2) > 20) continue;
              dive(f, now, [wx(e.x), wz(e.y)], [wx(e.end_x), wz(e.end_y)]);
            }
          }
        } else if ((e.type === "tackle" || e.type === "interception") && e.player) {
          const f = figures.get(e.player);
          if (f) lunge(f, now, e.type === "tackle" ? 1 : 0.6);
        } else if (e.type === "goal") {
          goalAt(end, now);
          director.goal(end, now);
          celebrate(e.player, e.team, end, now);
        } else if (e.type === "card" && e.player) {
          const info = roster.players[e.player];
          if (info) {
            const red = e.outcome === "red";
            showLower({
              kind: red ? "Red card" : "Yellow card",
              title: `#${info.number} ${info.name}`,
              sub: `${roster.clubs[e.team].name} ${Math.floor(e.t / 60)}\u2032`,
              color: red ? CARD_COLOR.red : CARD_COLOR.yellow,
            });
          }
        }
      }
      if (seen.size > 4000) seen.clear();
    };

    const syncFigures = () => {
      const { roster, focus, tagged } = live.current;
      for (const id of to.keys()) {
        if (id === "ball" || figures.has(id)) continue;
        const info = roster.players[id];
        if (!info) continue;
        const club = roster.clubs[info.side];
        try {
          kit.setCrest(club.id, crestMarkup(club));
        } catch {
          /* no crest on the shirt; everything else still draws */
        }
        // Keepers wear a dark kit trimmed in the club colour, as on the 2D pitch.
        const f =
          info.position === "GK"
            ? kit.make(id, true, { club: club.id, shirt: "#16181b", trim: club.primary, shorts: "#16181b", socks: "#16181b", number: info.number, pattern: "plain" })
            : kit.make(id, false, {
                club: club.id, shirt: club.primary, trim: club.secondary, shorts: club.secondary, socks: club.primary, number: info.number, pattern: patternFor(club.id),
              });
        const p = to.get(id)!;
        f.group.position.set(wx(p[0]), 0, wz(p[1]));
        figures.set(id, f);
        players.add(f.group);
      }
      for (const [id, f] of figures) {
        if (!to.has(id)) {
          players.remove(f.group);
          figures.delete(id);
          kit.release(id);
        }
      }
      for (const [id, f] of figures) {
        const want = replay ? null : id === focus ? ringGeo : tagged.has(id) ? tagGeo : null;
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

    // Name tags: small HTML labels pinned above the heads of the players that matter right now.
    const tags = new Map<string, HTMLDivElement>();
    const proj = new THREE.Vector3();
    const syncTags = () => {
      const layer = tagLayer.current;
      if (!layer) return;
      const { roster, focus, tagged, labels = {} } = live.current;
      const want = new Map<string, string>();
      const text = (id: string) => {
        const info = roster.players[id];
        return info ? `#${info.number} ${info.short.toUpperCase()}` : id;
      };
      if (replay) {
        for (const id of replay.script.tags) want.set(id, text(id));
      } else {
        for (const id of tagged) want.set(id, labels[id] ? `${text(id)}  ${labels[id].toUpperCase()}` : text(id));
        const me = focus ? drawn.get(focus) : undefined;
        if (focus && me && director.mode !== "eye") want.set(focus, `${text(focus)}  ${((me[2] ?? 0) * 3.6).toFixed(1)} KM/H`);
      }
      const w = layer.clientWidth;
      const h = layer.clientHeight;
      for (const [id, label] of want) {
        const f = figures.get(id);
        const info = roster.players[id];
        if (!f || !info) continue;
        let tag = tags.get(id);
        if (!tag) {
          tag = document.createElement("div");
          tag.className = "p3-tag";
          tag.style.setProperty("--club", roster.clubs[info.side].primary);
          layer.appendChild(tag);
          tags.set(id, tag);
        }
        if (tag.textContent !== label) tag.textContent = label;
        tag.classList.toggle("focus", id === focus && !replay);
        proj.copy(f.group.position).setY(HEAD_Y + 0.6).project(camera);
        const off = proj.z > 1 || Math.abs(proj.x) > 1.1 || Math.abs(proj.y) > 1.1;
        tag.style.display = off ? "none" : "block";
        tag.style.transform = `translate(${(((proj.x + 1) / 2) * w).toFixed(1)}px, ${(((1 - proj.y) / 2) * h).toFixed(1)}px) translate(-50%, -100%)`;
      }
      for (const [id, tag] of tags) {
        if (want.has(id) && figures.has(id)) continue;
        tag.remove();
        tags.delete(id);
      }
    };

    const rollAxis = new THREE.Vector3();
    const tick = () => {
      if (failed.v) return;
      try {
        const now = performance.now();
        const { roster, focus } = live.current;
        if (clubsKey(roster) !== stadiumFor) {
          scene.remove(stadium);
          disposeTree(stadium);
          stadium = buildStadium(roster);
          stadiumFor = clubsKey(roster);
          scene.add(stadium);
        }
        if (replay) advanceReplay(replay, now);
        const a = still || replay ? 1 : Math.min(1, (now - glideStart) / gap);

        // The player on the ball, from where things were drawn last frame.
        const b0 = drawn.get("ball");
        let carrier: string | null = null;
        if (b0 && (b0[2] ?? 0) < 1.5) {
          let best = CARRIER_M;
          for (const [id, p] of drawn) {
            if (id === "ball") continue;
            const d = Math.hypot(p[0] - b0[0], p[1] - b0[1]);
            if (d < best) {
              best = d;
              carrier = id;
            }
          }
        }

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
          let dist = 0;
          let turn = 0;
          if (prev) {
            dist = Math.hypot(v[0] - prev[0], v[1] - prev[1]);
            if (dist > 1e-3) {
              // Ease into turns rather than snapping round; the body banks with the turn.
              const want = Math.atan2(-(v[1] - prev[1]), v[0] - prev[0]);
              let d = want - fig.group.rotation.y;
              d = ((((d + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)) - Math.PI;
              turn = d * 0.12;
              fig.group.rotation.y += turn;
            }
          }
          fig.group.position.set(wx(v[0]), 0, wz(v[1]));
          animate(fig, now, dist, v[2] ?? 0, id === carrier, turn);
        }
        syncFigures();
        if (!replay) syncFx(now);
        else if (!replay.netDone && replay.req.shot.outcome === "goal" && Math.abs(ball.position.x) > L / 2 + 0.3 && Math.abs(ball.position.z) < 3.8) {
          replay.netDone = true;
          goalAt(replay.script.goalEnd, now);
          celebrate(replay.req.shot.player, replay.req.shot.team, replay.script.goalEnd, now);
        }
        tele.update(now);
        pitch.nets[0].update(now);
        pitch.nets[1].update(now);
        trail.update(ball.position, now);
        flights.update(ball.position, ball.position.y - BALL_R, now);
        tactics.update(now, drawn, roster, carrier);

        ctx.ball.copy(ball.position).setY(ball.position.y - BALL_R);
        ctx.focus = focus ? figures.get(focus) ?? null : null;
        const eye = director.mode === "eye" && !replay ? focus : null;
        for (const [id, f] of figures) f.group.visible = id !== eye;
        director.update(now, ctx);
        syncTags();
        renderer.render(scene, camera);
      } catch {
        fail();
      }
    };

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

    // Hover shows the player; a click without a drag focuses them.
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const pick = (ev: PointerEvent): string | null => {
      const r = cv.getBoundingClientRect();
      ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hits = ray.intersectObjects([...figures.values()].filter((f) => f.group.visible).map((f) => f.hit), false);
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
      cv.style.cursor = info ? "pointer" : "grab";
      if (!info) {
        t.style.display = "none";
        return;
      }
      const r = el.getBoundingClientRect();
      t.textContent = `#${info.number} ${info.name}`;
      t.style.display = "block";
      t.style.left = `${Math.max(0, Math.min(ev.clientX - r.left + 12, r.width - 200))}px`;
      t.style.top = `${ev.clientY - r.top - 30}px`;
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
    const onStart = () => director.userStart();
    controls.addEventListener("start", onStart);
    cv.addEventListener("pointermove", onMove);
    cv.addEventListener("pointerdown", onDown);
    cv.addEventListener("pointerup", onUp);
    cv.addEventListener("pointerleave", onLeave);

    engine.current = {
      frame(f) {
        const now = performance.now();
        latest = f;
        if (replay) return;
        if (last) gap = Math.min(500, Math.max(60, 0.7 * gap + 0.3 * (now - last)));
        last = now;
        glideTo(toPositions(f), now);
      },
      preset(p) {
        director.setMode(p, performance.now(), ctx);
      },
      layers(on) {
        tactics.on = new Set(on);
      },
      explain: startReplay,
      stopExplain: endReplay,
      api: {
        flyTo(target, duration = 1200, opts = {}) {
          const c = resolve(target) ?? [L / 2, 34];
          const t1 = new THREE.Vector3(wx(c[0]), 0, wz(c[1]));
          const dir = camera.position.clone().sub(controls.target).setY(0);
          if (dir.lengthSq() < 1e-3) dir.set(0, 0, 1);
          dir.normalize().multiplyScalar(opts.distance ?? 26);
          director.script(t1.clone().add(dir).setY(opts.height ?? 16), t1, performance.now(), duration);
        },
        drawArrow: (a, b, s) => tele.arrow(a, b, s),
        drawLine: (a, b, s) => tele.lineBetween(a, b, s),
        drawRing: (at, radius, s) => tele.ring(at, radius, s),
        drawZone: (at, radius, s) => tele.zone(at, radius, s),
        drawWedge: (apex, a, b, s) => tele.wedge(apex, a, b, s),
        removeOverlay: (id) => tele.remove(id),
        clearOverlays: () => tele.clear(),
      },
    };
    if (live.current.frame) engine.current.frame(live.current.frame);
    // Start on the chosen view at once rather than flying in from the default pose.
    const startBall = to.get("ball");
    if (startBall) ctx.ball.set(wx(startBall[0]), 0, wz(startBall[1]));
    director.setMode(readPreset(), performance.now() - 5000, ctx);
    renderer.setAnimationLoop(tick);

    return () => {
      window.clearTimeout(lowerTimer);
      renderer.setAnimationLoop(null);
      ro.disconnect();
      controls.removeEventListener("start", onStart);
      controls.dispose();
      cv.removeEventListener("pointermove", onMove);
      cv.removeEventListener("pointerdown", onDown);
      cv.removeEventListener("pointerup", onUp);
      cv.removeEventListener("pointerleave", onLeave);
      cv.removeEventListener("webglcontextlost", fail);
      for (const t of tags.values()) t.remove();
      engine.current = null;
      flights.clear();
      tele.clear();
      disposeTree(scene);
      for (const g of [ringGeo, tagGeo]) g.dispose();
      for (const m of [ringMat, tagMat]) m.dispose();
      kit.dispose();
      tactics.dispose();
      renderer.dispose();
      cv.remove();
    };
  }, []);

  useEffect(() => {
    if (props.frame) engine.current?.frame(props.frame);
  }, [props.frame]);

  const firstPreset = useRef(true);
  useEffect(() => {
    save(PRESET_KEY, preset);
    // The scene already starts on the saved preset; only later changes fly the camera.
    if (firstPreset.current) firstPreset.current = false;
    else engine.current?.preset(preset);
  }, [preset]);

  useEffect(() => {
    save(LAYER_KEY, JSON.stringify([...layers]));
    engine.current?.layers(layers);
  }, [layers]);

  const explainKey = props.explain?.key;
  useEffect(() => {
    if (live.current.explain) engine.current?.explain(live.current.explain);
  }, [explainKey]);

  useImperativeHandle(ref, () => ({
    flyTo: (...a) => engine.current?.api.flyTo(...a),
    setPreset: (p) => setPreset(p),
    drawArrow: (...a) => engine.current?.api.drawArrow(...a) ?? "",
    drawLine: (...a) => engine.current?.api.drawLine(...a) ?? "",
    drawRing: (...a) => engine.current?.api.drawRing(...a) ?? "",
    drawZone: (...a) => engine.current?.api.drawZone(...a) ?? "",
    drawWedge: (...a) => engine.current?.api.drawWedge(...a) ?? "",
    removeOverlay: (id) => engine.current?.api.removeOverlay(id),
    clearOverlays: () => engine.current?.api.clearOverlays(),
    explain: (req) => engine.current?.explain(req),
    stopExplain: () => engine.current?.stopExplain(),
  }));

  const toggle = (l: Layer) =>
    setLayers((prev) => {
      const next = new Set(prev);
      if (next.has(l)) next.delete(l);
      else next.add(l);
      return next;
    });

  return (
    <div className="pitch3d">
      <div ref={host} className="p3-canvas" />
      <div ref={tagLayer} className="p3-tags" />
      <div ref={tip} className="p3-tip" />
      <div className="p3-controls">
        <div className="p3-group" role="group" aria-label="Camera">
          {(Object.keys(PRESET_LABEL) as Preset[]).map((p) => (
            <button key={p} className={p === preset ? "on" : ""} aria-pressed={p === preset} onClick={() => setPreset(p)}>
              {PRESET_LABEL[p]}
            </button>
          ))}
        </div>
        <div className="p3-group" role="group" aria-label="Layers">
          <span className="p3-glabel">Layers</span>
          {(Object.keys(LAYER_LABEL) as Layer[]).map((l) => (
            <button key={l} className={layers.has(l) ? "on" : ""} aria-pressed={layers.has(l)} onClick={() => toggle(l)}>
              {LAYER_LABEL[l]}
            </button>
          ))}
        </div>
      </div>
      {props.score && (
        <div className="p3-bug" aria-label="Score">
          <span className="t" style={{ "--club": props.roster.clubs.home.primary } as CSSProperties}>{props.roster.clubs.home.short}</span>
          <b className="num">{props.score[0]}</b>
          <b className="num">{props.score[1]}</b>
          <span className="t" style={{ "--club": props.roster.clubs.away.primary } as CSSProperties}>{props.roster.clubs.away.short}</span>
          {props.clock !== undefined && <span className="num clk">{clock(props.clock)}</span>}
        </div>
      )}
      {lower && !replaying && (
        <div key={lower.key} className="p3-lower" style={{ "--club": lower.color } as CSSProperties}>
          <span className="kind">{lower.kind}</span>
          <b>{lower.title}</b>
          <span className="sub">{lower.sub}</span>
        </div>
      )}
      {wipe && <div key={wipe.key} className="p3-wipe" style={{ "--club": wipe.color } as CSSProperties} onAnimationEnd={() => setWipe(null)} />}
      {replaying && (
        <div className="p3-replay">
          <b>Replay</b>
          <button onClick={() => engine.current?.stopExplain()}>Back to live</button>
        </div>
      )}
      {caption && (
        <div key={caption.kind + caption.text} className="p3-caption" style={{ "--club": caption.color } as CSSProperties}>
          <span className="kind">{caption.kind}</span>
          <p>{caption.text}</p>
        </div>
      )}
      {!replaying && <div className="p3-hint label">Drag to orbit. Scroll to zoom. Click a player to focus.</div>}
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
  const { onSelect: _onSelect, explain, onExplainEnd, ...flat } = props;
  // The 2D fallback cannot run the 3D replay, so tell the caller it is over.
  useEffect(() => {
    if (!ok && explain) onExplainEnd?.();
  }, [ok, explain, onExplainEnd]);
  if (!ok) return <Pitch {...flat} />;
  return (
    <Boundary onFail={() => setOk(false)}>
      <Scene ref={ref} {...props} onFail={() => setOk(false)} />
    </Boundary>
  );
});

export default Pitch3D;
