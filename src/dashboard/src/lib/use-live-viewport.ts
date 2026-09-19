/**
 * Robust live MuJoCo viewport client.
 *
 * Transport (contract): long-poll JPEG on GET /viewport/frame?after_seq=&wait_ms=
 * Prefer same-origin Next proxy `/api/bridge/...` so Safari/Chrome never hit
 * multipart MJPEG (known black-box failure mode).
 *
 * Guarantees:
 * - Keeps last good frame (never flash to empty black without reason)
 * - Pauses when tab is hidden (Page Visibility)
 * - Exponential backoff on errors
 * - Honest status: live | waiting | stale | offline
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { bridgeBaseUrl } from "./bridge-client";

export type ViewportStatus = "idle" | "waiting" | "live" | "stale" | "offline";

export type LiveViewportState = {
  /** Object URL for <img src>, or null while waiting for first frame. */
  src: string | null;
  status: ViewportStatus;
  seq: number;
  source: string | null;
  ageMs: number | null;
  error: string | null;
};

const INITIAL: LiveViewportState = {
  src: null,
  status: "idle",
  seq: 0,
  source: null,
  ageMs: null,
  error: null,
};

/** Same-origin proxy path — preferred for frames. */
export function viewportProxyBase(): string {
  if (typeof window === "undefined") return "/api/bridge";
  return `${window.location.origin}/api/bridge`;
}

/**
 * Resolve where to fetch frames from.
 * 1) Same-origin `/api/bridge` (Next proxies to Python)
 * 2) Direct bridge URL as fallback if proxy 502s repeatedly
 */
export function resolveViewportBase(bridgeUrl?: string): string {
  return viewportProxyBase();
  // bridgeUrl kept for API symmetry / future direct mode
  void bridgeUrl;
}

function isJpeg(buf: ArrayBuffer): boolean {
  const u = new Uint8Array(buf);
  return u.length >= 3 && u[0] === 0xff && u[1] === 0xd8 && u[2] === 0xff;
}

export function useLiveViewport(opts: {
  enabled: boolean;
  /** Unused for primary path; reserved if we ever force direct bridge. */
  bridgeUrl?: string;
  waitMs?: number;
}): LiveViewportState {
  const waitMs = opts.waitMs ?? 1500;
  const [state, setState] = useState<LiveViewportState>(INITIAL);
  const objectUrlRef = useRef<string | null>(null);
  const seqRef = useRef(0);
  const visibleRef = useRef(true);
  const failRef = useRef(0);

  useEffect(() => {
    if (!opts.enabled) {
      setState(INITIAL);
      seqRef.current = 0;
      failRef.current = 0;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      return;
    }

    let cancelled = false;
    const ac = new AbortController();

    const onVisibility = () => {
      visibleRef.current = document.visibilityState === "visible";
    };
    document.addEventListener("visibilitychange", onVisibility);
    onVisibility();

    const paint = (buf: ArrayBuffer, seq: number, source: string | null) => {
      const blob = new Blob([buf], { type: "image/jpeg" });
      const next = URL.createObjectURL(blob);
      const prev = objectUrlRef.current;
      objectUrlRef.current = next;
      seqRef.current = seq;
      setState({
        src: next,
        status: "live",
        seq,
        source,
        ageMs: 0,
        error: null,
      });
      if (prev) URL.revokeObjectURL(prev);
    };

    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        const t = window.setTimeout(resolve, ms);
        ac.signal.addEventListener(
          "abort",
          () => {
            window.clearTimeout(t);
            resolve();
          },
          { once: true },
        );
      });

    const loop = async () => {
      // Prefer same-origin proxy; fall back to direct bridge after repeated 502s.
      let base = viewportProxyBase();
      let useDirect = false;

      while (!cancelled && !ac.signal.aborted) {
        if (!visibleRef.current) {
          setState((s) =>
            s.src ? { ...s, status: "stale" } : { ...s, status: "waiting" },
          );
          await sleep(400);
          continue;
        }

        const after = seqRef.current;
        const url = `${base}/viewport/frame?after_seq=${after}&wait_ms=${waitMs}`;

        try {
          setState((s) =>
            s.src
              ? s.status === "live"
                ? s
                : { ...s, status: "live" }
              : { ...s, status: "waiting", error: null },
          );

          const res = await fetch(url, {
            cache: "no-store",
            signal: ac.signal,
          });

          if (res.status === 304) {
            failRef.current = 0;
            setState((s) => (s.src ? { ...s, status: "live" } : s));
            continue;
          }

          if (res.status === 502 || res.status === 503) {
            failRef.current += 1;
            // Proxy dead → try direct bridge once we have a few failures.
            if (!useDirect && failRef.current >= 2) {
              useDirect = true;
              base = (opts.bridgeUrl || bridgeBaseUrl()).replace(/\/$/, "");
            }
            setState((s) => ({
              ...s,
              status: s.src ? "stale" : "offline",
              error:
                res.status === 503
                  ? "Viewport aún no listo"
                  : "Bridge inalcanzable",
            }));
            await sleep(Math.min(4000, 300 * failRef.current));
            continue;
          }

          if (!res.ok) {
            failRef.current += 1;
            setState((s) => ({
              ...s,
              status: s.src ? "stale" : "offline",
              error: `HTTP ${res.status}`,
            }));
            await sleep(Math.min(4000, 300 * failRef.current));
            continue;
          }

          const buf = await res.arrayBuffer();
          if (!isJpeg(buf)) {
            failRef.current += 1;
            await sleep(200);
            continue;
          }

          const seqHeader = res.headers.get("X-Viewport-Seq");
          const seq = seqHeader ? Number(seqHeader) : after + 1;
          const source = res.headers.get("X-Viewport-Source");

          failRef.current = 0;
          if (seq > after || !objectUrlRef.current) {
            paint(buf, Number.isFinite(seq) ? seq : after + 1, source);
          } else {
            setState((s) => ({ ...s, status: "live", error: null }));
          }
        } catch (err) {
          if (cancelled || ac.signal.aborted) break;
          failRef.current += 1;
          if (!useDirect && failRef.current >= 2) {
            useDirect = true;
            base = (opts.bridgeUrl || bridgeBaseUrl()).replace(/\/$/, "");
          }
          setState((s) => ({
            ...s,
            status: s.src ? "stale" : "offline",
            error: err instanceof Error ? err.message : "error de red",
          }));
          await sleep(Math.min(4000, 400 * failRef.current));
        }
      }
    };

    void loop();

    return () => {
      cancelled = true;
      ac.abort();
      document.removeEventListener("visibilitychange", onVisibility);
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [opts.enabled, opts.bridgeUrl, waitMs]);

  return state;
}
