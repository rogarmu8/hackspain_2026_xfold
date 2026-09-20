"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { MoreHorizontal, RotateCcw, Square, Trash2 } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useDashboard } from "@/lib/dashboard-context";
import {
  DEFAULT_CLOTH_CONDITIONS,
  DEFAULT_CLOTH_TYPES,
} from "@/lib/format";
import type { RunSummary } from "@/lib/types";
import type { ClothCondition, ClothType } from "@xfold/protocol";

export function RunRowMenu({ run }: { run: RunSummary }) {
  const router = useRouter();
  const { launch, deleteRun, stopRun, getRun, snapshot } = useDashboard();
  const [confirm, setConfirm] = useState<"stop" | "delete" | null>(null);
  const [busy, setBusy] = useState<"stop" | "rerun" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canLaunch = snapshot.capabilities.startRun;
  const live = run.lifecycle === "running" || run.lifecycle === "paused" || run.lifecycle === "queued";
  const canStop = Boolean(snapshot.capabilities.commands.cancel_run) && live;
  // Cancelled rows must stay removable even if the live capability bit is off
  // (an older Isaac box, or a force-quit that has already left the worker).
  const canDelete = Boolean(snapshot.capabilities.deleteRun) || run.lifecycle === "cancelled";

  async function rerun() {
    if (!canLaunch || busy) return;
    setBusy("rerun");
    setError(null);
    const detail = getRun(run.id);
    const clothType = DEFAULT_CLOTH_TYPES.includes(run.clothType as ClothType)
      ? (run.clothType as ClothType)
      : DEFAULT_CLOTH_TYPES.includes(detail?.config.clothType as ClothType)
        ? (detail!.config.clothType as ClothType)
        : "tee";
    const clothCondition = DEFAULT_CLOTH_CONDITIONS.includes(run.clothCondition as ClothCondition)
      ? (run.clothCondition as ClothCondition)
      : DEFAULT_CLOTH_CONDITIONS.includes(detail?.config.clothCondition as ClothCondition)
        ? (detail!.config.clothCondition as ClothCondition)
        : "good";
    const result = await Promise.resolve(
      launch({
        mode: "individual",
        name: run.name ?? "",
        seed: run.seed,
        scenario: detail?.config.scenario ?? "line",
        clothType,
        clothCondition,
        speed: run.speed ?? 1,
      }),
    );
    setBusy(null);
    if (!result.ok) {
      setError(result.reason);
      return;
    }
    router.push(`/historial/${result.id}`);
  }

  async function confirmStop() {
    if (!canStop || busy) return;
    setBusy("stop");
    setError(null);
    const result = await stopRun(run.id, run.batchId);
    setBusy(null);
    setConfirm(null);
    if (!result.ok) setError(result.reason);
  }

  async function confirmDelete() {
    if (!canDelete || busy) return;
    setBusy("delete");
    setError(null);
    const result = await deleteRun(run.id);
    setBusy(null);
    setConfirm(null);
    if (!result.ok) setError(result.reason);
  }

  return (
    <div className="flex justify-end" onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="text-muted-foreground hover:text-ink"
            aria-label={`Actions for ${run.id}`}
            title={error ?? undefined}
          >
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenuItem disabled={!canStop || busy !== null} onSelect={() => setConfirm("stop")}>
            <Square aria-hidden />
            Stop
          </DropdownMenuItem>
          <DropdownMenuItem disabled={!canLaunch || busy !== null} onSelect={() => void rerun()}>
            <RotateCcw aria-hidden />
            Rerun
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="danger"
            disabled={!canDelete || busy !== null}
            onSelect={() => setConfirm("delete")}
          >
            <Trash2 aria-hidden />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <AlertDialog open={confirm === "stop"} onOpenChange={(open) => { if (!open) setConfirm(null); }}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Stop {run.id}?</AlertDialogTitle>
            <AlertDialogDescription>
              This force-quits the cycle. The run stays in the list as cancelled and can be deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void confirmStop()}>
              Stop
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={confirm === "delete"} onOpenChange={(open) => { if (!open) setConfirm(null); }}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {run.id}?</AlertDialogTitle>
            <AlertDialogDescription>
              {live
                ? "This cancels the cycle and removes it from the list, including its recording."
                : "This removes the run from the list, including its recording."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void confirmDelete()}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {error ? (
        <span className="sr-only" role="status">
          {error}
        </span>
      ) : null}
    </div>
  );
}
