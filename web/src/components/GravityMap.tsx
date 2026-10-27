import { useEffect, useMemo, useRef, useState } from "react";
import type { GravityGrid, GravityPlayer, Roster, Side } from "../types";
import { Jersey } from "./Kit";
import { Crest } from "./Crest";
import { t } from "../i18n";

type Metric = "overall" | "on" | "off";

const SCALE_MAX = 60; // gravity at the ends of the colour scale
const PX_PER_M = 4;
const VIEW = { x: -3, y: -3, w: 111, h: 74 };
const SIGMA_CELLS = 1.1;
const MIN_FRAMES = 40; // smoothed frames below which a spot fades to the background
const BANDS = 9; // per side of zero, for the contour look
const BG: [number, number, number] = [12, 14, 17];

// The NBA's diverging gravity scale: more attention runs dark red to pink, less runs dark blue to ice.
const STOPS: [number, [number, number, number]][] = [
  [-1, [181, 220, 255]],
  [-0.66, [64, 138, 204]],
  [-0.33, [26, 64, 92]],
  [0, BG],
  [0.33, [118, 44, 28]],
  [0.66, [236, 112, 98]],
  [1, [255, 206, 220]],
];
const POSITION: Record<string, string> = { GK: "GK", DF: "DF", MF: "MF", FW: "FW" };

function colour(v: number): [number, number, number] {
  const t = Math.max(-1, Math.min(1, v));
  for (let i = 1; i < STOPS.length; i++) {
    const [b, cb] = STOPS[i];
    const [a, ca] = STOPS[i - 1];
    if (t <= b) {
      const u = (t - a) / (b - a);
      return [0, 1, 2].map((k) => ca[k] + (cb[k] - ca[k]) * u) as [number, number, number];
    }
  }
  return STOPS[STOPS.length - 1][1];
}

/** Separable Gaussian blur of a column-major grid. */
function blur(grid: number[][], sigma: number): number[][] {
  const r = Math.ceil(sigma * 3);
  const kernel = Array.from({ length: 2 * r + 1 }, (_, i) => Math.exp(-((i - r) ** 2) / (2 * sigma * sigma)));
  const nx = grid.length;
  const ny = grid[0].length;
  const pass = (get: (x: number, y: number) => number, alongX: boolean) =>
    Array.from({ length: nx }, (_, x) =>
      Array.from({ length: ny }, (_, y) => {
        let s = 0;
        for (let k = -r; k <= r; k++) {
          const xx = alongX ? x + k : x;
          const yy = alongX ? y : y + k;
          if (xx >= 0 && xx < nx && yy >= 0 && yy < ny) s += get(xx, yy) * kernel[k + r];
        }
        return s;
      }),
    );
  const once = pass((x, y) => grid[x][y], true);
  return pass((x, y) => once[x][y], false);
}

function sample(grid: number[][], gx: number, gy: number): number {
  const nx = grid.length;
  const ny = grid[0].length;
  const x = Math.max(0, Math.min(nx - 1.001, gx));
  const y = Math.max(0, Math.min(ny - 1.001, gy));
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const u = x - x0;
  const v = y - y0;
  return (
    grid[x0][y0] * (1 - u) * (1 - v) + grid[x0 + 1][y0] * u * (1 - v) + grid[x0][y0 + 1] * (1 - u) * v + grid[x0 + 1][y0 + 1] * u * v
  );
}

/** Smooth heatmap of gravity by location, drawn in contour bands on a dark pitch. */
function Heat({ grid, metric, cellM }: { grid: GravityGrid; metric: Metric; cellM: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const fields = useMemo(() => {
    const pick = (on: number[][], off: number[][]) =>
      metric === "on" ? on : metric === "off" ? off : on.map((col, x) => col.map((v, y) => v + off[x][y]));
    return { sum: blur(pick(grid.on_sum, grid.off_sum), SIGMA_CELLS), n: blur(pick(grid.on_n, grid.off_n), SIGMA_CELLS) };
  }, [grid, metric]);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const w = VIEW.w * PX_PER_M;
    const h = VIEW.h * PX_PER_M;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(w, h);
    for (let py = 0; py < h; py++) {
      for (let px = 0; px < w; px++) {
        const mx = VIEW.x + (px + 0.5) / PX_PER_M;
        const my = VIEW.y + (py + 0.5) / PX_PER_M;
        const gx = mx / cellM - 0.5;
        const gy = my / cellM - 0.5;
        const n = sample(fields.n, gx, gy);
        const value = n > 1e-6 ? sample(fields.sum, gx, gy) / n : 0;
        const banded = Math.round((value / SCALE_MAX) * BANDS) / BANDS;
        const weight = Math.max(0, Math.min(1, (n - MIN_FRAMES * 0.25) / MIN_FRAMES));
        const c = colour(banded);
        const i = (py * w + px) * 4;
        img.data[i] = BG[0] + (c[0] - BG[0]) * weight;
        img.data[i + 1] = BG[1] + (c[1] - BG[1]) * weight;
        img.data[i + 2] = BG[2] + (c[2] - BG[2]) * weight;
        img.data[i + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [fields, cellM]);

  return <canvas ref={ref} className="gravity-canvas" aria-hidden="true" />;
}

const L = { fill: "none", stroke: "#DCE8F5", strokeWidth: 0.32, opacity: 0.9 } as const;
const ARC_DY = Math.sqrt(9.15 ** 2 - 5.5 ** 2);

function Lines() {
  return (
    <svg viewBox={`${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`} className="gravity-lines" aria-hidden="true">
      <rect x={0} y={0} width={105} height={68} {...L} />
      <line x1={52.5} y1={0} x2={52.5} y2={68} {...L} />
      <circle cx={52.5} cy={34} r={9.15} {...L} />
      {[0, 1].map((end) => {
        const left = end === 0;
        const box = left ? 16.5 : 88.5;
        return (
          <g key={end}>
            <rect x={left ? 0 : 88.5} y={13.84} width={16.5} height={40.32} {...L} />
            <rect x={left ? 0 : 99.5} y={24.84} width={5.5} height={18.32} {...L} />
            <path d={`M${box},${34 - ARC_DY}A9.15 9.15 0 0 ${left ? 1 : 0} ${box},${34 + ARC_DY}`} {...L} />
            <rect x={left ? -1.8 : 105} y={30.34} width={1.8} height={7.32} {...L} />
          </g>
        );
      })}
    </svg>
  );
}

function fmt(v: number | null): string {
  return v === null ? "-" : v.toFixed(1);
}

interface Props {
  players: GravityPlayer[];
  maps: Record<Side, GravityGrid>;
  cellM: number;
  roster: Roster;
}

export function GravitySection({ players, maps, cellM, roster }: Props) {
  const [side, setSide] = useState<Side>("home");
  const [metric, setMetric] = useState<Metric>("overall");
  const team = players.filter((p) => p.team === side);
  const [chosen, setChosen] = useState<string | null>(null);
  const player = team.find((p) => p.player === chosen) ?? team[0];
  const club = roster.clubs[side];
  const info = player ? roster.players[player.player] : undefined;

  useEffect(() => setChosen(null), [side]);

  const legend = useMemo(() => {
    const stops = Array.from({ length: 21 }, (_, i) => {
      const v = 1 - i / 10;
      const [r, g, b] = colour(Math.round(v * BANDS) / BANDS);
      return `rgb(${r},${g},${b}) ${(i / 20) * 100}%`;
    });
    return `linear-gradient(90deg, ${stops.join(", ")})`;
  }, []);

  return (
    <section className="bp-section">
      <h3 className="bp-h">{t("Gravity")}</h3>
      <div className="bp-two wide-left">
        <div>
          <div className="bp-seg">
            {(["home", "away"] as Side[]).map((s) => (
              <button key={s} className={side === s ? "on" : ""} onClick={() => setSide(s)}>
                {roster.clubs[s].name}
              </button>
            ))}
          </div>
          <div className="bp-selects">
            <label>
              <span className="label">{t("Gravity metric")}</span>
              <select value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
                <option value="overall">{t("Overall")}</option>
                <option value="on">{t("On-ball")}</option>
                <option value="off">{t("Off-ball")}</option>
              </select>
            </label>
            <label>
              <span className="label">{t("Player")}</span>
              <select value={player?.player ?? ""} onChange={(e) => setChosen(e.target.value)}>
                {team.map((p) => (
                  <option key={p.player} value={p.player}>
                    #{roster.players[p.player]?.number} {roster.players[p.player]?.name} ({p.overall.toFixed(1)})
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="gravity-stage">
            <Heat grid={maps[side]} metric={metric} cellM={cellM} />
            <Lines />
            <span className="gravity-dir">{club.short} attacking &rarr;</span>
          </div>
          <div className="gravity-legend">
            <span className="label">{t("Gravity")}</span>
            <div className="gravity-scale" style={{ background: legend }} />
            <div className="gravity-ticks num">
              {[SCALE_MAX, SCALE_MAX / 2, 0, -SCALE_MAX / 2, -SCALE_MAX].map((v) => (
                <span key={v}>{v > 0 ? `+${v}` : v}</span>
              ))}
            </div>
            <div className="gravity-ticks muted">
              <span>{t("More attention than usual")}</span>
              <span>{t("Less")}</span>
            </div>
          </div>
        </div>

        <div className="bp-card flush">
          {!player || !info ? (
            <div className="empty" style={{ padding: 20 }}>
              {t("Gravity shows once a player has been measured for five minutes with the ball.")}
            </div>
          ) : (
            <>
              <div className="bp-band" style={{ background: club.primary, color: club.secondary }}>
                <div className="bp-band-mark">
                  <Crest club={club} size={120} />
                </div>
                <div>
                  <span className="bp-band-sub">
                    {club.name} | #{info.number} | {POSITION[info.position]}
                  </span>
                  <h4>{info.name}</h4>
                </div>
                <Jersey club={club} info={info} size={92} away />
              </div>
              <div className="bp-card-body">
                <p>{player.text}</p>
                <div className="bp-tiles two">
                  <div className="full">
                    <b className="num">{fmt(player.overall)}</b>
                    <span>{t("Overall, over")} {Math.round(player.seconds / 60)} min with the ball</span>
                  </div>
                  <div><b className="num">{fmt(player.final_third_on_ball)}</b><span>{t("Final third on-ball")}</span></div>
                  <div><b className="num">{fmt(player.build_up_on_ball)}</b><span>{t("Build-up on-ball")}</span></div>
                  <div><b className="num">{fmt(player.final_third_off_ball)}</b><span>{t("Final third off-ball")}</span></div>
                  <div><b className="num">{fmt(player.build_up_off_ball)}</b><span>{t("Build-up off-ball")}</span></div>
                </div>
                <p className="bp-fine">
                  {t("Gravity is the defenders a player pulls close beyond the league average for the same spot and role, from every tracking frame with the ball. +100 is one extra defender.")}
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
