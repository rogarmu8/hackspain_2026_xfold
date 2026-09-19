"use client";

import { useCallback, useState } from "react";
import { Camera, Loader2, Shirt } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { RunDetail } from "@/lib/types";

/**
 * The QC camera's product shot, and the try-on image generated from it.
 *
 * The shot is a file on the bridge (never a journal event), fetched through
 * the same-origin /api/bridge proxy. The try-on call goes to /api/tryon so the
 * OpenAI key stays server-side.
 *
 * Generated URLs are remembered per run for the life of the tab, so stepping
 * between runs does not spend another call and another twenty seconds. The
 * cache is a module Map rather than localStorage on purpose: it is empty on
 * the server and on the client's first render alike, so there is nothing for
 * hydration to disagree about. A full reload starts over.
 *
 * ControlRoom passes key={run.id}, so switching run remounts this and the
 * state below starts from the cache again.
 */

const looks = new Map<string, string>();

type Phase = { state: "idle" | "loading" } | { state: "error"; message: string };

export function ProductShotPanel({ run }: { run: RunDetail }) {
  const [look, setLook] = useState<string | null>(() => looks.get(run.id) ?? null);
  const [phase, setPhase] = useState<Phase>({ state: "idle" });

  const generate = useCallback(async () => {
    setPhase({ state: "loading" });
    try {
      const res = await fetch("/api/tryon", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ runId: run.id }),
      });
      const body = (await res.json()) as {
        ok?: boolean;
        url?: string;
        detail?: string;
      };
      if (!res.ok || !body.ok || !body.url) {
        setPhase({
          state: "error",
          message: body.detail ?? `Error ${res.status}`,
        });
        return;
      }
      setLook(body.url);
      looks.set(run.id, body.url);
      setPhase({ state: "idle" });
    } catch (err) {
      setPhase({
        state: "error",
        message: err instanceof Error ? err.message : "Network error",
      });
    }
  }, [run.id]);

  const busy = phase.state === "loading";

  return (
    <aside className="flex flex-col gap-3 border border-divider bg-surface p-4">
      <header>
        <p className="eyebrow flex items-center gap-1.5">
          <Camera className="size-3.5" strokeWidth={1.75} aria-hidden />
          Product photo
        </p>
        <p className="mt-0.5 font-mono text-xs text-muted-foreground">
          overhead camera · after the press
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3">
        <figure className="m-0 flex flex-col gap-1.5">
          {/* eslint-disable-next-line @next/next/no-img-element -- bridge file, not a Next asset */}
          <img
            src={`/api/bridge/runs/${encodeURIComponent(run.id)}/photo`}
            alt={`Overhead garment photo for ${run.id}`}
            className="aspect-square w-full border border-divider object-cover"
          />
          <figcaption className="eyebrow">Captured</figcaption>
        </figure>

        <figure className="m-0 flex flex-col gap-1.5">
          {look ? (
            // eslint-disable-next-line @next/next/no-img-element -- data URI from OpenAI
            <img
              src={look}
              alt={`Model wearing the garment from ${run.id}`}
              className="aspect-square w-full border border-divider object-cover"
            />
          ) : (
            <div className="flex aspect-square w-full items-center justify-center border border-dashed border-divider text-muted-foreground">
              {busy ? (
                <Loader2 className="size-5 animate-spin" aria-hidden />
              ) : (
                <Shirt className="size-5" strokeWidth={1.5} aria-hidden />
              )}
            </div>
          )}
          <figcaption className="eyebrow">
            {look ? "Generated" : "Not generated"}
          </figcaption>
        </figure>
      </div>

      <Button size="sm" onClick={generate} disabled={busy}>
        {busy ? "Generating…" : look ? "Regenerate look" : "Generate look on a model"}
      </Button>

      {phase.state === "error" ? (
        <p className="text-sm text-danger" role="alert">
          {phase.message}
        </p>
      ) : (
        <p className="eyebrow">
          {busy
            ? "OpenAI · can take ~30 s"
            : "Sends the photo to OpenAI and returns the garment on a model"}
        </p>
      )}
    </aside>
  );
}
