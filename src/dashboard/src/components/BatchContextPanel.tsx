"use client";

import Link from "next/link";
import { Progress } from "./ui/progress";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "./ui/alert-dialog";
import { useRef, useState } from "react";
import { Button } from "./ui/button";
import { StatusBadge } from "./ui/StatusBadge";
import type { PendingCommand } from "@/lib/adapter";
import type { BatchSummary, CommandKind, RunDetail, SimulatorCapabilities } from "@/lib/types";

export function BatchContextPanel({ batch, run, capabilities, pendingCommand, disconnected, onCommand }: {
  batch: BatchSummary | null; run: RunDetail | null; capabilities: SimulatorCapabilities;
  pendingCommand: PendingCommand | null; disconnected: boolean;
  onCommand: (kind: CommandKind, scope: string) => void;
}) {
  const [confirm, setConfirm] = useState<"run" | "batch" | null>(null);
  const cancelTrigger = useRef<HTMLElement | null>(null);
  function confirmCancel(scope: "run" | "batch") { cancelTrigger.current = document.activeElement as HTMLElement; setConfirm(scope); }
  const runActive = run && ["running", "paused"].includes(run.lifecycle);
  const batchActive = batch && ["running", "paused", "partial"].includes(batch.lifecycle);
  const pauseRun: CommandKind = run?.lifecycle === "paused" ? "resume_run" : "pause_run";
  const pauseBatch: CommandKind = batch?.lifecycle === "paused" ? "resume_batch" : "pause_batch";
  const disabled = (kind: CommandKind) => disconnected || Boolean(pendingCommand) || !capabilities.commands[kind];
  return <aside className="border border-divider bg-surface p-5">
    <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-muted-foreground">{batch ? "Experimento seleccionado" : "Ejecución individual"}</p>
    <h2 className="text-xl font-semibold">{batch?.name ?? run?.name ?? "Sin actividad"}</h2>
    <p className="mt-2 font-mono text-xs text-muted-foreground">{batch?.id ?? run?.id ?? "Todo listo para empezar"}</p>
    {batch && <>
      <div className="mt-6 flex items-baseline gap-2"><strong className="text-3xl font-semibold tabular">{batch.finished}<span className="text-lg font-normal text-muted-foreground"> / {batch.total}</span></strong><span className="text-sm text-muted-foreground">finalizadas</span></div>
      <Progress aria-label="Ejecuciones finalizadas" value={batch.total ? batch.finished / batch.total * 100 : 0} className="mt-3" />
      <p className="mt-2 text-xs text-muted-foreground">{batch.failed} fallidas · {batch.pending} pendientes</p>
      <div className="mt-6 border-t border-divider pt-4">
        <div className="flex justify-between text-sm"><h3 className="font-semibold">Próximas ejecuciones</h3><Link href={`/experimentos/${batch.id}`} className="underline underline-offset-4">Ver todas</Link></div>
        <ul className="mt-2 divide-y divide-divider">{batch.queuePreview.slice(0, 3).map(item => <li key={item.runId} className="flex justify-between py-3 text-xs"><span className="font-mono">{item.runId}</span><span className="text-muted-foreground">Semilla {item.seed}</span></li>)}</ul>
        {!batch.pending && <p className="mt-3 text-sm text-muted-foreground">No quedan ejecuciones en cola.</p>}
      </div>
    </>}
    {run && <div className="mt-5 border-t border-divider pt-5">
      <div className="mb-4 flex items-center justify-between gap-2"><span className="font-mono text-sm">{run.id}</span><StatusBadge tone={run.lifecycle === "failed" ? "danger" : "neutral"}>{({running:"En curso",paused:"En pausa",succeeded:"Correcta",failed:"Fallida",cancelled:"Cancelada",queued:"Pendiente"})[run.lifecycle]}</StatusBadge></div>
      {runActive && <div className="flex gap-2"><Button className="flex-1" variant="outline" disabled={disabled(pauseRun)} onClick={() => onCommand(pauseRun, `ejecución ${run.id}`)}>{run.lifecycle === "paused" ? "Reanudar" : "Pausar ejecución"}</Button><Button variant="ghost" disabled={disabled("cancel_run")} onClick={() => confirmCancel("run")}>Cancelar</Button></div>}
      <Link href={`/historial/${run.id}`} className="mt-4 block text-sm font-semibold underline-offset-4 hover:underline">Ver detalle de ejecución ↗</Link>
    </div>}
    {batchActive && <details className="mt-5 border-t border-divider pt-4"><summary className="cursor-pointer text-sm text-muted-foreground">Gestionar cola</summary><p className="my-3 text-xs text-muted-foreground">Pausar la cola conserva la ejecución actual.</p><div className="flex flex-col gap-2"><Button variant="outline" disabled={disabled(pauseBatch)} onClick={() => onCommand(pauseBatch, `cola ${batch.id}`)}>{batch.lifecycle === "paused" ? "Reanudar cola" : "Pausar cola"}</Button><Button variant="destructive" disabled={disabled("cancel_batch")} onClick={() => confirmCancel("batch")}>Cancelar batch</Button></div></details>}
    <AlertDialog open={Boolean(confirm)} onOpenChange={(open) => { if (!open) setConfirm(null); }}>
      <AlertDialogContent onCloseAutoFocus={(event) => { event.preventDefault(); cancelTrigger.current?.focus(); }}>
        <AlertDialogHeader><AlertDialogTitle>¿Cancelar {confirm === "batch" ? "el batch" : "la ejecución"}?</AlertDialogTitle><AlertDialogDescription>{confirm === "batch" ? "Se cancelarán la ejecución actual y todas las pendientes de este batch." : "Se cancelará solo esta ejecución. El resto del batch se conserva."}</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel>Volver</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={disconnected || Boolean(pendingCommand)} onClick={() => { onCommand(confirm === "batch" ? "cancel_batch" : "cancel_run", confirm === "batch" ? `batch ${batch?.id}` : `ejecución ${run?.id}`); }}>Cancelar {confirm === "batch" ? "batch" : "ejecución"}</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    {pendingCommand && <p role="status" className="mt-4 text-sm text-active-ink">Solicitud pendiente · {pendingCommand.scopeLabel}</p>}
    {disconnected && <p className="mt-4 text-sm text-danger">Sin conexión. Controles deshabilitados.</p>}
    {!run && !batch && <p className="mt-4 text-sm text-muted-foreground">Crea un experimento individual o un batch desde el botón superior.</p>}
  </aside>;
}
