"use client";

import { useRef, useState } from "react";
import type { CellState } from "@xfold/protocol";
import { AppShell } from "@/components/AppShell";
import { BatchContextPanel } from "@/components/BatchContextPanel";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { SimulationViewport } from "@/components/SimulationViewport";
import { StageStepper } from "@/components/StageStepper";
import { useDashboard } from "@/lib/dashboard-context";
import type { FixtureScenario } from "@/lib/adapter";
import { formatSeconds, stageLabel } from "@/lib/format";
import Link from "next/link";
import { PlusIcon } from "lucide-react";
import { Button } from "./ui/button";
import { Alert, AlertTitle, AlertDescription } from "./ui/alert";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "./ui/sheet";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { lifecycleLabel } from "@/lib/format";

const SCENARIOS: { id: FixtureScenario; label: string }[] = [
  { id: "active", label: "Activo" },
  { id: "empty", label: "Vacío" },
  { id: "disconnected", label: "Desconectado" },
  { id: "failed", label: "Fallido" },
  { id: "finished", label: "Finalizado" },
];

export function ControlRoom() {
  const { snapshot, scenario, pendingCommand, setScenario, requestCommand } =
    useDashboard();
  const [selectedStage, setSelectedStage] = useState<CellState | null>(null);
  const stageTrigger = useRef<HTMLElement | null>(null);

  const run = snapshot.activeRun;
  const stageDetail =
    run && selectedStage
      ? run.stages.find((s) => s.state === selectedStage)
      : null;
  const stageEvents =
    run && selectedStage
      ? run.events.filter((e) => e.stage === selectedStage)
      : [];

  return (
    <AppShell
      title="Centro de control"
      description="Celda OpenArm · prensa · pliegue ninja · tolva → bolsa"
      actions={
        <>
          <ConnectionBadge
            connection={snapshot.connection}
            provenance={snapshot.provenance}
            lastUpdatedIso={snapshot.lastUpdatedIso}
          />
          <Button asChild><Link href="/experimentos/nuevo"><PlusIcon data-icon="inline-start" />Nuevo experimento</Link></Button>
        </>
      }
    >
      {snapshot.incident ? (
        <Alert variant="destructive" className="mb-6">
          <AlertTitle>Incidencia</AlertTitle>
          <AlertDescription>{snapshot.incident.message}
            {snapshot.incident.runId && <Link href={`/historial/${snapshot.incident.runId}`}>Ver ejecución</Link>}
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_var(--inspector-width)]">
        <div className="flex min-w-0 flex-col gap-6">
          <SimulationViewport
            run={run}
            provenance={snapshot.provenance}
            streamAvailable={snapshot.capabilities.viewportStream}
          />

          <section className="border border-divider bg-surface p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">Etapas del proceso</h2>

            </div>
            <StageStepper
              stages={run?.stages ?? null}
              selected={selectedStage}
              onSelect={(state) => { stageTrigger.current = document.activeElement as HTMLElement; setSelectedStage(state); }}
            />
            <Sheet open={Boolean(selectedStage && run)} onOpenChange={(open) => { if (!open) setSelectedStage(null); }}>
              <SheetContent onCloseAutoFocus={(event) => { event.preventDefault(); stageTrigger.current?.focus(); }}>
                <SheetHeader>
                  <SheetTitle>{selectedStage ? stageLabel(selectedStage) : "Detalle de etapa"}</SheetTitle>
                  <SheetDescription>{run?.id} · Trazabilidad de la etapa</SheetDescription>
                </SheetHeader>
                <div className="flex flex-col gap-6 overflow-y-auto px-4 pb-6">
                  <dl className="grid grid-cols-2 gap-4 text-sm">
                    <div><dt className="text-muted-foreground">Estado</dt><dd className="mt-1 font-medium">{stageDetail ? lifecycleLabel(stageDetail.status) : "Pendiente"}</dd></div>
                    <div><dt className="text-muted-foreground">Duración simulada</dt><dd className="mt-1 font-mono">{formatSeconds(stageDetail?.durationSimS ?? null)}</dd></div>
                  </dl>
                  <div><h3 className="mb-4 font-semibold">Eventos · {stageEvents.length}</h3>
                    {stageEvents.length ? <ol className="flex flex-col gap-4">{stageEvents.map(event => <li key={event.id} className="border-l-2 border-border pl-3"><p className="font-mono text-xs text-muted-foreground">t={formatSeconds(event.atSimS)}</p><p className="mt-1 text-sm">{event.message}</p></li>)}</ol> : <p className="text-sm text-muted-foreground">Esta etapa todavía no tiene eventos registrados.</p>}
                  </div>
                </div>
              </SheetContent>
            </Sheet>
          </section>
        </div>

        <div className="min-w-0 xl:sticky xl:top-[calc(var(--header-height)+24px)] xl:self-start">
          <BatchContextPanel
            batch={snapshot.activeBatch}
            run={run}
            capabilities={snapshot.capabilities}
            pendingCommand={pendingCommand}
            disconnected={snapshot.connection === "disconnected"}
            onCommand={requestCommand}
          />
        </div>
      </div>

      {snapshot.provenance === "fixture" || snapshot.provenance === "stale" ? (
        <details className="mt-8 border-t border-divider pt-4"><summary className="cursor-pointer text-sm text-muted-foreground">Escenarios de demostración</summary>
          <ToggleGroup type="single" value={scenario} onValueChange={(value) => { if (value) setScenario(value as FixtureScenario); }} variant="outline" className="mt-3 flex-wrap" aria-label="Escenario de demostración">
            {SCENARIOS.map(item => <ToggleGroupItem key={item.id} value={item.id}>{item.label}</ToggleGroupItem>)}
          </ToggleGroup>
        </details>
      ) : null}
    </AppShell>
  );
}
