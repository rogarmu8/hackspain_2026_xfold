import type { PhaseId } from "@xfold/protocol";
import {
  ArrowDownToLine,
  Circle,
  FoldVertical,
  Package,
  RotateCcw,
  RotateCw,
  ShoppingBag,
  type LucideIcon,
} from "lucide-react";

/** One Lucide glyph per cell stage — shared by stepper, HUD and history. */
export const STAGE_ICONS: Partial<Record<PhaseId, LucideIcon>> = {
  LOAD: RotateCw,
  ORIENT: RotateCw,
  PICK: RotateCw,
  SPREAD: RotateCw,
  TO_PRESS: ArrowDownToLine,
  PRESS: ArrowDownToLine,
  TO_QC: ArrowDownToLine,
  PHOTO: ArrowDownToLine,
  SORT: ArrowDownToLine,
  TO_FOLDER: FoldVertical,
  FOLD: FoldVertical,
  INSERT: ShoppingBag,
  CHUTE: ShoppingBag,
  TO_SEAL: Package,
  SEAL: Package,
  TO_CARTON: Package,
  DONE: Package,
  BAG: Package,
  RESET: RotateCcw,
};

export const DEFAULT_STAGE_ICON = Circle;
