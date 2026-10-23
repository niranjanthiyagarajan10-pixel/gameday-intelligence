import { useCallback, useEffect, useReducer, useRef } from "react";
import type { AgentInfo, Analyst, Card, Cue, Frame, FxEvent, MatchState, Roster, Stats, Status, TraceStep } from "./types";

type Message =
  | {
      type: "hello";
      room: string;
      status: Status;
      speed: number;
      paused: boolean;
      half_s: number;
      roster: Roster;
      stats: Stats & { type: string };
      frame: (Frame & { type: string }) | null;
      history: number[][];
      cards: Card[];
      analyst: Analyst;
      trace?: TraceStep[];
      agents?: AgentInfo;
    }
  | (Frame & { type: "frame" })
  | (Stats & { type: "stats" })
  | (Card & { type: "card" })
  | (Analyst & { type: "analyst" })
  | { type: "events"; events: Omit<FxEvent, "at">[]; at: number }
  | { type: "trace"; steps: TraceStep[] }
  | { type: "card_update"; moment_id: string; cues: Card["cues"]; source: string; sources: Record<string, string> }
  | { type: "control"; status: Status; speed: number; paused: boolean }
  | { type: "error"; message: string };

type Action = Message | { type: "connected"; value: boolean };

const HISTORY_STEP_S = 10;
const FX_KEEP_MS = 6000;
const FX_MAX = 80;
const TRACE_KEEP = 400;

const initial: MatchState = {
  connected: false,
  room: "main",
  status: "live",
  speed: 1,
  paused: false,
  halfS: 2700,
  roster: null,
  frame: null,
  stats: null,
  history: [],
  cards: [],
  analyst: null,
  fx: [],
  trace: [],
  agents: null,
};

function reducer(state: MatchState, msg: Action): MatchState {
  switch (msg.type) {
    case "connected":
      return { ...state, connected: msg.value };
    case "hello":
      return {
        ...state,
        room: msg.room,
        status: msg.status,
        speed: msg.speed,
        paused: msg.paused,
        halfS: msg.half_s,
        roster: msg.roster,
        frame: msg.frame,
        stats: msg.stats,
        history: msg.history,
        cards: msg.cards,
        analyst: msg.analyst,
        fx: [],
        trace: msg.trace ?? [],
        agents: msg.agents ?? null,
      };
    case "frame":
      return { ...state, frame: msg };
    case "stats": {
      const last = state.history[state.history.length - 1];
      const scoreChanged =
        state.stats && (state.stats.score[0] !== msg.score[0] || state.stats.score[1] !== msg.score[1]);
      const history =
        !last || msg.t - last[0] >= HISTORY_STEP_S || scoreChanged
          ? [...state.history, [msg.t, ...msg.win_prob]]
          : state.history;
      return { ...state, stats: msg, history };
    }
    case "card":
      if (state.cards.some((c) => c.moment.moment_id === msg.moment.moment_id)) return state;
      return { ...state, cards: [...state.cards, msg] };
    case "analyst":
      return { ...state, analyst: msg };
    case "trace":
      return { ...state, trace: [...state.trace, ...msg.steps].slice(-TRACE_KEEP) };
    case "card_update":
      return {
        ...state,
        cards: state.cards.map((c) =>
          c.moment.moment_id === msg.moment_id
            ? { ...c, cues: msg.cues as Record<"casual" | "analyst", Cue>, source: msg.source, sources: msg.sources as Card["sources"] }
            : c,
        ),
      };
    case "events": {
      const kept = state.fx.filter((e) => msg.at - e.at < FX_KEEP_MS);
      return { ...state, fx: [...kept, ...msg.events.map((e) => ({ ...e, at: msg.at }))].slice(-FX_MAX) };
    }
    case "control":
      return { ...state, status: msg.status, speed: msg.speed, paused: msg.paused };
    default:
      return state;
  }
}

/** Live connection to a match room. onGone fires if the room no longer exists, say after a redeploy. */
export function useMatch(room: string, onGone?: () => void) {
  const [state, dispatch] = useReducer(reducer, initial);
  const socket = useRef<WebSocket | null>(null);
  const gone = useRef(onGone);
  gone.current = onGone;

  useEffect(() => {
    let closed = false;
    let retry = 0;
    let timer: number | undefined;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/${room}`);
      socket.current = ws;
      ws.onopen = () => {
        retry = 0;
        dispatch({ type: "connected", value: true });
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data) as Message;
        // Stamp arrival here so the reducer stays pure; animations time themselves from it.
        dispatch(msg.type === "events" ? { ...msg, at: performance.now() } : msg);
      };
      ws.onclose = (e) => {
        dispatch({ type: "connected", value: false });
        if (e.code === 4404) {
          gone.current?.();
          return;
        }
        if (!closed) {
          retry = Math.min(retry + 1, 6);
          timer = window.setTimeout(connect, 500 * 2 ** retry);
        }
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      socket.current?.close();
    };
  }, [room]);

  const control = useCallback((action: string, value?: number) => {
    socket.current?.send(JSON.stringify({ action, value }));
  }, []);

  return { state, control };
}
