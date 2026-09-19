import type { CellState } from "@xfold/protocol";
import {
  ArrowDownToLine,
  FoldVertical,
  Funnel,
  Hand,
  Package,
  RotateCcw,
  StretchHorizontal,
  type LucideIcon,
} from "lucide-react";

/** One Lucide glyph per cell stage — shared by stepper, HUD and history. */
export const STAGE_ICONS: Record<CellState, LucideIcon> = {
  PICK: Hand,
  SPREAD: StretchHorizontal,
  PRESS: ArrowDownToLine,
  FOLD: FoldVertical,
  CHUTE: Funnel,
  BAG: Package,
  RESET: RotateCcw,
};
