import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  runGarmentLabel,
  runGarmentTone,
  runProcessLabel,
  runProcessTone,
} from "@/lib/format";

type RunStatusSource = {
  lifecycle: string;
  clothCondition?: string | null;
  config?: { clothCondition?: string | null };
};

/** Process result and garment mark as two independent badges. */
export function RunStatusBadges({ run }: { run: RunStatusSource }) {
  const garment = runGarmentLabel(run);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <StatusBadge tone={runProcessTone(run)}>{runProcessLabel(run)}</StatusBadge>
      {garment ? <StatusBadge tone={runGarmentTone(run)}>{garment}</StatusBadge> : null}
    </span>
  );
}
