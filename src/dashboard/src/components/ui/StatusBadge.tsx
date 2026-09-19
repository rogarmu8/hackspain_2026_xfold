import type { ReactNode } from "react";
import { Badge } from "./badge";

export function StatusBadge({
  tone,
  icon,
  pulse = false,
  title,
  children,
}: {
  tone: "active" | "neutral" | "danger" | "success" | "pending";
  icon?: ReactNode;
  /** Adds a breathing dot — only for genuinely live states. */
  pulse?: boolean;
  title?: string;
  children: ReactNode;
}) {
  return (
    <Badge
      title={title}
      variant={
        tone === "active" || tone === "success"
          ? "active"
          : tone === "danger"
            ? "destructive"
            : "outline"
      }
    >
      {pulse ? (
        <span className="pulse-dot size-1.5 shrink-0 rounded-full bg-current" aria-hidden />
      ) : null}
      {icon}
      {children}
    </Badge>
  );
}
