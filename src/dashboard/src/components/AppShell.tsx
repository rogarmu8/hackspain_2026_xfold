"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Activity, FlaskConical, History, type LucideIcon } from "lucide-react";
import { FoldMark } from "@/components/FoldMark";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Control", icon: Activity },
  { href: "/experimentos", label: "Experimentos", icon: FlaskConical },
  { href: "/historial", label: "Historial", icon: History },
];

export function AppShell({
  title,
  eyebrow,
  actions,
  fit = false,
  children,
}: {
  title: string;
  /** Short mono caption next to the title (context, not prose). */
  eyebrow?: string;
  actions?: ReactNode;
  /** Lock the page to the viewport height (no page scroll) on desktop. */
  fit?: boolean;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const isCurrent = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div className={`flex bg-canvas text-ink ${fit ? "h-svh" : "min-h-svh"}`}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-surface focus:p-4"
      >
        Saltar al contenido
      </a>

      <aside className="sticky top-0 flex h-svh w-[var(--nav-width)] shrink-0 flex-col border-r border-divider bg-canvas px-3 py-4 max-[768px]:hidden">
        <Link
          href="/"
          className="flex h-10 items-center gap-2.5 px-2 text-ink no-underline"
        >
          <FoldMark className="text-primary" />
          <span className="text-[15px] font-semibold tracking-tight">XFOLD</span>
          <span className="eyebrow ml-auto">sim</span>
        </Link>

        <nav className="mt-6 flex flex-col gap-0.5" aria-label="Principal">
          {NAV.map((item) => {
            const current = isCurrent(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={`relative flex h-10 items-center gap-3 rounded-[var(--radius-sm)] px-3 text-sm font-medium no-underline transition-colors duration-[var(--motion-feedback)] ease-[var(--motion-ease)] ${
                  current
                    ? "bg-surface text-ink before:absolute before:top-2 before:bottom-2 before:left-0 before:w-0.5 before:bg-primary"
                    : "text-muted-foreground hover:bg-surface hover:text-ink"
                }`}
              >
                <Icon className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="eyebrow mt-auto px-2 leading-relaxed">
          HackSpain ’26
          <br />
          THEKER challenge
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-[var(--header-height)] shrink-0 items-center justify-between gap-4 border-b border-divider bg-canvas/95 px-5 backdrop-blur-[2px] max-[768px]:px-4">
          <div className="flex min-w-0 items-baseline gap-3">
            <h1 className="truncate text-[17px] font-semibold leading-none tracking-tight">
              {title}
            </h1>
            {eyebrow ? (
              <span className="eyebrow hidden truncate lg:inline">{eyebrow}</span>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">{actions}</div>
        </header>

        <nav
          className="flex gap-1 border-b border-divider px-3 py-1.5 min-[769px]:hidden"
          aria-label="Principal móvil"
        >
          {NAV.map((item) => {
            const current = isCurrent(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={`flex items-center gap-2 rounded-[var(--radius-sm)] px-3 py-2 text-sm font-medium no-underline ${
                  current ? "bg-surface text-ink" : "text-muted-foreground"
                }`}
              >
                <Icon className="size-4" strokeWidth={1.75} aria-hidden />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <main
          id="main-content"
          className={`flex-1 px-5 py-4 max-[768px]:px-4 ${
            fit ? "flex min-h-0 flex-col xl:overflow-hidden" : ""
          }`}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
