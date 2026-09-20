"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The run's H.264 recording, live or finished.
 *
 * One HLS URL: no ENDLIST while the run is going (player tails it), then
 * ENDLIST turns the same file into a VOD. Prefer hls.js whenever MSE works —
 * Chromium's native HLS does not play this fMP4 live playlist.
 *
 * The viewport keeps the fold loader up until the file can play (`ready`).
 * A parked VOD (paused at t=0) is still ready — do not wait for Play.
 * Replay transport
 * (seek / play / pause) is driven by the HUD, not the native video bar.
 */

const NATIVE = "application/vnd.apple.mpegurl";

export type Status = "waiting" | "ready" | "error";

export type VideoTransport = {
  t: number;
  playing: boolean;
  onTime: (t: number) => void;
  onEnded: () => void;
};

export function RunVideoPlayer({
  runId,
  live,
  transport,
  className,
  onStatus,
}: {
  runId: string;
  live: boolean;
  transport?: VideoTransport;
  className?: string;
  onStatus?: (status: Status) => void;
}) {
  const ref = useRef<HTMLVideoElement | null>(null);
  const [status, setStatus] = useState<Status>("waiting");
  const transportRef = useRef(transport);
  transportRef.current = transport;
  const liveRef = useRef(live);
  liveRef.current = live;

  useEffect(() => {
    onStatus?.(status);
  }, [status, onStatus]);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    const src = `/api/bridge/runs/${encodeURIComponent(runId)}/video/index.m3u8`;
    let cancelled = false;
    let destroy: (() => void) | undefined;
    setStatus("waiting");

    const markReady = () => {
      if (!cancelled) setStatus("ready");
    };
    const onEnded = () => {
      if (cancelled) return;
      video.currentTime = 0;
      video.pause();
      setStatus("ready");
      transportRef.current?.onEnded();
    };
    video.addEventListener("canplay", markReady);
    video.addEventListener("loadeddata", markReady);
    video.addEventListener("playing", markReady);
    video.addEventListener("ended", onEnded);
    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) markReady();

    async function attach() {
      const minSeg = liveRef.current ? 2 : 1;
      const playlist = await waitForPlaylist(src, () => cancelled, minSeg);
      if (cancelled || !video) return;
      if (!playlist) {
        setStatus("error");
        return;
      }

      const { default: Hls } = await import("hls.js");
      if (cancelled) return;

      const liveNow = () => liveRef.current && !transportRef.current;

      if (Hls.isSupported()) {
        const hls = new Hls({
          enableWorker: true,
          lowLatencyMode: false,
          liveSyncDurationCount: 3,
          liveMaxLatencyDurationCount: 6,
          maxBufferLength: liveRef.current ? 8 : 30,
          backBufferLength: liveRef.current ? 30 : 600,
          manifestLoadPolicy: {
            default: {
              maxTimeToFirstByteMs: 10_000,
              maxLoadTimeMs: 20_000,
              timeoutRetry: { maxNumRetry: 8, retryDelayMs: 1000, maxRetryDelayMs: 4000 },
              errorRetry: { maxNumRetry: 12, retryDelayMs: 1000, maxRetryDelayMs: 4000 },
            },
          },
        });
        let joined = false;
        const start = () => {
          if (cancelled || joined) return;
          const parked = transportRef.current && !transportRef.current.playing;
          if (liveNow()) {
            const edge = hls.liveSyncPosition;
            if (edge == null || !Number.isFinite(edge)) return;
            joined = true;
            video.currentTime = edge;
            void video.play().catch(() => {});
            return;
          }
          joined = true;
          if (parked) {
            video.currentTime = transportRef.current?.t ?? 0;
            video.pause();
            setStatus("ready");
            return;
          }
          void video.play().catch(() => {});
        };
        hls.on(Hls.Events.MANIFEST_PARSED, start);
        hls.on(Hls.Events.LEVEL_UPDATED, start);
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (!data.fatal) return;
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
          else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
          else setStatus("error");
        });
        hls.loadSource(src);
        hls.attachMedia(video);
        destroy = () => hls.destroy();
        return;
      }

      if (video.canPlayType(NATIVE)) {
        const onMeta = () => {
          if (cancelled) return;
          const parked = transportRef.current && !transportRef.current.playing;
          if (liveNow() && video.seekable.length > 0) {
            video.currentTime = video.seekable.end(video.seekable.length - 1);
            void video.play().catch(() => {});
            return;
          }
          if (parked) {
            video.currentTime = transportRef.current?.t ?? 0;
            video.pause();
            setStatus("ready");
            return;
          }
          void video.play().catch(() => {});
        };
        video.addEventListener("loadedmetadata", onMeta, { once: true });
        video.src = src;
        return;
      }

      setStatus("error");
    }

    void attach();
    return () => {
      cancelled = true;
      video.removeEventListener("canplay", markReady);
      video.removeEventListener("loadeddata", markReady);
      video.removeEventListener("playing", markReady);
      video.removeEventListener("ended", onEnded);
      video.pause();
      video.removeAttribute("src");
      video.load();
      destroy?.();
    };
  }, [runId]);

  useEffect(() => {
    const video = ref.current;
    if (!video || !transport) return;

    const onTime = () => transportRef.current?.onTime(video.currentTime);
    video.addEventListener("timeupdate", onTime);
    return () => {
      video.removeEventListener("timeupdate", onTime);
    };
  }, [transport]);

  useEffect(() => {
    const video = ref.current;
    if (!video || !transport) return;
    if (transport.playing) return;
    if (Math.abs(video.currentTime - transport.t) > 0.15) {
      video.currentTime = transport.t;
    }
  }, [transport, transport?.t]);

  useEffect(() => {
    const video = ref.current;
    if (!video || !transport) return;
    if (transport.playing) void video.play().catch(() => {});
    else video.pause();
  }, [transport, transport?.playing]);

  return (
    <video
      ref={ref}
      muted
      playsInline
      autoPlay={false}
      preload="auto"
      controls={false}
      className={className}
    />
  );
}

function playlistHasMedia(text: string, min: number): boolean {
  return (text.match(/#EXTINF/g)?.length ?? 0) >= min;
}

async function waitForPlaylist(
  src: string,
  cancelled: () => boolean,
  minSegments = 1,
): Promise<boolean> {
  for (; !cancelled(); ) {
    try {
      const probe = await fetch(src, { method: "GET", cache: "no-store" });
      if (probe.ok && playlistHasMedia(await probe.text(), minSegments)) return true;
    } catch {
      /* bridge not up yet */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}
