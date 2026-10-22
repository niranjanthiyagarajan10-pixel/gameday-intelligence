import { useEffect, useState } from "react";

export type Route = { page: "match" } | { page: "shot"; id: string } | { page: "player"; id: string };

function parse(hash: string): Route {
  const [, page, id] = hash.replace(/^#/, "").split("/");
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
