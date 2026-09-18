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
import {
  getAdapter,
  type FixtureScenario,
  type PendingCommand,
} from "@/lib/adapter";
import { BridgeClient, bridgeBaseUrl, probeBridge } from "@/lib/bridge-client";
import type {
  BatchSummary,
  CommandKind,
  ControlSnapshot,
  ExperimentListItem,
  LaunchRequest,
  RunDetail,
  RunSummary,
} from "@/lib/types";

export type DataSource = "fixture" | "live";

type DashboardContextValue = {
  source: DataSource;
  bridgeUrl: string;
  snapshot: ControlSnapshot;
  scenario: FixtureScenario;
  pendingCommand: PendingCommand | null;
  experiments: ExperimentListItem[];
  history: RunSummary[];
  setScenario: (scenario: FixtureScenario) => void;
  requestCommand: (kind: CommandKind, scopeLabel: string) => void;
  launch: (
    request: LaunchRequest,
  ) =>
    | { ok: true; id: string }
    | { ok: false; reason: string }
    | Promise<{ ok: true; id: string } | { ok: false; reason: string }>;
  getRun: (id: string) => RunDetail | null;
  getBatch: (id: string) => BatchSummary | null;
  refresh: () => void;
};

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const fixture = useMemo(() => getAdapter(), []);
  const [source, setSource] = useState<DataSource>("fixture");
  const [bridge, setBridge] = useState<BridgeClient | null>(null);
  const [, startTransition] = useTransition();
  const [version, setVersion] = useState(0);
  const [scenario, setScenarioState] = useState<FixtureScenario>(
    () => fixture.scenario,
  );
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
        setSource("fixture");
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
        setSource("fixture");
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
      return;
    }
    startTransition(() => {
      setPendingCommand(fixture.pendingCommand);
      setScenarioState(fixture.scenario);
      setVersion((v) => v + 1);
    });
  }, [source, bridge, fixture, bump, startTransition]);

  const snapshot = useMemo(() => {
    void version;
    if (source === "live" && bridge) return bridge.getControlSnapshot();
    return fixture.getControlSnapshot();
  }, [source, bridge, fixture, version]);

  const experiments = useMemo(() => {
    void version;
    if (source === "live" && bridge) return bridge.listExperiments();
    return fixture.listExperiments();
  }, [source, bridge, fixture, version]);

  const history = useMemo(() => {
    void version;
    if (source === "live" && bridge) return bridge.listHistory();
    return fixture.listHistory();
  }, [source, bridge, fixture, version]);

  const setScenario = useCallback(
    (next: FixtureScenario) => {
      if (source === "live") return; // fixture knobs disabled while live
      fixture.setScenario(next);
      setScenarioState(next);
      setPendingCommand(null);
      setVersion((v) => v + 1);
    },
    [fixture, source],
  );

  const requestCommand = useCallback(
    (kind: CommandKind, scopeLabel: string) => {
      if (source === "live" && bridge) {
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
        return;
      }
      const pending = fixture.requestCommand(kind, scopeLabel);
      setPendingCommand(pending);
      setVersion((v) => v + 1);
      if (!pending) return;
      window.setTimeout(() => {
        fixture.confirmPendingCommand();
        setPendingCommand(null);
        setVersion((v) => v + 1);
      }, 700);
    },
    [source, bridge, fixture, bump],
  );

  const launch = useCallback(
    (request: LaunchRequest) => {
      if (source === "live" && bridge) {
        return bridge.launch(request).then((result) => {
          bump();
          return result;
        });
      }
      const result = fixture.launch(request);
      setScenarioState(fixture.scenario);
      setVersion((v) => v + 1);
      return result;
    },
    [source, bridge, fixture, bump],
  );

  const getRun = useCallback(
    (id: string) => {
      void version;
      if (source === "live" && bridge) return bridge.getRun(id);
      return fixture.getRun(id);
    },
    [source, bridge, fixture, version],
  );

  const getBatch = useCallback(
    (id: string) => {
      void version;
      if (source === "live" && bridge) return bridge.getBatch(id);
      return fixture.getBatch(id);
    },
    [source, bridge, fixture, version],
  );

  const value = useMemo(
    () => ({
      source,
      bridgeUrl: bridgeBaseUrl(),
      snapshot,
      scenario,
      pendingCommand,
      experiments,
      history,
      setScenario,
      requestCommand,
      launch,
      getRun,
      getBatch,
      refresh,
    }),
    [
      source,
      snapshot,
      scenario,
      pendingCommand,
      experiments,
      history,
      setScenario,
      requestCommand,
      launch,
      getRun,
      getBatch,
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
