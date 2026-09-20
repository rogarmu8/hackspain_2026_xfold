import type { PhaseId } from "@xfold/protocol";
import { operatorStepTitle } from "@/lib/format";
import type { StageProgress } from "@/lib/types";

/** Consecutive simulator phases that share an operator title (Rotate → Pack). */
export type OperatorStep = {
  label: string;
  state: PhaseId;
  states: PhaseId[];
  status: StageProgress["status"];
  durationSimS: number | null;
};

export function groupOperatorSteps(stages: StageProgress[]): OperatorStep[] {
  const groups: OperatorStep[] = [];
  for (const stage of stages) {
    const label = operatorStepTitle(stage.state, stages);
    const prev = groups.at(-1);
    if (prev && prev.label === label) {
      prev.states.push(stage.state);
      prev.status = combineStatus(prev.status, stage.status);
      prev.durationSimS = sumDuration(prev.durationSimS, stage);
      if (stage.status === "active") prev.state = stage.state;
      continue;
    }
    groups.push({
      label,
      state: stage.state,
      states: [stage.state],
      status: stage.status,
      durationSimS: stage.status === "completed" ? stage.durationSimS : null,
    });
  }
  return groups;
}

/** 0–1 fill: completed steps count as 1, the active/failed step as 0.55. */
export function cycleFill(items: OperatorStep[]): number {
  if (items.length === 0) return 0;
  let units = 0;
  for (const step of items) {
    if (step.status === "completed" || step.status === "skipped") {
      units += 1;
      continue;
    }
    if (step.status === "active" || step.status === "failed") {
      units += 0.55;
    }
    break;
  }
  return units / items.length;
}

function combineStatus(
  a: StageProgress["status"],
  b: StageProgress["status"],
): StageProgress["status"] {
  if (a === "failed" || b === "failed") return "failed";
  if (a === "active" || b === "active") return "active";
  if (a === "completed" && b === "pending") return "active";
  if (a === "pending" && b === "completed") return "active";
  if (a === "completed" && (b === "completed" || b === "skipped")) return "completed";
  if (a === "skipped" && b === "completed") return "completed";
  if (a === "skipped" && b === "skipped") return "skipped";
  return b;
}

function sumDuration(current: number | null, stage: StageProgress): number | null {
  if (stage.status !== "completed" || stage.durationSimS == null) return current;
  return (current ?? 0) + stage.durationSimS;
}
