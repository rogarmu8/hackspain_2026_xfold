"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { FoldMark } from "@/components/FoldMark";

const NAV = [
  { href: "/", label: "Control" },
  { href: "/experimentos", label: "Experimentos" },
  { href: "/historial", label: "Historial" },
] as const;

export function AppShell({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-full bg-canvas text-ink">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-surface focus:p-4">Saltar al contenido</a>
      <aside className="sticky top-0 flex h-svh w-[var(--nav-width)] shrink-0 flex-col border-r border-divider bg-canvas px-4 py-6 max-[768px]:hidden">
        <Link href="/" className="flex items-start gap-2 px-2 text-ink no-underline">
          <FoldMark className="mt-0.5 text-primary" />
          <span>
            <span className="block text-lg font-semibold tracking-tight">XFOLD</span>
            <span className="mt-1 block text-[12px] leading-snug text-muted-foreground">
              Centro de control · simulación
            </span>
          </span>
        </Link>

        <nav className="mt-10 flex flex-col gap-1" aria-label="Principal">
          {NAV.map((item) => {
            const current =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={`relative rounded-[var(--radius-sm)] px-3 py-2.5 text-sm font-semibold no-underline transition-colors duration-[120ms] ease-out ${
                  current
                    ? "bg-surface text-ink before:absolute before:top-2 before:bottom-2 before:left-0 before:w-0.5 before:bg-ink"
                    : "text-muted-foreground hover:bg-surface hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <p className="mt-auto px-2 text-[12px] leading-snug text-muted-foreground">
          HackSpain ’26 · THEKER challenge
        </p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex min-h-[var(--header-height)] flex-wrap items-center justify-between gap-4 border-b border-divider bg-canvas/95 px-6 py-3 backdrop-blur-[2px] max-[768px]:px-4">
          <div className="min-w-0">
            <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em]">
              {title}
            </h1>
            {description ? (
              <p className="mt-1 text-[13px] text-muted-foreground">{description}</p>
            ) : null}
          </div>
          <div className="flex max-w-full flex-wrap items-center justify-end gap-3">
            {actions}
          </div>
        </header>

        <nav
          className="flex gap-1 border-b border-divider px-4 py-2 min-[769px]:hidden"
          aria-label="Principal móvil"
        >
          {NAV.map((item) => {
            const current =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={`rounded-[var(--radius-sm)] px-3 py-2 text-sm font-semibold no-underline ${
                  current ? "bg-surface text-ink" : "text-muted-foreground"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <main id="main-content" className="flex-1 px-6 py-6 max-[768px]:px-4">{children}</main>
      </div>
    </div>
  );
}
