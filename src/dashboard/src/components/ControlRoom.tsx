"use client";

import { useMemo, useRef, useState, useSyncExternalStore, type CSSProperties, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import type { PhaseId } from "@xfold/protocol";
import { AppShell } from "@/components/AppShell";
import { BatchContextPanel } from "@/components/BatchContextPanel";
import { ConsolePanel } from "@/components/ConsolePanel";
import { ProductShotPanel } from "@/components/ProductShotPanel";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { RunSummaryPanel } from "@/components/RunSummaryPanel";
import { SimulationViewport } from "@/components/SimulationViewport";
import { StageStepper } from "@/components/StageStepper";
import { useDashboard } from "@/lib/dashboard-context";
import type { FixtureScenario } from "@/lib/adapter";
import { consoleLines } from "@/lib/console";
import { formatSeconds, stageLabel } from "@/lib/format";
import type { RunLifecycle } from "@/lib/types";
import { useRunReplay } from "@/lib/use-run-replay";
import Link from "next/link";
import { ArrowUpRight, TriangleAlert } from "lucide-react";
import { Alert, AlertTitle, AlertDescription } from "./ui/alert";
import { Button } from "./ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "./ui/sheet";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { lifecycleLabel } from "@/lib/format";
import { NewExperimentDialog } from "@/components/NewExperimentDialog";

const SCENARIOS: { id: FixtureScenario; label: string }[] = [
  { id: "active", label: "Active" },
  { id: "empty", label: "Empty" },
  { id: "disconnected", label: "Disconnected" },
  { id: "failed", label: "Failed" },
  { id: "finished", label: "Finished" },
];

const INSPECTOR_KEY = "xfold.inspectorWidth";
const INSPECTOR_MIN = 260;
const INSPECTOR_MAX = 480;
const INSPECTOR_DEFAULT = 312;

const clamp = (n: number) => Math.min(INSPECTOR_MAX, Math.max(INSPECTOR_MIN, n));

const INSPECTOR_EVENT = "xfold:inspector-width";

function readStoredWidth() {
  const stored = Number(window.localStorage.getItem(INSPECTOR_KEY));
  return stored ? clamp(stored) : INSPECTOR_DEFAULT;
}

function subscribeStoredWidth(onChange: () => void) {
  window.addEventListener(INSPECTOR_EVENT, onChange);
  return () => window.removeEventListener(INSPECTOR_EVENT, onChange);
}

function writeStoredWidth(w: number) {
  window.localStorage.setItem(INSPECTOR_KEY, String(w));
  window.dispatchEvent(new Event(INSPECTOR_EVENT));
}

/** Persisted inspector width; live drag value overrides until pointer-up. */
function useInspectorWidth() {
  const stored = useSyncExternalStore(
    subscribeStoredWidth,
    readStoredWidth,
    () => INSPECTOR_DEFAULT,
  );
  const [drag, setDrag] = useState<number | null>(null);
  const width = drag ?? stored;
  const dragging = drag !== null;

  const commit = (next: number) => writeStoredWidth(clamp(next));

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startW = width;
    setDrag(startW);
    const move = (e: PointerEvent) => setDrag(clamp(startW + (startX - e.clientX)));
    const up = (e: PointerEvent) => {
      commit(startW + (startX - e.clientX));
      setDrag(null);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 40 : 16;
    if (event.key === "ArrowLeft") commit(width + step);
    else if (event.key === "ArrowRight") commit(width - step);
    else if (event.key === "Home") commit(INSPECTOR_MAX);
    else if (event.key === "End") commit(INSPECTOR_MIN);
    else return;
    event.preventDefault();
  };

  return { width, dragging, onPointerDown, onKeyDown };
}

const FINISHED = new Set<RunLifecycle>(["succeeded", "failed", "cancelled"]);

/**
 * Single run view. The active run gets the live stream + commands; a finished
 * run becomes a scrubbable replay of the same layout.
 */
export function ControlRoom({ runId }: { runId: string }) {
  const {
    snapshot,
    scenario,
    pendingCommand,
    setScenario,
    requestCommand,
    source,
    bridgeUrl,
    getRun,
    getJournal,
  } = useDashboard();
  const [selectedStage, setSelectedStage] = useState<PhaseId | null>(null);
  const stageTrigger = useRef<HTMLElement | null>(null);
  const inspector = useInspectorWidth();

  const run = getRun(runId);
  const journal = getJournal(runId);
  const consoleRows = useMemo(() => consoleLines(run, journal), [run, journal]);
  const finished = Boolean(run && FINISHED.has(run.lifecycle));
  const replay = useRunReplay({ run, enabled: finished, bridgeUrl });
  const isActive = Boolean(run && run.id === snapshot.activeRun?.id);
  const notFound = !run;

  const stageDetail =
    run && selectedStage
      ? run.stages.find((s) => s.state === selectedStage)
      : null;
  const stageEvents =
    run && selectedStage
      ? run.events.filter((e) => e.stage === selectedStage)
      : [];

  const selectStage = (state: PhaseId) => {
    if (finished) {
      setSelectedStage((prev) => (prev === state ? null : state));
      const marker = replay.markers.find((m) => m.state === state);
      if (marker) replay.seek(marker.t);
      return;
    }
    stageTrigger.current = document.activeElement as HTMLElement;
    setSelectedStage(state);
  };

  return (
    <AppShell
      title={run?.id ?? runId}
      eyebrow={run ? (run.name ?? undefined) : undefined}
      back={{ href: "/", label: "Runs" }}
      fit
      actions={
        <>
          <ConnectionBadge
            connection={snapshot.connection}
            provenance={snapshot.provenance}
            lastUpdatedIso={snapshot.lastUpdatedIso}
          />
          {!isActive && snapshot.activeRun ? (
            <Button asChild variant="outline" size="sm">
              <Link href={`/historial/${snapshot.activeRun.id}`}>
                View live <ArrowUpRight className="size-3.5" aria-hidden />
              </Link>
            </Button>
          ) : null}
          <NewExperimentDialog />
        </>
      }
    >
      {notFound ? (
        <Alert className="mb-3 py-2">
          <AlertTitle>Run not found</AlertTitle>
          <AlertDescription>
            No data for <span className="font-mono">{runId}</span>.
            <Link href="/" className="inline-flex items-center gap-1">
              View runs <ArrowUpRight className="size-3.5" aria-hidden />
            </Link>
          </AlertDescription>
        </Alert>
      ) : null}

      {snapshot.incident ? (
        <Alert variant="destructive" className="mb-3 py-2">
          <TriangleAlert className="size-4" />
          <AlertTitle>Incident</AlertTitle>
          <AlertDescription>
            {snapshot.incident.message}
            {snapshot.incident.runId && (
              <Link href={`/historial/${snapshot.incident.runId}`} className="inline-flex items-center gap-1">
                View run <ArrowUpRight className="size-3.5" aria-hidden />
              </Link>
            )}
          </AlertDescription>
        </Alert>
      ) : null}

      <div
        className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_12px_var(--inspector-width)] xl:gap-0"
        style={{ "--inspector-width": `${inspector.width}px` } as CSSProperties}
      >
        <div className="flex min-h-0 min-w-0 flex-col gap-3">
          <SimulationViewport
            run={run}
            provenance={snapshot.provenance}
            streamAvailable={snapshot.capabilities.viewportStream}
            bridgeUrl={bridgeUrl}
            replay={finished ? replay : null}
          />

          <section className="shrink-0 border border-divider bg-surface px-4 py-3">
            <StageStepper
              stages={finished ? replay.stages : run?.stages ?? null}
              selected={selectedStage}
              onSelect={selectStage}
            />
            <Sheet open={Boolean(selectedStage && run && !finished)} onOpenChange={(open) => { if (!open) setSelectedStage(null); }}>
              <SheetContent onCloseAutoFocus={(event) => { event.preventDefault(); stageTrigger.current?.focus(); }}>
                <SheetHeader>
                  <SheetTitle>{selectedStage ? stageLabel(selectedStage, run?.stages) : "Stage detail"}</SheetTitle>
                  <SheetDescription>{run?.id} · Stage trace</SheetDescription>
                </SheetHeader>
                <div className="flex flex-col gap-6 overflow-y-auto px-4 pb-6">
                  <dl className="grid grid-cols-2 gap-4 text-sm">
                    <div><dt className="text-muted-foreground">Status</dt><dd className="mt-1 font-medium">{stageDetail ? lifecycleLabel(stageDetail.status) : "Pending"}</dd></div>
                    <div><dt className="text-muted-foreground">Simulated duration</dt><dd className="mt-1 font-mono">{formatSeconds(stageDetail?.durationSimS ?? null)}</dd></div>
                  </dl>
                  <div><h3 className="mb-4 font-semibold">Events · {stageEvents.length}</h3>
                    {stageEvents.length ? <ol className="flex flex-col gap-4">{stageEvents.map(event => <li key={event.id} className="border-l-2 border-border pl-3"><p className="font-mono text-xs text-muted-foreground">t={formatSeconds(event.atSimS)}</p><p className="mt-1 text-sm">{event.message}</p></li>)}</ol> : <p className="text-sm text-muted-foreground">This stage has no events yet.</p>}
                  </div>
                </div>
              </SheetContent>
            </Sheet>
          </section>
        </div>

        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Side panel width"
          aria-valuemin={INSPECTOR_MIN}
          aria-valuemax={INSPECTOR_MAX}
          aria-valuenow={inspector.width}
          tabIndex={0}
          data-dragging={inspector.dragging}
          onPointerDown={inspector.onPointerDown}
          onKeyDown={inspector.onKeyDown}
          className="resize-handle hidden cursor-col-resize items-center justify-center outline-none xl:flex"
        >
          <span className="h-10 w-1 rounded-full bg-border opacity-70 transition-[background,opacity] duration-[var(--motion-feedback)]" />
        </div>

        <div className="flex min-h-0 min-w-0 flex-col gap-3">
          <div className="shrink-0 xl:max-h-[45%] xl:overflow-y-auto">
            {run && finished ? (
              <RunSummaryPanel run={run} />
            ) : (
              <BatchContextPanel
                batch={isActive ? snapshot.activeBatch : null}
                run={run}
                capabilities={snapshot.capabilities}
                pendingCommand={pendingCommand}
                disconnected={snapshot.connection === "disconnected"}
                onCommand={requestCommand}
              />
            )}
          </div>
          {run?.hasPhoto ? <ProductShotPanel key={run.id} run={run} /> : null}
          <ConsolePanel
            lines={consoleRows}
            running={run?.lifecycle === "running"}
            className="min-h-[220px] flex-1"
          />
        </div>
      </div>

      {source === "live" ? (
        <p className="eyebrow mt-3 shrink-0 truncate">
          live · {bridgeUrl} · journal + REST/SSE
        </p>
      ) : snapshot.provenance === "fixture" || snapshot.provenance === "stale" ? (
        <details className="mt-3 shrink-0">
          <summary className="eyebrow cursor-pointer">Demo scenarios · fixtures</summary>
          <ToggleGroup type="single" value={scenario} onValueChange={(value) => { if (value) setScenario(value as FixtureScenario); }} variant="outline" size="sm" className="mt-2 flex-wrap" aria-label="Demo scenario">
            {SCENARIOS.map(item => <ToggleGroupItem key={item.id} value={item.id}>{item.label}</ToggleGroupItem>)}
          </ToggleGroup>
        </details>
      ) : null}
    </AppShell>
  );
}
