"use client";

import { useEffect, useRef, useState } from "react";
import {
  Camera,
  CameraOff,
  ChevronLeft,
  ChevronRight,
  FlaskConical,
  History,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  Radio,
} from "lucide-react";
import { CellSchematic } from "./CellSchematic";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { STAGE_ICONS } from "@/lib/stage-icons";
import { formatFlatness, formatSeconds, lifecycleLabel, stageLabel } from "@/lib/format";
import {
  useLiveViewport,
  type ViewportStatus,
} from "@/lib/use-live-viewport";
import type { RunReplay } from "@/lib/use-run-replay";
import type { DataProvenance, RunDetail } from "@/lib/types";

export function SimulationViewport({
  run,
  provenance,
  streamAvailable,
  bridgeUrl,
  replay,
}: {
  run: RunDetail | null;
  provenance: DataProvenance;
  streamAvailable: boolean;
  /** Direct bridge URL (fallback if Next proxy cannot reach it). */
  bridgeUrl?: string;
  /** When set, the viewport scrubs a finished run instead of showing the live stream. */
  replay?: RunReplay | null;
}) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    const sync = () => setFullscreen(document.fullscreenElement === stageRef.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void stageRef.current?.requestFullscreen();
  };

  const running = run?.lifecycle === "running";
  const showLive =
    !replay && streamAvailable && Boolean(bridgeUrl) && provenance !== "fixture";
  const live = running && showLive;
  const stage = replay ? replay.active : run?.currentState ?? null;
  const StageIcon = stage ? STAGE_ICONS[stage] : null;

  const viewport = useLiveViewport({
    enabled: showLive,
    bridgeUrl,
    waitMs: 1500,
  });

  return (
    <section className="flex min-h-0 flex-1 flex-col border border-divider bg-surface">
      <div className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-divider px-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <h2 className="truncate font-mono text-[13px] font-semibold tabular">
            {run ? run.id : "Sin ejecución"}
          </h2>
          {run?.seed != null ? (
            <span className="eyebrow hidden sm:inline">seed {run.seed}</span>
          ) : null}
          {live ? (
            <StatusBadge tone="active">En directo</StatusBadge>
          ) : null}
          {run && !running ? (
            <StatusBadge tone={run.lifecycle === "failed" ? "danger" : "neutral"}>
              {lifecycleLabel(run.lifecycle)}
            </StatusBadge>
          ) : null}
          {provenance === "fixture" ? (
            <StatusBadge tone="neutral" icon={<FlaskConical className="size-3" aria-hidden />}>
              Ejemplo
            </StatusBadge>
          ) : null}
          {showLive ? <ViewportStatusBadge status={viewport.status} /> : null}
          {replay?.loading ? <StatusBadge tone="neutral">Cargando replay</StatusBadge> : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-8"
            onClick={toggleFullscreen}
            aria-label={fullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
            title={fullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
          >
            {fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </Button>
        </div>
      </div>

      <div
        ref={stageRef}
        className="hud-corners viewport-focus relative min-h-[200px] flex-1 overflow-hidden bg-viewport text-hud"
      >
        <span className="hud-corner" aria-hidden />
        {live ? <div className="scanline" aria-hidden /> : null}

        {replay ? (
          replay.frameSrc ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={replay.frameSrc}
              alt={`Frame MuJoCo en t=${formatSeconds(replay.t)}`}
              className="absolute inset-0 h-full w-full object-contain"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center p-6">
              <CellSchematic stage={stage} />
            </div>
          )
        ) : showLive ? (
          viewport.src ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={viewport.src}
              alt="Vista MuJoCo de la celda XFold"
              className="absolute inset-0 h-full w-full object-contain"
            />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center font-mono text-[12px] uppercase tracking-[0.12em] text-hud-dim">
              <span>
                {viewport.status === "offline"
                  ? viewport.error ?? "Sin señal del viewport"
                  : "Cargando vista 3D…"}
              </span>
              {viewport.error && viewport.status !== "offline" ? (
                <span className="normal-case tracking-normal text-hud-dim/70">
                  {viewport.error}
                </span>
              ) : null}
            </div>
          )
        ) : (
          <div className="absolute inset-0 flex items-center justify-center p-6">
            <CellSchematic stage={stage} />
          </div>
        )}

        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between px-6 py-5">
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em]">
            {StageIcon ? (
              <span
                key={stage}
                className="hud-flash flex items-center gap-2 border border-hud/40 bg-black/50 px-2 py-1"
              >
                <StageIcon className="size-3.5" strokeWidth={1.75} aria-hidden />
                {stage ? stageLabel(stage) : null}
              </span>
            ) : (
              <span className="text-hud-dim">standby</span>
            )}
          </div>
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em]">
            {replay ? (
              <>
                <History className="size-3.5" strokeWidth={1.75} aria-hidden />
                <span>replay{replay.hasTrajectory ? " · mujoco" : " · fsm"}</span>
              </>
            ) : live ? (
              <>
                <span className="pulse-dot size-2 rounded-full bg-danger text-danger" aria-hidden />
                <span>live</span>
              </>
            ) : showLive ? (
              <>
                <Camera className="size-3.5" strokeWidth={1.75} aria-hidden />
                <span>
                  mujoco · long-poll
                  {viewport.seq ? ` · #${viewport.seq}` : ""}
                </span>
              </>
            ) : (
              <>
                <CameraOff className="size-3.5 text-hud-dim" strokeWidth={1.75} aria-hidden />
                <span className="text-hud-dim">esquema</span>
              </>
            )}
          </div>
        </div>

        {replay ? (
          <ReplayControls replay={replay} />
        ) : run?.telemetry ? (
          <dl className="pointer-events-none absolute inset-x-0 bottom-0 grid grid-cols-5 gap-x-3 border-t border-hud/15 bg-black/60 px-6 py-2.5 text-left backdrop-blur-[2px]">
            <Metric label="fase" value={stageLabel(run.telemetry.state)} />
            <Metric label="ciclo" value={String(run.telemetry.cycle)} />
            <Metric label="planitud" value={formatFlatness(run.telemetry.flatness)} />
            <Metric label="en bolsa" value={run.telemetry.shirt_in_bag ? "sí" : "no"} />
            <Metric label="t sim" value={formatSeconds(run.telemetry.t)} />
          </dl>
        ) : !run && !showLive ? (
          <p className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-2 px-6 py-3 font-mono text-[11px] uppercase tracking-[0.12em] text-hud-dim">
            <Radio className="size-3.5" strokeWidth={1.75} aria-hidden />
            Lanza un experimento para ver la celda
          </p>
        ) : null}
      </div>
    </section>
  );
}

/** Bottom HUD bar: transport + scrubber with FSM markers, synced to `replay.t`. */
function ReplayControls({ replay }: { replay: RunReplay }) {
  const pct = (t: number) => (replay.tMax > 0 ? (t / replay.tMax) * 100 : 0);
  return (
    <div className="absolute inset-x-0 bottom-0 flex items-center gap-3 border-t border-hud/15 bg-black/60 px-4 py-2 backdrop-blur-[2px]">
      <div className="flex shrink-0 items-center gap-0.5">
        <Button variant="ghost" size="icon-sm" className="size-7 text-hud hover:bg-hud/10 hover:text-hud" onClick={() => replay.stepMarker(-1)} aria-label="Fase anterior" title="Fase anterior">
          <ChevronLeft className="size-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" className="size-7 text-hud hover:bg-hud/10 hover:text-hud" onClick={replay.togglePlay} aria-label={replay.playing ? "Pausa" : "Reproducir"} title={replay.playing ? "Pausa" : "Reproducir"}>
          {replay.playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </Button>
        <Button variant="ghost" size="icon-sm" className="size-7 text-hud hover:bg-hud/10 hover:text-hud" onClick={() => replay.stepMarker(1)} aria-label="Fase siguiente" title="Fase siguiente">
          <ChevronRight className="size-4" />
        </Button>
      </div>

      <div className="relative min-w-0 flex-1">
        <div className="pointer-events-none absolute inset-x-0 top-1/2 h-3 -translate-y-1/2" aria-hidden>
          {replay.markers.filter((m) => m.state).map((m) => (
            <span
              key={`${m.seq ?? ""}-${m.t}-${m.state}`}
              className="absolute top-0 bottom-0 w-px -translate-x-1/2 bg-hud/50"
              style={{ left: `${pct(m.t)}%` }}
            />
          ))}
        </div>
        <input
          type="range"
          min={0}
          max={replay.tMax || 1}
          step={0.01}
          value={replay.t}
          onChange={(e) => replay.seek(Number(e.target.value))}
          aria-label="Tiempo simulado del replay"
          className="relative block w-full accent-[var(--color-hud)]"
        />
      </div>

      <span className="shrink-0 font-mono text-[11px] tabular text-hud">
        {formatSeconds(replay.t)} <span className="text-hud-dim">/ {formatSeconds(replay.tMax)}</span>
      </span>
    </div>
  );
}

function ViewportStatusBadge({ status }: { status: ViewportStatus }) {
  if (status === "live") return null;
  if (status === "waiting") {
    return <StatusBadge tone="neutral">Esperando frame</StatusBadge>;
  }
  if (status === "stale") {
    return <StatusBadge tone="pending">Vista stale</StatusBadge>;
  }
  if (status === "offline") {
    return <StatusBadge tone="danger">Sin cámara</StatusBadge>;
  }
  return null;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="font-mono text-[10px] uppercase tracking-[0.12em] text-hud-dim">{label}</dt>
      <dd key={value} className="value-tick truncate font-mono text-[13px] tabular text-hud">
        {value}
      </dd>
    </div>
  );
}
