import type { SimulatorCapabilities } from "./types";

/**
 * Honest capabilities for the current monorepo.
 * The sim only exposes SAMPLE_TELEMETRY / mock JSON lines — no command bus,
 * no run store, no viewport stream.
 */
export const LIVE_CAPABILITIES: SimulatorCapabilities = {
  liveTelemetry: false,
  viewportStream: false,
  startRun: false,
  startBatch: false,
  commands: {},
};

/** Fixture adapter may demo command UX locally; still not a real sim API. */
export const FIXTURE_CAPABILITIES: SimulatorCapabilities = {
  liveTelemetry: false,
  viewportStream: false,
  startRun: true,
  startBatch: true,
  commands: {
    pause_run: true,
    resume_run: true,
    cancel_run: true,
    pause_batch: true,
    resume_batch: true,
    cancel_batch: true,
  },
};
