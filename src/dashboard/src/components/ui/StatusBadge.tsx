import type { ReactNode } from "react";
import { Badge } from "./badge";
export function StatusBadge({tone, icon, children}: {tone: "active" | "neutral" | "danger" | "success" | "pending"; icon?: ReactNode; children: ReactNode}) {
  return <Badge variant={tone === "active" || tone === "success" ? "active" : tone === "danger" ? "destructive" : "outline"}>{icon}{children}</Badge>;
}
