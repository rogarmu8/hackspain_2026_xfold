import { CircleHelp, FlaskConical, PlugZap, TimerOff, Unplug } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatIso } from "@/lib/format";
import type { ConnectionStatus, DataProvenance } from "@/lib/types";

/** Connection + provenance in one glance: icon (shape) + tone + short label. */
export function ConnectionBadge({
  connection,
  provenance,
  lastUpdatedIso,
}: {
  connection: ConnectionStatus;
  provenance: DataProvenance;
  lastUpdatedIso: string | null;
}) {
  const stamp = lastUpdatedIso ? (
    <span className="font-mono font-normal tabular">{formatIso(lastUpdatedIso)}</span>
  ) : null;

  if (connection === "disconnected") {
    return (
      <StatusBadge tone="danger" icon={<Unplug className="size-3.5" aria-hidden />} title="Bridge disconnected">
        Offline {stamp}
      </StatusBadge>
    );
  }

  if (provenance === "fixture") {
    return (
      <StatusBadge tone="neutral" icon={<FlaskConical className="size-3.5" aria-hidden />} title="Local fixtures · bridge offline">
        Sample
      </StatusBadge>
    );
  }

  if (provenance === "stale") {
    return (
      <StatusBadge tone="danger" icon={<TimerOff className="size-3.5" aria-hidden />} title="Last data received">
        Stale {stamp}
      </StatusBadge>
    );
  }

  if (connection === "connected") {
    return (
      <StatusBadge
        tone="active"
        pulse
        icon={<PlugZap className="size-3.5" aria-hidden />}
        title={provenance === "live" ? "Bridge · journal + SSE" : "OpenArm simulator v2"}
      >
        {provenance === "live" ? "Live" : "Simulator"}
      </StatusBadge>
    );
  }

  return (
    <StatusBadge tone="neutral" icon={<CircleHelp className="size-3.5" aria-hidden />}>
      Unknown
    </StatusBadge>
  );
}
