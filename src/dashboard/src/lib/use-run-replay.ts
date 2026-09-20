"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PhaseId } from "@xfold/protocol";
import { BridgeClient, bridgeBaseUrl } from "@/lib/bridge-client";
import type {
  RecordingFrame,
  RunDetail,
  StageProgress,
  TimelineMarker,
} from "@/lib/types";

export type RunReplay = {
  t: number;
  tMax: number;
  playing: boolean;
  loading: boolean;
  hasTrajectory: boolean;
  markers: TimelineMarker[];
  /** Stage progress as it was at time `t`. */
  stages: StageProgress[];
  active: PhaseId | null;
  /** `data:` URL of the recorded frame at `t`, if any. */
  frameSrc: string | null;
  seek: (t: number) => void;
  togglePlay: () => void;
  stepMarker: (dir: -1 | 1) => void;
  /** Update `t` without pausing — used while the video element is the clock. */
  reportTime: (t: number) => void;
};

/** Timeline fetched from the bridge; `markers === null` ⇒ bridge had none. */
type Remote = {
  runId: string;
  markers: TimelineMarker[] | null;
  tMax: number | null;
  hasTrajectory: boolean;
};

type Cursor = { runId: string | null; t: number; playing: boolean };

const IDLE: Cursor = { runId: null, t: 0, playing: false };

function activeStateAt(markers: TimelineMarker[], t: number): PhaseId | null {
  let current: PhaseId | null = null;
  for (const m of markers) {
    if (m.t > t) break;
    if (m.state && !m.finished) current = m.state;
  }
  return current;
}

export function stagesForT(markers: TimelineMarker[], t: number, tMax: number, stages: StageProgress[]): StageProgress[] {
  const active = activeStateAt(markers, t);
  const transitions = markers.filter((m) => m.state && !m.finished);
  const terminal = markers.find((m) => m.finished && m.t <= t);
  return stages.map((stage) => {
    const index = transitions.findIndex((m) => m.state === stage.state);
    const start = transitions[index]?.t;
    if (start == null || t < start) {
      return { ...stage, status: terminal && start == null ? "skipped" : "pending", startedAtSimS: start ?? null, durationSimS: null };
    }
    if (active === stage.state && !terminal) {
      return { ...stage, status: "active", startedAtSimS: start, durationSimS: null };
    }
    const nextT = transitions.slice(index + 1).find((m) => m.state !== stage.state)?.t ?? terminal?.t ?? tMax;
    const status = active === stage.state && terminal?.lifecycle === "failed" ? "failed"
      : active === stage.state && terminal?.lifecycle === "cancelled" ? "skipped" : "completed";
    return { ...stage, status, startedAtSimS: start, durationSimS: Math.max(0, nextT - start) };
  });
}

/** Fallback markers from run.stages when the bridge has no timeline yet. */
function markersFromStages(run: RunDetail | null): TimelineMarker[] {
  if (!run) return [];
  return run.stages
    .filter((s) => s.startedAtSimS != null)
    .map((s) => ({ t: s.startedAtSimS as number, state: s.state }))
    .sort((a, b) => a.t - b.t);
}

/**
 * Scrubbable replay of a finished run: FSM markers from the journal timeline
 * and (when available) recorded MuJoCo frames. Disabled ⇒ inert, no fetches.
 * All state is keyed by `runId`, so switching runs resets without effects.
 */
export function useRunReplay({
  run,
  enabled,
  bridgeUrl,
  clock = "internal",
}: {
  run: RunDetail | null;
  enabled: boolean;
  bridgeUrl?: string;
  /** `video`: the <video> element reports time; skip the synthetic ticker and JPEG frames. */
  clock?: "internal" | "video";
}): RunReplay {
  const runId = run?.id ?? null;
  const base = bridgeUrl || bridgeBaseUrl();
  const client = useMemo(() => new BridgeClient(base), [base]);

  const [remote, setRemote] = useState<Remote | null>(null);
  const [cursorState, setCursor] = useState<Cursor>(IDLE);
  const [frameState, setFrame] = useState<{ runId: string; frame: RecordingFrame } | null>(null);
  const seekGen = useRef(0);

  const tl = remote?.runId === runId ? remote : null;
  const cursor = cursorState.runId === runId ? cursorState : IDLE;
  const frame = frameState?.runId === runId ? frameState.frame : null;
  const loading = enabled && runId != null && tl == null;
  const hasTrajectory = tl?.hasTrajectory ?? false;

  useEffect(() => {
    if (!enabled || !runId || tl) return;
    let cancelled = false;
    void client.fetchTimeline(runId).then((res) => {
      if (cancelled) return;
      setRemote({
        runId,
        markers: res?.markers ?? null,
        tMax: res?.tMax ?? null,
        hasTrajectory: res?.hasTrajectory ?? false,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [client, enabled, runId, tl]);

  const fallbackMarkers = useMemo(() => markersFromStages(run), [run]);
  const markers = tl?.markers ?? fallbackMarkers;
  const tMax = tl?.tMax ?? run?.metrics.cycleTimeSimS ?? markers.at(-1)?.t ?? 1;
  const { t, playing } = cursor;

  const update = useCallback(
    (patch: Partial<Omit<Cursor, "runId">>) =>
      setCursor((prev) => ({ ...(prev.runId === runId ? prev : IDLE), ...patch, runId })),
    [runId],
  );

  useEffect(() => {
    if (!enabled || !hasTrajectory || !runId || clock === "video") return;
    const gen = ++seekGen.current;
    const handle = window.setTimeout(() => {
      void client.fetchRecordingFrame(runId, t).then((fr) => {
        if (gen === seekGen.current && fr) setFrame({ runId, frame: fr });
      });
    }, playing ? 100 : 30);
    return () => window.clearTimeout(handle);
  }, [client, enabled, hasTrajectory, runId, t, playing, clock]);

  useEffect(() => {
    if (!playing || clock === "video") return;
    const id = window.setInterval(() => {
      setCursor((prev) => {
        const next = prev.t + Math.max(tMax / 200, 0.05);
        return next >= tMax ? { ...prev, t: tMax, playing: false } : { ...prev, t: next };
      });
    }, 50);
    return () => window.clearInterval(id);
  }, [playing, tMax, clock]);

  const seek = useCallback(
    (next: number) => update({ t: Math.max(0, Math.min(next, tMax)), playing: false }),
    [update, tMax],
  );

  const togglePlay = useCallback(() => {
    if (playing) {
      update({ playing: false });
      return;
    }
    update(t >= tMax - 0.05 ? { t: 0, playing: true } : { playing: true });
  }, [playing, t, tMax, update]);

  const stepMarker = useCallback(
    (dir: -1 | 1) => {
      const stateMarkers = markers.filter((m) => m.state && !m.finished);
      if (!stateMarkers.length) return;
      let idx = 0;
      stateMarkers.forEach((m, i) => {
        if (m.t <= t) idx = i;
      });
      seek(stateMarkers[Math.max(0, Math.min(stateMarkers.length - 1, idx + dir))].t);
    },
    [markers, seek, t],
  );

  const reportTime = useCallback(
    (next: number) => update({ t: Math.max(0, Math.min(next, tMax)) }),
    [update, tMax],
  );

  const stages = useMemo(() => stagesForT(markers, t, tMax, run?.stages ?? []), [markers, t, tMax, run?.stages]);

  return {
    t,
    tMax,
    playing,
    loading,
    hasTrajectory,
    markers,
    stages,
    active: activeStateAt(markers, t),
    frameSrc: frame ? `data:${frame.mime};base64,${frame.imageBase64}` : null,
    seek,
    togglePlay,
    stepMarker,
    reportTime,
  };
}
