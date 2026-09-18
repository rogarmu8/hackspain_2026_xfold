import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatIso } from "@/lib/format";
import type { ConnectionStatus, DataProvenance } from "@/lib/types";

export function ConnectionBadge({
  connection,
  provenance,
  lastUpdatedIso,
}: {
  connection: ConnectionStatus;
  provenance: DataProvenance;
  lastUpdatedIso: string | null;
}) {
  if (connection === "disconnected") {
    return (
      <StatusBadge tone="danger" icon={<Dot className="bg-danger" />}>
        Sin conexión
        {lastUpdatedIso ? (
          <span className="font-normal text-muted-foreground">
            · último dato {formatIso(lastUpdatedIso)}
          </span>
        ) : null}
      </StatusBadge>
    );
  }

  if (provenance === "fixture") {
    return (
      <StatusBadge tone="neutral" icon={<Dot className="bg-muted" />}>
        Datos de ejemplo
        <span className="font-normal">· demo local</span>
      </StatusBadge>
    );
  }

  if (provenance === "stale") {
    return (
      <StatusBadge tone="danger" icon={<Dot className="bg-danger" />}>
        Datos obsoletos
        {lastUpdatedIso ? (
          <span className="font-normal">· {formatIso(lastUpdatedIso)}</span>
        ) : null}
      </StatusBadge>
    );
  }

  if (connection === "connected") {
    return (
      <StatusBadge tone="active" icon={<Dot className="bg-active" />}>
        Simulador conectado
        <span className="font-normal">· OpenArm v2</span>
      </StatusBadge>
    );
  }

  return (
    <StatusBadge tone="neutral" icon={<Dot className="bg-muted" />}>
      Estado de conexión desconocido
    </StatusBadge>
  );
}

function Dot({ className }: { className: string }) {
  return (
    <span
      className={`inline-block size-2 shrink-0 rounded-full ${className}`}
      aria-hidden
    />
  );
}
