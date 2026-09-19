"use client";

import { useEffect, useRef, useState, type UIEvent } from "react";
import { ArrowDownToLine, TerminalSquare, TriangleAlert } from "lucide-react";
import type { LogLevel } from "@xfold/protocol";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { STALL_AFTER_S, type ConsoleLine } from "@/lib/console";
import { formatSeconds } from "@/lib/format";

const LEVEL_CLASS: Record<LogLevel, string> = {
  debug: "text-muted-foreground/70",
  info: "text-ink",
  warning: "text-warning",
  error: "text-danger font-semibold",
};

const NEAR_BOTTOM_PX = 24;

/**
 * Live simulator console: journal facts as monospace lines, level filter,
 * auto-scroll that pauses when the operator scrolls up, and a stall watchdog
 * that flags a running run with no facts for `STALL_AFTER_S`.
 */
export function ConsolePanel({
  lines,
  running,
  className = "",
}: {
  lines: ConsoleLine[];
  /** True while the run is running (enables the stall watchdog). */
  running: boolean;
  className?: string;
}) {
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [pinned, setPinned] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const bodyRef = useRef<HTMLOListElement | null>(null);
  /** Line count when the operator last left the bottom; drives the "N nuevas" hint. */
  const [seenAt, setSeenAt] = useState(lines.length);

  const visible = onlyProblems ? lines.filter((l) => l.level === "warning" || l.level === "error") : lines;
  const problems = lines.filter((l) => l.level === "warning" || l.level === "error").length;
  const lastTs = lines.at(-1)?.tsIso ?? null;
  const silenceS = lastTs ? (now - Date.parse(lastTs)) / 1000 : 0;
  const stalled = running && lastTs !== null && silenceS > STALL_AFTER_S;
  const unread = pinned ? 0 : Math.max(0, lines.length - seenAt);

  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running]);

  useEffect(() => {
    const el = bodyRef.current;
    if (!el || !pinned) return;
    el.scrollTop = el.scrollHeight;
  }, [lines.length, visible.length, pinned, stalled]);

  const onScroll = (event: UIEvent<HTMLOListElement>) => {
    const el = event.currentTarget;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    if (atBottom !== pinned) {
      setSeenAt(lines.length);
      setPinned(atBottom);
    }
  };

  return (
    <section className={`flex min-h-0 flex-col border border-divider bg-surface ${className}`}>
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-divider px-3">
        <h2 className="eyebrow flex items-center gap-1.5">
          <TerminalSquare className="size-3.5" strokeWidth={1.75} aria-hidden />
          Consola
        </h2>
        <span className="font-mono text-[11px] tabular text-muted-foreground">{lines.length}</span>
        {stalled ? (
          <StatusBadge tone="danger" icon={<TriangleAlert className="size-3" aria-hidden />} title={`Sin eventos desde hace ${Math.round(silenceS)} s`}>
            Sin señal · {Math.round(silenceS)} s
          </StatusBadge>
        ) : running ? (
          <StatusBadge tone="active" pulse>en vivo</StatusBadge>
        ) : null}
        <button
          type="button"
          onClick={() => setOnlyProblems((v) => !v)}
          aria-pressed={onlyProblems}
          className={`ml-auto rounded-[var(--radius-sm)] border px-2 py-0.5 font-mono text-[11px] uppercase tracking-[0.08em] ${
            onlyProblems ? "border-ink bg-canvas text-ink" : "border-divider text-muted-foreground hover:text-ink"
          }`}
          title="Mostrar solo avisos y errores"
        >
          avisos {problems ? `· ${problems}` : ""}
        </button>
      </header>

      <ol
        ref={bodyRef}
        onScroll={onScroll}
        aria-live={running ? "polite" : "off"}
        className="min-h-0 flex-1 overflow-y-auto px-3 py-2 font-mono text-[12px] leading-[1.6]"
      >
        {visible.length === 0 ? (
          <li className="text-muted-foreground">
            {lines.length ? "Sin avisos ni errores." : running ? "Esperando eventos de la simulación…" : "Sin eventos registrados."}
          </li>
        ) : (
          visible.map((line) => (
            <li key={line.id} className={`grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-2 ${LEVEL_CLASS[line.level]}`}>
              <span className="tabular text-muted-foreground">
                {line.atSimS == null ? "—" : formatSeconds(line.atSimS)}
              </span>
              <span className="min-w-0 break-words">
                <span className="text-muted-foreground">
                  {[line.station ?? line.source, line.stage, line.operation].filter(Boolean).join(" · ")}
                  {line.parallel ? " · paralelo" : ""}{" "}
                </span>
                {line.message}
              </span>
            </li>
          ))
        )}
        {stalled ? (
          <li className="mt-1 grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-2 text-danger">
            <span className="tabular">—</span>
            <span>
              <span className="opacity-70">watchdog </span>
              sin eventos desde hace {Math.round(silenceS)} s · comprobar bridge o simulación
            </span>
          </li>
        ) : null}
      </ol>

      {!pinned ? (
        <div className="shrink-0 border-t border-divider px-2 py-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-full justify-center gap-1.5 text-xs"
            onClick={() => {
              setPinned(true);
            }}
          >
            <ArrowDownToLine className="size-3.5" aria-hidden />
            Seguir en vivo{unread ? ` · ${unread} nuevas` : ""}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
