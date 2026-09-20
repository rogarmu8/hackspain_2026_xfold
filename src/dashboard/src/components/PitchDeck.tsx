"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { DARK_SURFACE, LIGHT_SURFACE, SLIDES } from "@/components/pitch-slides";

const NEXT_KEYS = new Set([" ", "Spacebar", "ArrowRight", "ArrowDown", "PageDown", "Enter", "n"]);
const PREV_KEYS = new Set(["ArrowLeft", "ArrowUp", "PageUp", "Backspace", "p"]);
/** Horizontal travel that counts as a swipe rather than a tap. */
const SWIPE_PX = 48;

function clampIndex(value: number) {
  return Math.max(0, Math.min(SLIDES.length - 1, value));
}

/**
 * The URL hash is the deck's position (`#3`, 1-based, so the address bar reads
 * like a deck). Keeping it as the only state means a reload or a shared link
 * lands on the same slide. Moving replaces the entry rather than pushing one,
 * so Back leaves the deck instead of walking it backwards one slide at a time.
 */
const listeners = new Set<() => void>();

function subscribeToHash(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("hashchange", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("hashchange", listener);
  };
}

function readHash() {
  return window.location.hash;
}

function hashIndex(hash: string) {
  const raw = Number(hash.slice(1));
  return Number.isFinite(raw) && raw > 0 ? clampIndex(raw - 1) : 0;
}

function writeHash(index: number) {
  window.history.replaceState(null, "", `#${index + 1}`);
  for (const listener of listeners) listener();
}

/**
 * The pitch deck at /ppt. Space or → advances, ← goes back; the slide index
 * lives in the URL hash so a reload lands where you were.
 */
export function PitchDeck() {
  // Server render (and the hydration pass) always starts at the first slide.
  const index = hashIndex(useSyncExternalStore(subscribeToHash, readHash, () => ""));
  const touchRef = useRef<{ x: number; y: number } | null>(null);

  const go = useCallback((next: number) => {
    writeHash(clampIndex(next));
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (NEXT_KEYS.has(event.key)) {
        // Space would otherwise scroll the page under the deck.
        event.preventDefault();
        go(index + 1);
      } else if (PREV_KEYS.has(event.key)) {
        event.preventDefault();
        go(index - 1);
      } else if (event.key === "Home") {
        event.preventDefault();
        go(0);
      } else if (event.key === "End") {
        event.preventDefault();
        go(SLIDES.length - 1);
      } else if (event.key === "f") {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen().catch(() => {});
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index]);

  const slide = SLIDES[index];
  const dark = slide.tone === "dark";
  const surface = dark ? DARK_SURFACE : LIGHT_SURFACE;

  return (
    <main
      className="relative flex h-[100svh] w-full flex-col overflow-hidden transition-colors duration-500"
      style={
        {
          background: surface,
          color: dark ? "#faf6ec" : "var(--foreground)",
          "--slide-surface": surface,
        } as React.CSSProperties
      }
      onPointerDown={(event) => {
        touchRef.current = { x: event.clientX, y: event.clientY };
      }}
      onPointerUp={(event) => {
        const start = touchRef.current;
        touchRef.current = null;
        // A button inside the slide handles its own click.
        if ((event.target as HTMLElement).closest("button, a")) return;
        if (!start) return;
        const dx = event.clientX - start.x;
        // Swipe picks the direction; any other click or tap advances.
        go(index + (Math.abs(dx) > SWIPE_PX ? (dx < 0 ? 1 : -1) : 1));
      }}
    >
      <section
        key={slide.id}
        aria-roledescription="slide"
        aria-label={`${index + 1} of ${SLIDES.length}: ${slide.label}`}
        className="flex flex-1 items-center justify-center px-6 py-16 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-500 motion-safe:slide-in-from-bottom-4 sm:px-12 lg:px-20"
      >
        <div className="w-full max-w-5xl">
          <slide.Content />
        </div>
      </section>

      <footer className="flex shrink-0 items-center justify-between gap-4 px-6 pb-5 text-current sm:px-12 lg:px-20">
        <p className="font-mono text-[11px] tracking-[0.14em] uppercase opacity-45">
          {slide.label}
        </p>
        <div className="flex items-center gap-4">
          <p className="tabular font-mono text-[11px] tracking-[0.14em] opacity-45">
            {String(index + 1).padStart(2, "0")} / {String(SLIDES.length).padStart(2, "0")}
          </p>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => go(index - 1)}
              disabled={index === 0}
              aria-label="Previous slide"
              className="rounded-[var(--radius)] p-2 opacity-55 transition-opacity hover:opacity-100 disabled:opacity-15"
            >
              <ChevronLeft size={18} aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => go(index + 1)}
              disabled={index === SLIDES.length - 1}
              aria-label="Next slide"
              className="rounded-[var(--radius)] p-2 opacity-55 transition-opacity hover:opacity-100 disabled:opacity-15"
            >
              <ChevronRight size={18} aria-hidden />
            </button>
          </div>
        </div>
      </footer>

      <div className="h-[3px] w-full shrink-0 bg-current/10" aria-hidden>
        <div
          className="h-full bg-[var(--primary)] transition-[width] duration-500 ease-[var(--motion-ease)]"
          style={{ width: `${((index + 1) / SLIDES.length) * 100}%` }}
        />
      </div>

      {index === 0 ? (
        <p className="pointer-events-none absolute inset-x-0 bottom-16 text-center font-mono text-[11px] tracking-[0.16em] uppercase opacity-40 motion-safe:animate-pulse">
          Press space to start
        </p>
      ) : null}
    </main>
  );
}
