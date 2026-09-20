"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import {
  ArrowUpRight,
  Layers,
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
import { XFoldLoader } from "@/components/XFoldLoader";
import { RunStatusBadges } from "@/components/RunStatusBadges";
import type { PendingCommand } from "@/lib/dashboard-context";
import type { BatchSummary, CommandKind, RunDetail, SimulatorCapabilities } from "@/lib/types";

export function BatchContextPanel({
  batch,
  run,
  capabilities,
  pendingCommand,
  disconnected,
  onCommand,
  embed = false,
}: {
  batch: BatchSummary | null;
  run: RunDetail | null;
  capabilities: SimulatorCapabilities;
  pendingCommand: PendingCommand | null;
  disconnected: boolean;
  onCommand: (kind: CommandKind, scope: string) => void;
  embed?: boolean;
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
    <aside className={embed ? "flex flex-col gap-4 overflow-y-auto p-4" : "flex flex-col gap-4 border border-divider bg-surface p-4"}>
      {embed ? (
        <div>
          <h3 className="truncate text-[17px] font-semibold leading-tight">
            {batch?.name ?? run?.name ?? "No activity"}
          </h3>
          {(batch?.id ?? run?.id) ? (
            <p className="mt-0.5 font-mono text-xs text-muted-foreground">{batch?.id ?? run?.id}</p>
          ) : null}
        </div>
      ) : (
      <header>
        <p className="eyebrow flex items-center gap-1.5">
          <Layers className="size-3.5" strokeWidth={1.75} aria-hidden />
          {batch ? "Batch" : run ? "Run" : "Idle"}
        </p>
        <h2 className="mt-1.5 truncate text-[17px] font-semibold leading-tight">
          {batch?.name ?? run?.name ?? "No activity"}
        </h2>
        {(batch?.id ?? run?.id) ? (
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">{batch?.id ?? run?.id}</p>
        ) : null}
      </header>
      )}

      {batch && (
        <div>
          <div className="flex items-baseline justify-between">
            <strong className="text-[28px] font-semibold leading-none tabular">
              {batch.finished}
              <span className="text-base font-normal text-muted-foreground"> / {batch.total}</span>
            </strong>
            <span className="font-mono text-[11px] tabular text-muted-foreground">
              {batch.failed} err · {batch.pending} queued
            </span>
          </div>
          <Progress
            aria-label="Finished runs"
            value={batch.total ? (batch.finished / batch.total) * 100 : 0}
            className="mt-3"
          />
          <div className="mt-4 flex items-center justify-between">
            <h3 className="eyebrow">Queue</h3>
            <Link
              href={`/experimentos/${batch.id}`}
              className="inline-flex items-center gap-1 text-xs font-semibold text-ink"
            >
              All <ArrowUpRight className="size-3.5" aria-hidden />
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
            <p className="mt-2 text-xs text-muted-foreground">Queue empty.</p>
          )}
        </div>
      )}

      {run && (
        <div className="border-t border-divider pt-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <span className="font-mono text-sm">{run.id}</span>
            <RunStatusBadges run={run} />
          </div>
          {runActive && (
            <div className="flex gap-2">
              <Button
                className="flex-1"
                size="sm"
                variant="outline"
                disabled={disabled(pauseRun)}
                onClick={() => onCommand(pauseRun, `run ${run.id}`)}
              >
                <ActionIcon busy={pending(pauseRun)} Icon={run.lifecycle === "paused" ? Play : Pause} />
                {run.lifecycle === "paused" ? "Resume" : "Pause"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={disabled("cancel_run")}
                onClick={() => confirmCancel("run")}
                aria-label="Cancel run"
                title="Cancel run"
              >
                <ActionIcon busy={pending("cancel_run")} Icon={Square} />
                Cancel
              </Button>
            </div>
          )}
        </div>
      )}

      {batchActive && (
        <details className="border-t border-divider pt-3">
          <summary className="eyebrow cursor-pointer">Manage queue</summary>
          <div className="mt-3 flex gap-2">
            <Button
              className="flex-1"
              size="sm"
              variant="outline"
              disabled={disabled(pauseBatch)}
              onClick={() => onCommand(pauseBatch, `queue ${batch.id}`)}
            >
              <ActionIcon busy={pending(pauseBatch)} Icon={batch.lifecycle === "paused" ? Play : Pause} />
              {batch.lifecycle === "paused" ? "Resume queue" : "Pause queue"}
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
          <p className="mt-2 text-xs text-muted-foreground">Pausing the queue keeps the current run.</p>
        </details>
      )}

      <AlertDialog open={Boolean(confirm)} onOpenChange={(open) => { if (!open) setConfirm(null); }}>
        <AlertDialogContent onCloseAutoFocus={(event) => { event.preventDefault(); cancelTrigger.current?.focus(); }}>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel {confirm === "batch" ? "the batch" : "the run"}?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === "batch"
                ? "The current run and every pending run in this batch will be cancelled."
                : "Only this run will be cancelled. The rest of the batch is kept."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Back</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={disconnected || Boolean(pendingCommand)}
              onClick={() => {
                onCommand(
                  confirm === "batch" ? "cancel_batch" : "cancel_run",
                  confirm === "batch" ? `batch ${batch?.id}` : `run ${run?.id}`,
                );
              }}
            >
              Cancel {confirm === "batch" ? "batch" : "run"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {pendingCommand && (
        <p role="status" className="flex items-center gap-2 text-xs text-active-ink">
          <XFoldLoader size={14} decorative className="shrink-0" />
          Sending · {pendingCommand.scopeLabel}
        </p>
      )}
      {disconnected && (
        <p className="flex items-center gap-2 text-xs text-danger">
          <Plug className="size-3.5" aria-hidden />
          Offline · controls locked
        </p>
      )}
      {!run && !batch && (
        <p className="text-xs text-muted-foreground">
          Launch an experiment or batch from “New experiment”.
        </p>
      )}
    </aside>
  );
}

function ActionIcon({ busy, Icon }: { busy: boolean; Icon: typeof Pause }) {
  return busy ? (
    <XFoldLoader size={14} decorative className="shrink-0" />
  ) : (
    <Icon className="size-3.5" aria-hidden />
  );
}
