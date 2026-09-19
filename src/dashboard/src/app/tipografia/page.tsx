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
    tag: "Previous",
    note: "Previous baseline. Clean product look; less “cell”.",
    sans: geistSans,
    mono: geistMono,
  },
  {
    id: "plex",
    name: "IBM Plex Sans + Plex Mono",
    tag: "Current",
    note: "Active dashboard family. Industrial human–machine.",
    sans: plexSans,
    mono: plexMono,
  },
  {
    id: "space-jb",
    name: "Space Grotesk + JetBrains Mono",
    tag: "Digital",
    note: "More contemporary control-room screen; mono is very readable for data.",
    sans: spaceGrotesk,
    mono: jetbrainsMono,
  },
  {
    id: "space-pair",
    name: "Space Grotesk + Space Mono",
    tag: "Single family",
    note: "Same typographic DNA. The mono is more display / terminal.",
    sans: spaceGrotesk,
    mono: spaceMono,
  },
  {
    id: "b612",
    name: "B612 + B612 Mono",
    tag: "Cockpit",
    note: "Airbus cockpit typeface. Maximum readability; rarer character.",
    sans: b612,
    mono: b612Mono,
  },
  {
    id: "recursive",
    name: "Recursive (sans ↔ mono)",
    tag: "Variable",
    note: "One family; the mono uses the MONO axis. Very UI/code, more complex.",
    sans: recursive,
    mono: recursive,
    monoAsRecursive: true,
  },
] as const;

export const metadata = {
  title: "Typography · XFOLD",
  description: "Typeface comparison for the control room",
};

export default function TipografiaPage() {
  return (
    <main className="min-h-full bg-background px-6 py-8 text-foreground md:px-10">
      <div className="mx-auto max-w-[1400px]">
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
          <div>
            <p className="text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
              Type lab
            </p>
            <h1 className="mt-1 text-[28px] font-semibold tracking-tight">
              Compare typefaces
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Same control mock (title, badge, telemetry, IDs) in each pair.
              The product is unchanged for now — this is only for deciding.
            </p>
          </div>
          <Link
            href="/"
            className="text-sm font-semibold underline-offset-4 hover:underline"
          >
            ← Back to control
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
