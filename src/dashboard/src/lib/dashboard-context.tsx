"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useTransition,
  type ReactNode,
} from "react";
import type { JournalEvent } from "@xfold/protocol";
import { BridgeClient, bridgeBaseUrl, probeBridge } from "@/lib/bridge-client";
import { OFFLINE_CAPABILITIES } from "@/lib/capabilities";
import type {
  BatchSummary,
  CommandKind,
  ControlSnapshot,
  ExperimentListItem,
  LaunchRequest,
  RunDetail,
  RunSummary,
} from "@/lib/types";

/** Live bridge, or honest empty UI when the bridge is unreachable. Never fixtures. */
export type DataSource = "live" | "offline";

const EMPTY_JOURNAL: JournalEvent[] = [];

const OFFLINE_SNAPSHOT: ControlSnapshot = {
  provenance: "absent",
  connection: "disconnected",
  lastUpdatedIso: null,
  capabilities: OFFLINE_CAPABILITIES,
  activeRun: null,
  activeBatch: null,
  incident: {
    id: "bridge-down",
    message: "No connection to the XFOLD bridge",
    runId: null,
  },
};

type DashboardContextValue = {
  source: DataSource;
  bridgeUrl: string;
  snapshot: ControlSnapshot;
  pendingCommand: PendingCommand | null;
  experiments: ExperimentListItem[];
  history: RunSummary[];
  requestCommand: (kind: CommandKind, scopeLabel: string) => void;
  launch: (
    request: LaunchRequest,
  ) =>
    | { ok: true; id: string }
    | { ok: false; reason: string }
    | Promise<{ ok: true; id: string } | { ok: false; reason: string }>;
  getRun: (id: string) => RunDetail | null;
  getBatch: (id: string) => BatchSummary | null;
  /** Journal facts for a run (live only). */
  getJournal: (runId: string) => JournalEvent[];
  refresh: () => void;
};

export type PendingCommand = {
  kind: CommandKind;
  scopeLabel: string;
  requestedAtIso: string;
};

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [source, setSource] = useState<DataSource>("offline");
  const [bridge, setBridge] = useState<BridgeClient | null>(null);
  const [, startTransition] = useTransition();
  const [version, setVersion] = useState(0);
  const [pendingCommand, setPendingCommand] = useState<PendingCommand | null>(
    null,
  );

  const bump = useCallback(() => {
    startTransition(() => setVersion((v) => v + 1));
  }, [startTransition]);

  useEffect(() => {
    let cancelled = false;
    let client: BridgeClient | null = null;

    async function connect() {
      const url = bridgeBaseUrl();
      const ok = await probeBridge(url);
      if (cancelled) return;
      if (!ok) {
        setSource("offline");
        setBridge(null);
        bump();
        return;
      }
      client = new BridgeClient(url);
      const started = await client.start();
      if (cancelled) {
        client.stop();
        return;
      }
      if (!started) {
        setSource("offline");
        setBridge(null);
        bump();
        return;
      }
      setBridge(client);
      setSource("live");
      client.subscribe(() => {
        setPendingCommand(
          client!.pendingCommandId && client!.pendingKind
            ? {
                kind: client!.pendingKind,
                scopeLabel: client!.pendingKind,
                requestedAtIso: new Date().toISOString(),
              }
            : null,
        );
        bump();
      });
      bump();
    }

    void connect();
    return () => {
      cancelled = true;
      client?.stop();
    };
  }, [bump]);

  const refresh = useCallback(() => {
    if (source === "live" && bridge) {
      void bridge.refreshSnapshot().then(bump);
    }
  }, [source, bridge, bump]);

  const snapshot = useMemo(() => {
    void version;
    if (source === "live" && bridge) return bridge.getControlSnapshot();
    return OFFLINE_SNAPSHOT;
  }, [source, bridge, version]);

  const experiments = useMemo(() => {
    void version;
    if (source === "live" && bridge) return bridge.listExperiments();
    return [];
  }, [source, bridge, version]);

  const history = useMemo(() => {
    void version;
    if (source === "live" && bridge) return bridge.listHistory();
    return [];
  }, [source, bridge, version]);

  const requestCommand = useCallback(
    (kind: CommandKind, scopeLabel: string) => {
      if (source !== "live" || !bridge) return;
      const runId = bridge.getControlSnapshot().activeRun?.id ?? null;
      const batchId = bridge.getControlSnapshot().activeBatch?.id ?? null;
      setPendingCommand({
        kind,
        scopeLabel,
        requestedAtIso: new Date().toISOString(),
      });
      void bridge.requestCommand(kind, runId, batchId).then(() => {
        setPendingCommand(null);
        bump();
      });
    },
    [source, bridge, bump],
  );

  const launch = useCallback(
    (request: LaunchRequest) => {
      if (source !== "live" || !bridge) {
        return {
          ok: false as const,
          reason: "Bridge offline — connect the simulator before launching.",
        };
      }
      return bridge.launch(request).then((result) => {
        bump();
        return result;
      });
    },
    [source, bridge, bump],
  );

  const getRun = useCallback(
    (id: string) => {
      void version;
      if (source === "live" && bridge) return bridge.getRun(id);
      return null;
    },
    [source, bridge, version],
  );

  const getBatch = useCallback(
    (id: string) => {
      void version;
      if (source === "live" && bridge) return bridge.getBatch(id);
      return null;
    },
    [source, bridge, version],
  );

  const getJournal = useCallback(
    (runId: string) => {
      void version;
      return source === "live" && bridge ? bridge.listJournal(runId) : EMPTY_JOURNAL;
    },
    [source, bridge, version],
  );

  const value = useMemo(
    () => ({
      source,
      bridgeUrl: bridgeBaseUrl(),
      snapshot,
      pendingCommand,
      experiments,
      history,
      requestCommand,
      launch,
      getRun,
      getBatch,
      getJournal,
      refresh,
    }),
    [
      source,
      snapshot,
      pendingCommand,
      experiments,
      history,
      requestCommand,
      launch,
      getRun,
      getBatch,
      getJournal,
      refresh,
    ],
  );

  return (
    <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>
  );
}

export function useDashboard() {
  const ctx = useContext(DashboardContext);
  if (!ctx) {
    throw new Error("useDashboard must be used within DashboardProvider");
  }
  return ctx;
}
