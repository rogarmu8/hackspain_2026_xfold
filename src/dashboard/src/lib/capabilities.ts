import type { BridgeCapabilities } from "@xfold/protocol";
import { CLOTH_CONDITION_KEYS, CLOTH_TYPE_KEYS } from "@xfold/protocol";
import type { SimulatorCapabilities } from "./types";

const DEFAULT_CATALOG = {
  clothTypes: CLOTH_TYPE_KEYS.map((key) => ({ key, label: key })),
  clothConditions: CLOTH_CONDITION_KEYS.map((key) => ({ key, label: key })),
};

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
  ...DEFAULT_CATALOG,
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
  ...DEFAULT_CATALOG,
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
    clothTypes: caps.clothTypes?.length ? caps.clothTypes : DEFAULT_CATALOG.clothTypes,
    clothConditions: caps.clothConditions?.length
      ? caps.clothConditions
      : DEFAULT_CATALOG.clothConditions,
  };
}
