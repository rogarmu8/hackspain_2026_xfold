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
import { XFoldLoader } from "@/components/XFoldLoader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Button } from "@/components/ui/button";
import { RunStatusBadges } from "@/components/RunStatusBadges";
import { STAGE_ICONS, DEFAULT_STAGE_ICON } from "@/lib/stage-icons";
import { formatFlatness, formatSeconds, operatorStepTitle, runGarmentLabel, runGarmentTone } from "@/lib/format";
import {
  useLiveViewport,
  type ViewportStatus,
} from "@/lib/use-live-viewport";
import { RunVideoPlayer, type Status as VideoStatus } from "@/components/RunVideoPlayer";
import type { RunReplay } from "@/lib/use-run-replay";
import type { DataProvenance, RunDetail } from "@/lib/types";

export function SimulationViewport({
  run,
  provenance,
  streamAvailable,
  liveVideo = true,
  engine = "mujoco",
  bridgeUrl,
  replay,
}: {
  run: RunDetail | null;
  provenance: DataProvenance;
  streamAvailable: boolean;
  /** The recording can be watched while the run is live (false: frames live, video after). */
  liveVideo?: boolean;
  /** Physics engine behind the view, for the labels. */
  engine?: string;
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
  // Recorded runs stay black until HLS is playing at the live edge. Showing
  // the JPEG stream first, then swapping to the playlist from t=0, looks
  // like the video restarting. An engine slower than realtime (Isaac) fills a
  // segment far slower than the player drains it, so there the live view is
  // the JPEG frames and the recording only plays once the run is over.
  const showVideo =
    Boolean(run?.hasVideo) && provenance !== "fixture" && !(running && !liveVideo);
  const engineName = engine === "isaac" ? "Isaac Sim" : "MuJoCo";
  const [videoStatus, setVideoStatus] = useState<VideoStatus>("waiting");
  useEffect(() => {
    setVideoStatus("waiting");
  }, [run?.id]);
  const videoUp = showVideo && videoStatus === "ready";
  const videoBuffering = showVideo && videoStatus === "waiting";
  const showJpeg =
    !replay &&
    !showVideo &&
    streamAvailable &&
    Boolean(bridgeUrl) &&
    provenance !== "fixture";
  const live = running && !replay;
  const stage = replay ? replay.active : run?.currentState ?? null;
  const StageIcon = stage ? STAGE_ICONS[stage] ?? DEFAULT_STAGE_ICON : null;

  const viewport = useLiveViewport({
    enabled: showJpeg,
    bridgeUrl,
    waitMs: 1500,
  });

  return (
    <section className="flex min-h-0 flex-1 flex-col border border-divider bg-surface">
      <div className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-divider px-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <h2 className="truncate font-mono text-[13px] font-semibold tabular">
            {run ? run.id : "No run"}
          </h2>
          {run?.seed != null ? (
            <span className="eyebrow hidden sm:inline">seed {run.seed}</span>
          ) : null}
          {live ? (
            <StatusBadge tone="active">Live</StatusBadge>
          ) : run ? (
            <RunStatusBadges run={run} />
          ) : null}
          {live && run && runGarmentLabel(run) ? (
            <StatusBadge tone={runGarmentTone(run)}>{runGarmentLabel(run)}</StatusBadge>
          ) : null}
          {provenance === "fixture" ? (
            <StatusBadge tone="neutral" icon={<FlaskConical className="size-3" aria-hidden />}>
              Sample
            </StatusBadge>
          ) : null}
          {showJpeg ? <ViewportStatusBadge status={viewport.status} /> : null}
          {replay?.loading ? <StatusBadge tone="neutral">Loading replay</StatusBadge> : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-8"
            onClick={toggleFullscreen}
            aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"}
            title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
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

        {showVideo && run ? (
          <RunVideoPlayer
            runId={run.id}
            live={running}
            transport={
              replay && !running
                ? {
                    t: replay.t,
                    playing: replay.playing,
                    onTime: replay.reportTime,
                    onEnded: () => replay.seek(replay.tMax),
                  }
                : undefined
            }
            onStatus={setVideoStatus}
            className={`absolute inset-0 h-full w-full object-contain ${videoUp ? "z-10" : "pointer-events-none opacity-0"}`}
          />
        ) : null}
        {videoBuffering ? (
          <div className="absolute inset-0 z-[5] flex items-center justify-center">
            <XFoldLoader size={72} decorative tone="dark" surface="var(--viewport)" />
          </div>
        ) : null}
        {videoUp || videoBuffering ? null : replay ? (
          replay.frameSrc ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={replay.frameSrc}
              alt={`${engineName} frame at t=${formatSeconds(replay.t)}`}
              className="absolute inset-0 h-full w-full object-contain"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center p-6">
              <CellSchematic stage={stage} stages={run?.stages} />
            </div>
          )
        ) : showJpeg ? (
          viewport.src ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={viewport.src}
              alt={`${engineName} view of the XFold cell`}
              className="absolute inset-0 h-full w-full object-contain"
            />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center font-mono text-[12px] uppercase tracking-[0.12em] text-hud-dim">
              {viewport.status !== "offline" ? (
                <XFoldLoader size={72} decorative tone="dark" surface="var(--viewport)" />
              ) : null}
              <span>
                {viewport.status === "offline"
                  ? viewport.error ?? "No viewport signal"
                  : "Loading 3D view…"}
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
            <CellSchematic stage={stage} stages={run?.stages} />
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
                {stage ? operatorStepTitle(stage, run?.stages) : null}
              </span>
            ) : (
              <span className="text-hud-dim">standby</span>
            )}
          </div>
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em]">
            {videoUp ? (
              <>
                {running ? (
                  <span className="pulse-dot size-2 rounded-full bg-danger text-danger" aria-hidden />
                ) : (
                  <History className="size-3.5" strokeWidth={1.75} aria-hidden />
                )}
                <span>{running ? "live" : "replay"}</span>
              </>
            ) : replay ? (
              <>
                <History className="size-3.5" strokeWidth={1.75} aria-hidden />
                <span>replay{replay.hasTrajectory ? run?.config.inputs?.driver === "line" ? " partial · qpos" : " · mujoco" : " · phases"}</span>
              </>
            ) : live ? (
              <>
                <span className="pulse-dot size-2 rounded-full bg-danger text-danger" aria-hidden />
                <span>live</span>
              </>
            ) : showJpeg ? (
              <>
                <Camera className="size-3.5" strokeWidth={1.75} aria-hidden />
                <span>
                  {engine} · long-poll
                  {viewport.seq ? ` · #${viewport.seq}` : ""}
                </span>
              </>
            ) : (
              <>
                <CameraOff className="size-3.5 text-hud-dim" strokeWidth={1.75} aria-hidden />
                <span className="text-hud-dim">schematic</span>
              </>
            )}
          </div>
        </div>

        {!replay && run?.telemetry?.operation ? (
          <div className="pointer-events-none absolute inset-x-6 top-16 z-20 max-w-xl bg-black/50 px-2 py-1 font-mono text-[11px] text-hud">
            <p>{run.telemetry.operation.message}</p>
            {run.telemetry.activities?.map((activity) => <p key={activity.station} className="text-hud-dim">{activity.station} · last parallel hit: {activity.message}</p>)}
          </div>
        ) : null}
        {replay ? (
          <ReplayControls replay={replay} />
        ) : run?.telemetry && !videoUp ? (
          <dl className="pointer-events-none absolute inset-x-0 bottom-0 grid grid-cols-5 gap-x-3 border-t border-hud/15 bg-black/60 px-6 py-2.5 text-left backdrop-blur-[2px]">
            <Metric label="operation" value={run.telemetry.operation?.id ?? operatorStepTitle(run.telemetry.state, run.stages)} />
            <Metric label="cycle" value={String(run.telemetry.cycle)} />
            <Metric label="flatness" value={formatFlatness(run.telemetry.flatness)} />
            <Metric label="in bag" value={run.telemetry.shirt_in_bag == null ? "not measured" : run.telemetry.shirt_in_bag ? "yes" : "no"} />
            <Metric label="sim t" value={formatSeconds(run.telemetry.t)} />
          </dl>
        ) : !run && !showJpeg ? (
          <p className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center gap-2 px-6 py-3 font-mono text-[11px] uppercase tracking-[0.12em] text-hud-dim">
            <Radio className="size-3.5" strokeWidth={1.75} aria-hidden />
            Launch an experiment to see the cell
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
    <div className="absolute inset-x-0 bottom-0 z-20 flex items-center gap-3 border-t border-hud/15 bg-black/60 px-4 py-2 backdrop-blur-[2px]">
      <div className="flex shrink-0 items-center gap-0.5">
        <Button variant="ghost" size="icon-sm" className="size-7 text-hud hover:bg-hud/10 hover:text-hud" onClick={() => replay.stepMarker(-1)} aria-label="Previous phase" title="Previous phase">
          <ChevronLeft className="size-4" />
        </Button>
        <Button variant="ghost" size="icon-sm" className="size-7 text-hud hover:bg-hud/10 hover:text-hud" onClick={replay.togglePlay} aria-label={replay.playing ? "Pause" : "Play"} title={replay.playing ? "Pause" : "Play"}>
          {replay.playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </Button>
        <Button variant="ghost" size="icon-sm" className="size-7 text-hud hover:bg-hud/10 hover:text-hud" onClick={() => replay.stepMarker(1)} aria-label="Next phase" title="Next phase">
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
          aria-label="Replay simulated time"
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
    return <StatusBadge tone="neutral">Waiting for frame</StatusBadge>;
  }
  if (status === "stale") {
    return <StatusBadge tone="pending">Stale view</StatusBadge>;
  }
  if (status === "offline") {
    return <StatusBadge tone="danger">No camera</StatusBadge>;
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
