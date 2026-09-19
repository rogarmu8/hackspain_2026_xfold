import type { BridgeCapabilities } from "@xfold/protocol";
import type { SimulatorCapabilities } from "./types";

/**
 * Honest offline defaults when the bridge is unreachable.
 * Live capabilities come from GET /capabilities on the bridge.
 */
export const OFFLINE_CAPABILITIES: SimulatorCapabilities = {
  liveTelemetry: false,
  viewportStream: false,
  recordingSeek: false,
  startRun: false,
  startBatch: false,
  commands: {},
};

/** @deprecated use OFFLINE_CAPABILITIES — name kept for fixture adapter imports */
export const LIVE_CAPABILITIES = OFFLINE_CAPABILITIES;

/** Fixture adapter may demo command UX locally; still not a real sim API. */
export const FIXTURE_CAPABILITIES: SimulatorCapabilities = {
  liveTelemetry: false,
  viewportStream: false,
  recordingSeek: false,
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

export function fromBridgeCapabilities(
  caps: BridgeCapabilities,
): SimulatorCapabilities {
  return {
    liveTelemetry: caps.liveTelemetry,
    viewportStream: caps.viewportStream,
    recordingSeek: caps.recordingSeek ?? false,
    startRun: caps.startRun,
    startBatch: caps.startBatch,
    commands: { ...caps.commands },
  };
}
