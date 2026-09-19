import {
  B612,
  B612_Mono,
  Geist,
  Geist_Mono,
  IBM_Plex_Mono,
  IBM_Plex_Sans,
  JetBrains_Mono,
  Recursive,
  Space_Grotesk,
  Space_Mono,
} from "next/font/google";
import Link from "next/link";
import { FontSampleCard } from "@/components/FontSampleCard";

const geistSans = Geist({ subsets: ["latin"], weight: ["400", "500", "600"] });
const geistMono = Geist_Mono({ subsets: ["latin"], weight: ["400", "500", "600"] });

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});
const spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
});

const b612 = B612({ subsets: ["latin"], weight: ["400", "700"] });
const b612Mono = B612_Mono({ subsets: ["latin"], weight: ["400", "700"] });

const recursive = Recursive({
  subsets: ["latin"],
  axes: ["MONO", "CASL", "CRSV", "slnt"],
});

const PAIRS = [
  {
    id: "geist",
    name: "Geist + Geist Mono",
    tag: "Anterior",
    note: "Baseline previo. Limpio y de producto; menos “celda”.",
    sans: geistSans,
    mono: geistMono,
  },
  {
    id: "plex",
    name: "IBM Plex Sans + Plex Mono",
    tag: "Actual",
    note: "Familia activa del dashboard. Industrial humano–máquina.",
    sans: plexSans,
    mono: plexMono,
  },
  {
    id: "space-jb",
    name: "Space Grotesk + JetBrains Mono",
    tag: "Digital",
    note: "Más pantallazo de control contemporáneo; mono muy legible en datos.",
    sans: spaceGrotesk,
    mono: jetbrainsMono,
  },
  {
    id: "space-pair",
    name: "Space Grotesk + Space Mono",
    tag: "Familia única",
    note: "Misma DNA tipográfica. El mono es más display / terminal.",
    sans: spaceGrotesk,
    mono: spaceMono,
  },
  {
    id: "b612",
    name: "B612 + B612 Mono",
    tag: "Cockpit",
    note: "Tipografía Airbus para cabina. Máxima legibilidad; carácter más raro.",
    sans: b612,
    mono: b612Mono,
  },
  {
    id: "recursive",
    name: "Recursive (sans ↔ mono)",
    tag: "Variable",
    note: "Una familia; el mono usa el eje MONO. Muy UI/code, más compleja.",
    sans: recursive,
    mono: recursive,
    monoAsRecursive: true,
  },
] as const;

export const metadata = {
  title: "Tipografía · XFOLD",
  description: "Comparativa de familias tipográficas para el centro de control",
};

export default function TipografiaPage() {
  return (
    <main className="min-h-full bg-background px-6 py-8 text-foreground md:px-10">
      <div className="mx-auto max-w-[1400px]">
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
          <div>
            <p className="text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
              Laboratorio tipográfico
            </p>
            <h1 className="mt-1 text-[28px] font-semibold tracking-tight">
              Comparar fuentes
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Misma maqueta de control (título, badge, telemetría, IDs) en cada
              pareja. No cambia el producto todavía — solo sirve para decidir.
            </p>
          </div>
          <Link
            href="/"
            className="text-sm font-semibold underline-offset-4 hover:underline"
          >
            ← Volver al control
          </Link>
        </header>

        <div className="grid gap-6 lg:grid-cols-2">
          {PAIRS.map((pair) => (
            <FontSampleCard
              key={pair.id}
              name={pair.name}
              tag={pair.tag}
              note={pair.note}
              sansClassName={pair.sans.className}
              monoClassName={pair.mono.className}
              monoAsRecursive={"monoAsRecursive" in pair && pair.monoAsRecursive}
            />
          ))}
        </div>
      </div>
    </main>
  );
}
