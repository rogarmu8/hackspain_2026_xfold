"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PRODUCTIVE_CYCLE, type CellState } from "@xfold/protocol";
import { AppShell } from "@/components/AppShell";
import { StageStepper } from "@/components/StageStepper";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  bridgeBaseUrl,
  BridgeClient,
} from "@/lib/bridge-client";
import { useDashboard } from "@/lib/dashboard-context";
import { formatSeconds, stageLabel } from "@/lib/format";
import type {
  RecordingFrame,
  RunTimeline,
  StageProgress,
  TimelineMarker,
} from "@/lib/types";

function activeStateAt(markers: TimelineMarker[], t: number): CellState | null {
  let current: CellState | null = null;
  for (const m of markers) {
    if (m.t > t) break;
    if (m.state) current = m.state as CellState;
  }
  return current;
}

function stagesForT(
  markers: TimelineMarker[],
  t: number,
  tMax: number,
): StageProgress[] {
  const active = activeStateAt(markers, t);
  const byState = new Map<string, number>();
  for (const m of markers) {
    if (m.state) byState.set(m.state, m.t);
  }
  return PRODUCTIVE_CYCLE.map((state) => {
    const start = byState.get(state);
    if (start == null) {
      return {
        state,
        status: "pending" as const,
        startedAtSimS: null,
        durationSimS: null,
      };
    }
    if (active === state) {
      return {
        state,
        status: "active" as const,
        startedAtSimS: start,
        durationSimS: null,
      };
    }
    if (t >= start) {
      const next = PRODUCTIVE_CYCLE[PRODUCTIVE_CYCLE.indexOf(state) + 1];
      const nextT = next ? byState.get(next) : tMax;
      return {
        state,
        status: "completed" as const,
        startedAtSimS: start,
        durationSimS:
          nextT != null ? Math.max(0, nextT - start) : Math.max(0, t - start),
      };
    }
    return {
      state,
      status: "pending" as const,
      startedAtSimS: start,
      durationSimS: null,
    };
  });
}

export function RunReplayView({ runId }: { runId: string }) {
  const { getRun, bridgeUrl } = useDashboard();
  const run = getRun(runId);
  const clientRef = useRef<BridgeClient | null>(null);

  const [timeline, setTimeline] = useState<RunTimeline | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [frame, setFrame] = useState<RecordingFrame | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seekGen = useRef(0);

  const base = bridgeUrl || bridgeBaseUrl();

  useEffect(() => {
    const client = new BridgeClient(base);
    clientRef.current = client;
    let cancelled = false;
    (async () => {
      setLoading(true);
      const tl = await client.fetchTimeline(runId);
      if (cancelled) return;
      if (!tl) {
        setError("No hay timeline para esta ejecución (¿bridge offline?).");
        setLoading(false);
        return;
      }
      setTimeline(tl);
      setT(0);
      setLoading(false);
      if (tl.hasTrajectory) {
        const fr = await client.fetchRecordingFrame(runId, 0);
        if (!cancelled && fr) setFrame(fr);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId, base]);

  const tMax = timeline?.tMax ?? run?.metrics.cycleTimeSimS ?? 1;
  const markers = timeline?.markers ?? [];

  const fetchFrame = useCallback(
    async (at: number) => {
      if (!timeline?.hasTrajectory) return;
      const gen = ++seekGen.current;
      const client = clientRef.current ?? new BridgeClient(base);
      const fr = await client.fetchRecordingFrame(runId, at);
      if (gen !== seekGen.current) return;
      if (fr) setFrame(fr);
    },
    [base, runId, timeline?.hasTrajectory],
  );

  const seek = useCallback(
    async (nextT: number) => {
      const clamped = Math.max(0, Math.min(nextT, tMax));
      setT(clamped);
      await fetchFrame(clamped);
    },
    [fetchFrame, tMax],
  );

  useEffect(() => {
    if (!playing || !timeline) return;
    const id = window.setInterval(() => {
      setT((prev) => {
        const step = Math.max(tMax / 200, 0.05);
        const next = prev + step;
        if (next >= tMax) {
          setPlaying(false);
          return tMax;
        }
        return next;
      });
    }, 50);
    return () => window.clearInterval(id);
  }, [playing, timeline, tMax]);

  useEffect(() => {
    if (!timeline?.hasTrajectory) return;
    const handle = window.setTimeout(() => {
      void fetchFrame(t);
    }, playing ? 100 : 30);
    return () => window.clearTimeout(handle);
  }, [t, playing, timeline?.hasTrajectory, fetchFrame]);

  const active = activeStateAt(markers, t);
  const stages = useMemo(
    () => stagesForT(markers, t, tMax),
    [markers, t, tMax],
  );

  const stepMarker = (dir: -1 | 1) => {
    const stateMarkers = markers.filter((m) => m.state && !m.finished);
    if (!stateMarkers.length) return;
    let idx = 0;
    for (let i = 0; i < stateMarkers.length; i++) {
      if (stateMarkers[i].t <= t) idx = i;
    }
    const next = stateMarkers[Math.max(0, Math.min(stateMarkers.length - 1, idx + dir))];
    void seek(next.t);
  };

  return (
    <AppShell
      title={`Replay · ${runId}`}
      description={
        run?.name
          ? `${run.name} · semilla ${run.seed}`
          : "Trazabilidad FSM + trayectoria MuJoCo"
      }
      actions={
        <>
          <StatusBadge tone="neutral">Replay</StatusBadge>
          <Button asChild variant="outline">
            <Link href={`/historial/${runId}`}>Detalle</Link>
          </Button>
        </>
      }
    >
      {loading ? (
        <p className="text-sm text-muted-foreground">Cargando timeline…</p>
      ) : error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : (
        <>
          <section className="mb-4 border border-divider bg-surface p-4">
            <div className="relative min-h-[220px] bg-viewport text-surface">
              {frame ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`data:${frame.mime};base64,${frame.imageBase64}`}
                  alt={`Frame t=${frame.t.toFixed(2)}s`}
                  className="mx-auto max-h-[420px] w-auto object-contain"
                />
              ) : (
                <div className="flex min-h-[220px] items-center justify-center px-6 text-center text-sm text-surface/70">
                  {timeline?.hasTrajectory
                    ? "Sin frame en este instante"
                    : "Sin trayectoria 3D (MockDriver o run anterior). Los marcadores FSM siguen disponibles."}
                </div>
              )}
              <div className="pointer-events-none absolute top-2 left-2 bg-viewport/90 px-2 py-1 text-[11px] font-semibold tracking-wide uppercase">
                Replay · no live
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setPlaying((p) => !p)}
              >
                {playing ? "Pausa" : "Play"}
              </Button>
              <Button type="button" variant="outline" onClick={() => stepMarker(-1)}>
                ← Fase
              </Button>
              <Button type="button" variant="outline" onClick={() => stepMarker(1)}>
                Fase →
              </Button>
              <span className="ml-auto font-mono text-sm tabular text-muted-foreground">
                t = {formatSeconds(t)} / {formatSeconds(tMax)}
                {active ? ` · ${stageLabel(active)}` : null}
              </span>
            </div>

            <label className="mt-3 block">
              <span className="sr-only">Scrubber de tiempo simulado</span>
              <input
                type="range"
                min={0}
                max={tMax || 1}
                step={0.01}
                value={t}
                onChange={(e) => {
                  setPlaying(false);
                  void seek(Number(e.target.value));
                }}
                className="w-full accent-[var(--color-ink)]"
              />
            </label>

            {/* FSM marker track */}
            <div className="relative mt-2 h-8 border border-divider bg-surface">
              {markers
                .filter((m) => m.state)
                .map((m) => {
                  const pct = tMax > 0 ? (m.t / tMax) * 100 : 0;
                  return (
                    <button
                      key={`${m.seq}-${m.t}-${m.state}`}
                      type="button"
                      title={`${m.state} @ ${formatSeconds(m.t)}`}
                      onClick={() => {
                        setPlaying(false);
                        void seek(m.t);
                      }}
                      className="absolute top-0 bottom-0 w-0.5 -translate-x-1/2 bg-ink hover:w-1"
                      style={{ left: `${pct}%` }}
                      aria-label={`Ir a ${m.state}`}
                    />
                  );
                })}
              <div
                className="pointer-events-none absolute top-0 bottom-0 w-0.5 bg-active"
                style={{ left: `${tMax > 0 ? (t / tMax) * 100 : 0}%` }}
              />
            </div>
            <p className="mt-1 text-[12px] text-muted-foreground">
              Marcas = eventos <code className="font-mono">state_changed</code> del
              journal. Scrub sincroniza fase FSM y frame 3D.
            </p>
          </section>

          <section className="mb-6 border border-divider bg-surface p-4">
            <h2 className="mb-3 text-lg font-semibold">Etapas en t</h2>
            <StageStepper
              stages={stages}
              selected={active}
              onSelect={(state) => {
                const m = markers.find((x) => x.state === state);
                if (m) void seek(m.t);
              }}
            />
          </section>
        </>
      )}

      <p className="mt-6 text-sm">
        <Link
          href={`/historial/${runId}`}
          className="font-semibold underline-offset-2 hover:underline"
        >
          ← Detalle
        </Link>
        {" · "}
        <Link href="/historial" className="font-semibold underline-offset-2 hover:underline">
          Historial
        </Link>
      </p>
    </AppShell>
  );
}
