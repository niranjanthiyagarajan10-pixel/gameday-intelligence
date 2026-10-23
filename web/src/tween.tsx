import { useEffect, useRef, useState } from "react";

const still = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** A number that eases to each new value instead of jumping, like a broadcast graphic. */
export function useTween(target: number, ms = 300): number {
  const [value, setValue] = useState(target);
  const current = useRef(target);
  useEffect(() => {
    if (still() || !Number.isFinite(target)) {
      current.current = target;
      setValue(target);
      return;
    }
    const from = current.current;
    const start = performance.now();
    let raf = 0;
    const step = () => {
      const a = Math.min(1, (performance.now() - start) / ms);
      const v = from + (target - from) * (1 - (1 - a) ** 3);
      current.current = v;
      setValue(v);
      if (a < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return value;
}

/** True once the value differs from the one first shown, so a page load does not count as a change. */
export function useChangedSinceMount(value: string): boolean {
  const first = useRef(value);
  return value !== first.current;
}

/** Renders a ticking number. */
export function Tick({ value, digits = 0, scale = 1 }: { value: number; digits?: number; scale?: number }) {
  const v = useTween(value * scale);
  return <>{digits === 0 ? Math.round(v) : v.toFixed(digits)}</>;
}
