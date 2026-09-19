import type { GarmentKind } from "@xfold/protocol";

/** Mirrors src/sim/src/xfold/garment.py SAMPLES (CC0 Grigorev clothing-dataset). */
export const GARMENT_SAMPLES: {
  id: string;
  kind: GarmentKind;
  file: string;
}[] = [
  { id: "tshirt_01", kind: "tshirt", file: "tshirt_01.jpg" },
  { id: "tshirt_02", kind: "tshirt", file: "tshirt_02.jpg" },
  { id: "polo_01", kind: "polo", file: "polo_01.jpg" },
  { id: "polo_02", kind: "polo", file: "polo_02.jpg" },
  { id: "tank_01", kind: "tank", file: "tank_01.jpg" },
  { id: "tank_02", kind: "tank", file: "tank_02.jpg" },
];

export function samplesFor(kind: GarmentKind) {
  return GARMENT_SAMPLES.filter((s) => s.kind === kind);
}

export function garmentThumbSrc(sample: { id: string; file: string }): string {
  return `/garments/${sample.file}`;
}
