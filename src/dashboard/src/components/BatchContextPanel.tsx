"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import {
  ArrowUpRight,
  Layers,
  LoaderCircle,
  Pause,
  Play,
  Plug,
  Square,
  X,
} from "lucide-react";
import { Progress } from "./ui/progress";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "./ui/alert-dialog";
import { Button } from "./ui/button";
import { StatusBadge } from "./ui/StatusBadge";
import { lifecycleLabel } from "@/lib/format";
import type { PendingCommand } from "@/lib/adapter";
import type { BatchSummary, CommandKind, RunDetail, SimulatorCapabilities } from "@/lib/types";

export function BatchContextPanel({
  batch,
  run,
  capabilities,
  pendingCommand,
  disconnected,
  onCommand,
}: {
  batch: BatchSummary | null;
  run: RunDetail | null;
  capabilities: SimulatorCapabilities;
  pendingCommand: PendingCommand | null;
  disconnected: boolean;
  onCommand: (kind: CommandKind, scope: string) => void;
}) {
  const [confirm, setConfirm] = useState<"run" | "batch" | null>(null);
  const cancelTrigger = useRef<HTMLElement | null>(null);
  function confirmCancel(scope: "run" | "batch") {
    cancelTrigger.current = document.activeElement as HTMLElement;
    setConfirm(scope);
  }

  const runActive = run && ["running", "paused"].includes(run.lifecycle);
  const batchActive = batch && ["running", "paused", "partial"].includes(batch.lifecycle);
  const pauseRun: CommandKind = run?.lifecycle === "paused" ? "resume_run" : "pause_run";
  const pauseBatch: CommandKind = batch?.lifecycle === "paused" ? "resume_batch" : "pause_batch";
  const disabled = (kind: CommandKind) =>
    disconnected || Boolean(pendingCommand) || !capabilities.commands[kind];
  const pending = (kind: CommandKind) => pendingCommand?.kind === kind;

  return (
    <aside className="flex flex-col gap-4 border border-divider bg-surface p-4">
      <header>
        <p className="eyebrow flex items-center gap-1.5">
          <Layers className="size-3.5" strokeWidth={1.75} aria-hidden />
          {batch ? "Batch" : run ? "Ejecución" : "Inactivo"}
        </p>
        <h2 className="mt-1.5 truncate text-[17px] font-semibold leading-tight">
          {batch?.name ?? run?.name ?? "Sin actividad"}
        </h2>
        {(batch?.id ?? run?.id) ? (
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">{batch?.id ?? run?.id}</p>
        ) : null}
      </header>

      {batch && (
        <div>
          <div className="flex items-baseline justify-between">
            <strong className="text-[28px] font-semibold leading-none tabular">
              {batch.finished}
              <span className="text-base font-normal text-muted-foreground"> / {batch.total}</span>
            </strong>
            <span className="font-mono text-[11px] tabular text-muted-foreground">
              {batch.failed} err · {batch.pending} cola
            </span>
          </div>
          <Progress
            aria-label="Ejecuciones finalizadas"
            value={batch.total ? (batch.finished / batch.total) * 100 : 0}
            className="mt-3"
          />
          <div className="mt-4 flex items-center justify-between">
            <h3 className="eyebrow">Cola</h3>
            <Link
              href={`/experimentos/${batch.id}`}
              className="inline-flex items-center gap-1 text-xs font-semibold text-ink"
            >
              Todas <ArrowUpRight className="size-3.5" aria-hidden />
            </Link>
          </div>
          {batch.queuePreview.length ? (
            <ul className="mt-1 divide-y divide-divider">
              {batch.queuePreview.slice(0, 3).map((item) => (
                <li key={item.runId} className="flex justify-between py-2 font-mono text-xs">
                  <span>{item.runId}</span>
                  <span className="text-muted-foreground">seed {item.seed}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">Cola vacía.</p>
          )}
        </div>
      )}

      {run && (
        <div className="border-t border-divider pt-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="font-mono text-sm">{run.id}</span>
            <StatusBadge
              tone={
                run.lifecycle === "failed"
                  ? "danger"
                  : run.lifecycle === "running"
                    ? "active"
                    : "neutral"
              }
            >
              {lifecycleLabel(run.lifecycle)}
            </StatusBadge>
          </div>
          {runActive && (
            <div className="flex gap-2">
              <Button
                className="flex-1"
                size="sm"
                variant="outline"
                disabled={disabled(pauseRun)}
                onClick={() => onCommand(pauseRun, `ejecución ${run.id}`)}
              >
                <ActionIcon busy={pending(pauseRun)} Icon={run.lifecycle === "paused" ? Play : Pause} />
                {run.lifecycle === "paused" ? "Reanudar" : "Pausar"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={disabled("cancel_run")}
                onClick={() => confirmCancel("run")}
                aria-label="Cancelar ejecución"
                title="Cancelar ejecución"
              >
                <ActionIcon busy={pending("cancel_run")} Icon={Square} />
                Cancelar
              </Button>
            </div>
          )}
        </div>
      )}

      {batchActive && (
        <details className="border-t border-divider pt-3">
          <summary className="eyebrow cursor-pointer">Gestionar cola</summary>
          <div className="mt-3 flex gap-2">
            <Button
              className="flex-1"
              size="sm"
              variant="outline"
              disabled={disabled(pauseBatch)}
              onClick={() => onCommand(pauseBatch, `cola ${batch.id}`)}
            >
              <ActionIcon busy={pending(pauseBatch)} Icon={batch.lifecycle === "paused" ? Play : Pause} />
              {batch.lifecycle === "paused" ? "Reanudar cola" : "Pausar cola"}
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={disabled("cancel_batch")}
              onClick={() => confirmCancel("batch")}
            >
              <ActionIcon busy={pending("cancel_batch")} Icon={X} />
              Batch
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Pausar la cola conserva la ejecución actual.</p>
        </details>
      )}

      <AlertDialog open={Boolean(confirm)} onOpenChange={(open) => { if (!open) setConfirm(null); }}>
        <AlertDialogContent onCloseAutoFocus={(event) => { event.preventDefault(); cancelTrigger.current?.focus(); }}>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Cancelar {confirm === "batch" ? "el batch" : "la ejecución"}?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === "batch"
                ? "Se cancelarán la ejecución actual y todas las pendientes de este batch."
                : "Se cancelará solo esta ejecución. El resto del batch se conserva."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Volver</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={disconnected || Boolean(pendingCommand)}
              onClick={() => {
                onCommand(
                  confirm === "batch" ? "cancel_batch" : "cancel_run",
                  confirm === "batch" ? `batch ${batch?.id}` : `ejecución ${run?.id}`,
                );
              }}
            >
              Cancelar {confirm === "batch" ? "batch" : "ejecución"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {pendingCommand && (
        <p role="status" className="flex items-center gap-2 text-xs text-active-ink">
          <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
          Enviando · {pendingCommand.scopeLabel}
        </p>
      )}
      {disconnected && (
        <p className="flex items-center gap-2 text-xs text-danger">
          <Plug className="size-3.5" aria-hidden />
          Sin conexión · controles bloqueados
        </p>
      )}
      {!run && !batch && (
        <p className="text-xs text-muted-foreground">
          Lanza un experimento o batch desde «Nuevo experimento».
        </p>
      )}
    </aside>
  );
}

function ActionIcon({ busy, Icon }: { busy: boolean; Icon: typeof Pause }) {
  return busy ? (
    <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
  ) : (
    <Icon className="size-3.5" aria-hidden />
  );
}
