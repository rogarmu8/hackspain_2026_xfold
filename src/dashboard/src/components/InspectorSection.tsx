"use client";

import type { ReactNode } from "react";
import { ChevronDown, type LucideIcon } from "lucide-react";

export function InspectorSection({
  id,
  title,
  icon: Icon,
  open,
  onToggle,
  trailing,
  children,
  fill = false,
  className = "",
}: {
  id: string;
  title: string;
  icon: LucideIcon;
  open: boolean;
  onToggle: () => void;
  trailing?: ReactNode;
  children: ReactNode;
  /** Grow into leftover column space. Other panes hug their content. */
  fill?: boolean;
  className?: string;
}) {
  return (
    <section
      className={`flex flex-col border border-divider bg-surface ${
        fill ? "h-full min-h-0 overflow-hidden" : "shrink-0"
      } ${className}`}
    >
      <h2 className="shrink-0">
        <button
          type="button"
          className="flex h-10 w-full items-center gap-2 px-3 text-left"
          aria-expanded={open}
          aria-controls={id}
          onClick={onToggle}
        >
          <Icon className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
          <span className="eyebrow truncate">{title}</span>
          {trailing}
          <ChevronDown
            className={`ml-auto size-3.5 shrink-0 text-muted-foreground transition-transform duration-[var(--motion-panel)] ease-[var(--motion-ease)] ${
              open ? "rotate-180" : ""
            }`}
            aria-hidden
          />
        </button>
      </h2>
      <div
        id={id}
        role="region"
        aria-hidden={!open}
        {...(open ? {} : { inert: true })}
        className={`grid min-h-0 transition-[grid-template-rows] duration-[var(--motion-panel)] ease-[var(--motion-ease)] ${
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
        } ${fill ? "min-h-0 flex-1" : ""}`}
      >
        <div className={`min-h-0 overflow-hidden ${fill ? "flex min-h-0 flex-col" : ""}`}>
          <div
            className={
              fill
                ? "flex h-full min-h-0 flex-col overflow-hidden"
                : "min-w-0"
            }
          >
            {children}
          </div>
        </div>
      </div>
    </section>
  );
}
