import type { PhaseId } from "@xfold/protocol";
import {
  ArrowDownToLine,
  ArrowRightLeft,
  Circle,
  FoldVertical,
  Funnel,
  Hand,
  Package,
  RotateCcw,
  StretchHorizontal,
  type LucideIcon,
} from "lucide-react";

/** One Lucide glyph per cell stage — shared by stepper, HUD and history. */
export const STAGE_ICONS: Partial<Record<PhaseId, LucideIcon>> = {
  PICK: Hand,
  ORIENT: ArrowRightLeft,
  SPREAD: StretchHorizontal,
  PRESS: ArrowDownToLine,
  FOLD: FoldVertical,
  CHUTE: Funnel,
  BAG: Package,
  RESET: RotateCcw,
};

export const DEFAULT_STAGE_ICON = Circle;
