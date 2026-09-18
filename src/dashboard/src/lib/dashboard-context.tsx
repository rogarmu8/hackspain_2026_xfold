"use client";

import {
  createContext,
  useCallback,
  useContext,
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
import type {
  BatchSummary,
  CommandKind,
  ControlSnapshot,
  ExperimentListItem,
  LaunchRequest,
  RunDetail,
  RunSummary,
} from "@/lib/types";

type DashboardContextValue = {
  snapshot: ControlSnapshot;
  scenario: FixtureScenario;
  pendingCommand: PendingCommand | null;
  experiments: ExperimentListItem[];
  history: RunSummary[];
  setScenario: (scenario: FixtureScenario) => void;
  requestCommand: (kind: CommandKind, scopeLabel: string) => void;
  launch: (
    request: LaunchRequest,
  ) => { ok: true; id: string } | { ok: false; reason: string };
  getRun: (id: string) => RunDetail | null;
  getBatch: (id: string) => BatchSummary | null;
  refresh: () => void;
};

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const adapter = useMemo(() => getAdapter(), []);
  const [, startTransition] = useTransition();
  const [version, setVersion] = useState(0);
  const [scenario, setScenarioState] = useState<FixtureScenario>(
    () => adapter.scenario,
  );
  const [pendingCommand, setPendingCommand] = useState<PendingCommand | null>(
    null,
  );

  const refresh = useCallback(() => {
    startTransition(() => {
      setPendingCommand(adapter.pendingCommand);
      setScenarioState(adapter.scenario);
      setVersion((v) => v + 1);
    });
  }, [adapter, startTransition]);

  const snapshot = useMemo(() => {
    void version;
    return adapter.getControlSnapshot();
  }, [adapter, version]);

  const experiments = useMemo(() => {
    void version;
    return adapter.listExperiments();
  }, [adapter, version]);

  const history = useMemo(() => {
    void version;
    return adapter.listHistory();
  }, [adapter, version]);

  const setScenario = useCallback(
    (next: FixtureScenario) => {
      adapter.setScenario(next);
      setScenarioState(next);
      setPendingCommand(null);
      setVersion((v) => v + 1);
    },
    [adapter],
  );

  const requestCommand = useCallback(
    (kind: CommandKind, scopeLabel: string) => {
      const pending = adapter.requestCommand(kind, scopeLabel);
      setPendingCommand(pending);
      setVersion((v) => v + 1);
      if (!pending) return;
      // Fixture-only demo confirmation — not a real simulator bus.
      window.setTimeout(() => {
        adapter.confirmPendingCommand();
        setPendingCommand(null);
        setVersion((v) => v + 1);
      }, 700);
    },
    [adapter],
  );

  const launch = useCallback(
    (request: LaunchRequest) => {
      const result = adapter.launch(request);
      setScenarioState(adapter.scenario);
      setVersion((v) => v + 1);
      return result;
    },
    [adapter],
  );

  const getRun = useCallback(
    (id: string) => {
      void version;
      return adapter.getRun(id);
    },
    [adapter, version],
  );

  const getBatch = useCallback(
    (id: string) => {
      void version;
      return adapter.getBatch(id);
    },
    [adapter, version],
  );

  const value = useMemo(
    () => ({
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
