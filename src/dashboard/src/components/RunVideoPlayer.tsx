"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The run's H.264 recording, live or finished.
 *
 * The bridge writes one HLS playlist per run: it grows while the run is going
 * and gains #EXT-X-ENDLIST when it ends. So this is the same URL in both
 * cases — live it tails a couple of segments behind, and once the run is over
 * the browser treats it as an ordinary video and scrubs it natively.
 *
 * Safari plays HLS directly; everywhere else hls.js is imported on demand, so
 * it stays out of the bundle for anyone who never opens a recorded run.
 */

const NATIVE = "application/vnd.apple.mpegurl";

export type Status = "waiting" | "playing" | "error";

export function RunVideoPlayer({
  runId,
  live,
  className,
  onStatus,
}: {
  runId: string;
  live: boolean;
  className?: string;
  /** Lets the caller keep showing something else until the video is up. */
  onStatus?: (status: Status) => void;
}) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const [status, setStatus] = useState<Status>("waiting");

  useEffect(() => {
    onStatus?.(status);
  }, [status, onStatus]);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    const src = `/api/bridge/runs/${encodeURIComponent(runId)}/video/index.m3u8`;
    let cancelled = false;
    let destroy: (() => void) | undefined;

    // The element's own event, not the manifest's: a parsed playlist only
    // means the bytes arrived, and a browser without H.264 gets that far and
    // then shows black. `loadeddata` means a frame actually decoded.
    const onData = () => setStatus("playing");
    video.addEventListener("loadeddata", onData);

    async function attach() {
      // The recorder marks the run before ffmpeg has closed a first segment,
      // so the playlist can 404 for a second or two. Wait it out rather than
      // letting the player report a hard error.
      for (let i = 0; i < 40 && !cancelled; i++) {
        try {
          const probe = await fetch(src, { method: "GET", cache: "no-store" });
          if (probe.ok) break;
        } catch {
          /* bridge not up yet */
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
      if (cancelled || !video) return;

      if (video.canPlayType(NATIVE)) {
        video.src = src;
        return;
      }

      const { default: Hls } = await import("hls.js");
      if (cancelled) return;
      if (!Hls.isSupported()) {
        setStatus("error");
        return;
      }
      const hls = new Hls({
        // Live: sit ~2 segments back, which is the delay we trade for H.264.
        liveSyncDurationCount: 2,
        lowLatencyMode: false,
        // A live playlist 404s until the first segment lands, and a run can
        // pause; keep retrying rather than giving up on the stream.
        manifestLoadPolicy: {
          default: {
            maxTimeToFirstByteMs: 10_000,
            maxLoadTimeMs: 20_000,
            timeoutRetry: { maxNumRetry: 6, retryDelayMs: 1000, maxRetryDelayMs: 4000 },
            errorRetry: { maxNumRetry: 8, retryDelayMs: 1000, maxRetryDelayMs: 4000 },
          },
        },
      });
      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (!data.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
        else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
        else setStatus("error");
      });
      hls.loadSource(src);
      hls.attachMedia(video);
      destroy = () => hls.destroy();
    }

    void attach();
    return () => {
      cancelled = true;
      video.removeEventListener("loadeddata", onData);
      destroy?.();
    };
  }, [runId]);

  return (
    <>
      <video
        ref={ref}
        // Live tails the edge on its own; a finished run is scrubbed by hand.
        autoPlay
        muted
        playsInline
        controls={!live}
        className={className}
      />
      {status === "error" ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-[12px] uppercase tracking-[0.12em] text-hud-dim">
          Vídeo no reproducible
        </div>
      ) : null}
    </>
  );
}
