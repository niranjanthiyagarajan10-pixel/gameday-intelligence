import { useCallback, useEffect, useReducer, useRef } from "react";
import type { Analyst, Card, Frame, MatchState, Roster, Stats, Status } from "./types";

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
    }
  | (Frame & { type: "frame" })
  | (Stats & { type: "stats" })
  | (Card & { type: "card" })
  | (Analyst & { type: "analyst" })
  | { type: "control"; status: Status; speed: number; paused: boolean }
  | { type: "error"; message: string };

type Action = Message | { type: "connected"; value: boolean };

const HISTORY_STEP_S = 10;

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
      ws.onmessage = (e) => dispatch(JSON.parse(e.data) as Message);
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
