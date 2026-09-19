"use client";

import { useEffect, useRef, type CSSProperties } from "react";
import { patchChildren } from "@/lib/patch-svg";
import { renderXFoldFrame, XFOLD_CYCLE_MS, XFOLD_REST_FRAME } from "@/lib/xfold-motion.mjs";

export type XFoldLoaderProps = {
  /** Width in px. Height follows the animation's 120:148 canvas unless overridden. */
  size?: number;
  /** Height in px; defaults to `size * 148 / 120`. Pair with `viewBox` to crop. */
  height?: number;
  /** SVG viewBox; defaults to the full "0 0 120 148" canvas. */
  viewBox?: string;
  label?: string;
  showLabel?: boolean;
  /** Use for purely decorative animations (e.g. the header logo). */
  decorative?: boolean;
  playing?: boolean;
  loop?: boolean;
  speed?: number;
  /** Change this to restart a one-shot animation. */
  replayKey?: number;
  onComplete?: () => void;
  className?: string;
  /** CSS color of the containing surface; also used for opaque folded faces. */
  surface?: string;
  tone?: "light" | "dark";
};

const REST_MARKUP = { __html: renderXFoldFrame(XFOLD_REST_FRAME) };

export function XFoldLoader({
  size = 64, height, viewBox = "0 0 120 148",
  label = "Loading…", showLabel = false, decorative = false,
  playing = true, loop = true, speed = 1, replayKey = 0, onComplete,
  className = "", surface = "var(--background, #f4ecd8)", tone = "light",
}: XFoldLoaderProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const contentRef = useRef<SVGGElement>(null);
  const completeRef = useRef(onComplete);
  useEffect(() => { completeRef.current = onComplete; }, [onComplete]);

  useEffect(() => {
    const svg = svgRef.current;
    const content = contentRef.current;
    if (!svg || !content) return;
    const scratch = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const rate = Number.isFinite(speed) ? Math.max(0.1, Math.min(4, speed)) : 1;
    let frame = 0, time = 0, last: number | null = null;
    let visible = false, finished = false, disposed = false;
    const draw = (ms: number) => {
      // Geometry is authored locally, never sourced from props or network data.
      scratch.innerHTML = renderXFoldFrame(ms);
      patchChildren(content, scratch);
    };
    const canRun = () => playing && visible && !document.hidden && !motion.matches && !finished;
    const tick = (now: number) => {
      frame = 0;
      if (disposed || !canRun()) { last = null; return; }
      if (last !== null) time += Math.min(now - last, 80) * rate;
      last = now;
      if (time >= XFOLD_CYCLE_MS) {
        if (loop) time %= XFOLD_CYCLE_MS;
        else {
          finished = true;
          draw(XFOLD_REST_FRAME);
          completeRef.current?.();
          return;
        }
      }
      draw((XFOLD_REST_FRAME + time) % XFOLD_CYCLE_MS);
      frame = requestAnimationFrame(tick);
    };
    const sync = () => {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      last = null;
      if (motion.matches || !playing) draw(XFOLD_REST_FRAME);
      if (canRun()) frame = requestAnimationFrame(tick);
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    });
    observer.observe(svg);
    motion.addEventListener("change", sync);
    document.addEventListener("visibilitychange", sync);
    sync();
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      motion.removeEventListener("change", sync);
      document.removeEventListener("visibilitychange", sync);
    };
  }, [playing, loop, speed, replayKey]);

  const colors = {
    "--stage-paper": surface,
    "--stage-ink": tone === "dark" ? "#faf6ec" : "#2a170f",
    "--stage-fold": "#d96b2a",
    "--stage-reverse": tone === "dark" ? "#925531" : "#efc39b",
    "--stage-sleeve": tone === "dark" ? "#49382c" : "#e9dfcb",
  } as CSSProperties;
  return (
    <span
      role={decorative ? undefined : "status"}
      aria-live={decorative ? undefined : "polite"}
      aria-hidden={decorative || undefined}
      className={`inline-flex shrink-0 flex-col items-center justify-center gap-2 ${className}`}
      style={colors}
    >
      <svg ref={svgRef} width={size} height={height ?? size * 148 / 120} viewBox={viewBox} aria-hidden="true" style={{ overflow: "hidden", display: "block" }}>
        <g ref={contentRef} dangerouslySetInnerHTML={REST_MARKUP} />
      </svg>
      {!decorative ? <span className={showLabel ? "text-sm text-muted-foreground" : "sr-only"}>{label}</span> : null}
    </span>
  );
}
