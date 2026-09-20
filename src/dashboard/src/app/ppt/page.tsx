import type { Metadata } from "next";
import { PitchDeck } from "@/components/PitchDeck";

export const metadata: Metadata = {
  title: "Pitch",
  description: "XFOLD in ten slides: the manual folding station, automated end to end.",
};

/** The demo-day deck. Space / → next, ← back, F for fullscreen. */
export default function PitchPage() {
  return <PitchDeck />;
}
