import type { Metadata } from "next";
import { PitchDeck } from "@/components/PitchDeck";

export const metadata: Metadata = {
  title: "Pitch",
  description: "XFOLD en cuatro diapositivas: la estación manual de plegado, automatizada de punta a punta.",
};

/** The demo-day deck (Spanish copy). Space / → next, ← back, F for fullscreen. */
export default function PitchPage() {
  return <PitchDeck />;
}
