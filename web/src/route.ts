import { useEffect, useState } from "react";
import type { Audience } from "./types";

export type Route =
  | { page: "match" }
  | { page: "shot"; id: string }
  | { page: "player"; id: string }
  | { page: "blueprint" }
  | { page: "overlay"; bg: boolean; audience: Audience };

function parse(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#/, "").split("?");
  const [, page, id] = path.split("/");
  if (page === "overlay") {
    const q = new URLSearchParams(query);
    return { page: "overlay", bg: q.get("bg") === "pitch", audience: q.get("aud") === "analyst" ? "analyst" : "casual" };
  }
  if (page === "blueprint") return { page: "blueprint" };
  if (page === "shot" && id) return { page: "shot", id: decodeURIComponent(id) };
  if (page === "player" && id) return { page: "player", id: decodeURIComponent(id) };
  return { page: "match" };
}

/** Pages live in the URL hash, so the live match connection stays open behind them. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parse(location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export const shotHref = (id: string) => `#/shot/${encodeURIComponent(id)}`;
export const playerHref = (id: string) => `#/player/${encodeURIComponent(id)}`;
export const overlayHref = (bg: boolean) => `${location.search}#/overlay${bg ? "?bg=pitch" : ""}`;
