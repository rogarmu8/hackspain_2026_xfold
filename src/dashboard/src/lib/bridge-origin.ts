/**
 * Where the Python bridge lives, as seen from the Next server.
 *
 * Shared by the /api/bridge proxy and the /api/tryon route so the two cannot
 * drift onto different bridges.
 */
export function bridgeOrigin(): string {
  const raw =
    process.env.NEXT_PUBLIC_XFOLD_BRIDGE_URL?.trim() ||
    process.env.XFOLD_BRIDGE_URL?.trim() ||
    "http://127.0.0.1:8765";
  return raw.replace(/\/$/, "");
}
