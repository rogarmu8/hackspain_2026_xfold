/** Browser-side catalogue of operator custom garments (pixels stay off the journal). */

export type StoredCustomGarment = {
  id: string;
  sourceUrl: string;
  previewUrl: string;
  maskUrl: string;
  outline: number[][];
  savedAtIso: string;
};

const KEY = "xfold.customGarments";
const MAX = 12;

function canStore(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function loadCustomGarments(): StoredCustomGarment[] {
  if (!canStore()) return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as StoredCustomGarment[];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item) =>
        item &&
        typeof item.id === "string" &&
        typeof item.previewUrl === "string" &&
        Array.isArray(item.outline),
    );
  } catch {
    return [];
  }
}

function write(items: StoredCustomGarment[]): StoredCustomGarment[] {
  const next = items.slice(0, MAX);
  if (canStore()) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* quota: drop the oldest and retry once */
      if (next.length > 1) {
        try {
          window.localStorage.setItem(KEY, JSON.stringify(next.slice(0, next.length - 1)));
          return next.slice(0, next.length - 1);
        } catch {
          /* keep the in-memory list even if we cannot persist */
        }
      }
    }
  }
  return next;
}

export function rememberCustomGarment(
  draft: Pick<StoredCustomGarment, "sourceUrl" | "previewUrl" | "maskUrl" | "outline">,
): StoredCustomGarment[] {
  const now = new Date().toISOString();
  const current = loadCustomGarments();
  const existing = current.findIndex((item) => item.previewUrl === draft.previewUrl);
  const entry: StoredCustomGarment = {
    id: existing >= 0 ? current[existing].id : `cg-${Date.now().toString(36)}`,
    sourceUrl: draft.sourceUrl,
    previewUrl: draft.previewUrl,
    maskUrl: draft.maskUrl,
    outline: draft.outline,
    savedAtIso: now,
  };
  const rest = current.filter((item) => item.id !== entry.id);
  return write([entry, ...rest]);
}
