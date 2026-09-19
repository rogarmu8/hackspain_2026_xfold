"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { FoldLogo, FoldMark } from "@/components/FoldMark";

/**
 * Single top bar: brand · (back link) · page title · actions. There is no
 * navigation: the run list is the home page and each run opens its own view.
 */
export function AppShell({
  title,
  description,
  eyebrow,
  back,
  actions,
  fit = false,
  children,
}: {
  title: string;
  description?: ReactNode;
  /** Short mono caption next to the title (context, not prose). */
  eyebrow?: string;
  /** Where this page came from (rendered as a back link). */
  back?: { href: string; label: string };
  actions?: ReactNode;
  /** Lock the page to the viewport height (no page scroll) on desktop. */
  fit?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={`flex flex-col bg-canvas text-ink ${fit ? "h-svh" : "min-h-svh"}`}>
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-surface focus:p-4">Saltar al contenido</a>

      <header className="sticky top-0 z-20 flex min-h-[var(--header-height)] shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-divider bg-canvas/95 px-6 py-2.5 backdrop-blur-[2px] max-[768px]:px-4">
        <Link href="/" className="flex shrink-0 items-center text-ink no-underline" aria-label="XFold · ejecuciones">
          <FoldLogo width={96} className="max-[640px]:hidden" />
          <FoldMark size={26} className="min-[641px]:hidden" />
        </Link>

        {back ? (
          <Link
            href={back.href}
            className="inline-flex shrink-0 items-center gap-1 rounded-[var(--radius-sm)] px-2 py-1.5 text-sm font-semibold text-muted-foreground no-underline transition-colors duration-[120ms] ease-out hover:bg-surface hover:text-ink"
          >
            <ArrowLeft className="size-3.5" aria-hidden />
            {back.label}
          </Link>
        ) : null}

        <div className="flex min-w-0 flex-1 items-baseline gap-3 border-l border-divider pl-5 max-[640px]:hidden">
          <h1 className="truncate text-[17px] font-semibold leading-tight tracking-[-0.01em]">{title}</h1>
          {eyebrow ? <p className="eyebrow truncate">{eyebrow}</p> : null}
          {description ? <p className="truncate text-[13px] text-muted-foreground">{description}</p> : null}
        </div>

        <div className="ml-auto flex max-w-full flex-wrap items-center justify-end gap-3">
          {actions}
        </div>
      </header>

      <main
        id="main-content"
        className={`flex-1 px-6 py-5 max-[768px]:px-4 ${fit ? "flex min-h-0 flex-col xl:overflow-hidden" : ""}`}
      >
        {children}
      </main>
    </div>
  );
}
