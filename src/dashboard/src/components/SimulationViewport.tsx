"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Camera,
  CameraOff,
  FlaskConical,
  Maximize2,
  Minimize2,
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
import type { DataProvenance, RunDetail } from "@/lib/types";

export function SimulationViewport({
  run,
  provenance,
  streamAvailable,
  bridgeUrl,
}: {
  run: RunDetail | null;
  provenance: DataProvenance;
  streamAvailable: boolean;
  /** Direct bridge URL (fallback if Next proxy cannot reach it). */
  bridgeUrl?: string;
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
    streamAvailable && Boolean(bridgeUrl) && provenance !== "fixture";
  const live = running && showLive;
  const stage = run?.currentState ?? null;
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
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {run ? (
            <Button asChild variant="ghost" size="sm" className="h-8 gap-1.5 px-2 text-xs">
              <Link href={`/historial/${run.id}`}>
                Detalle <ArrowUpRight className="size-3.5" aria-hidden />
              </Link>
            </Button>
          ) : null}
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

        {showLive ? (
          viewport.src ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={viewport.src}
              alt="Vista MuJoCo de la celda XFOLD"
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
            {live ? (
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

        {run?.telemetry ? (
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
