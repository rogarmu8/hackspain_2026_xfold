"use client";

import type { ReactNode } from "react";
import { XFoldLoader } from "@/components/XFoldLoader";

export type SlideTone = "light" | "dark";

export type Slide = {
  id: string;
  /** Surface the slide paints; the deck chrome follows it. */
  tone: SlideTone;
  /** Short name for the progress rail and the screen-reader announcement. */
  label: string;
  Content: () => ReactNode;
};

export const DARK_SURFACE = "#2a170f";
export const LIGHT_SURFACE = "var(--background)";

/* --- Slide primitives ------------------------------------------------- */

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[11px] tracking-[0.18em] uppercase opacity-60 sm:text-xs">
      {children}
    </p>
  );
}

function Headline({ children }: { children: ReactNode }) {
  return (
    <h2 className="max-w-[18ch] text-[clamp(2rem,5.4vw,4.25rem)] leading-[1.04] font-semibold tracking-[-0.02em] text-balance">
      {children}
    </h2>
  );
}

function Lede({ children }: { children: ReactNode }) {
  return (
    <p className="max-w-[52ch] text-[clamp(1rem,1.7vw,1.5rem)] leading-[1.45] opacity-75 text-pretty">
      {children}
    </p>
  );
}

function Stack({ children }: { children: ReactNode }) {
  return <div className="flex flex-col items-start gap-5 sm:gap-7">{children}</div>;
}

/** The orange rule that carries a number or a short claim. */
function Stat({ value, unit, caption }: { value: string; unit?: string; caption: string }) {
  return (
    <div className="border-t-2 border-[var(--primary)] pt-3">
      <p className="tabular text-[clamp(1.6rem,3.4vw,2.75rem)] leading-none font-semibold">
        {value}
        {unit ? <span className="ml-1 text-[0.45em] font-medium opacity-60">{unit}</span> : null}
      </p>
      <p className="mt-2 max-w-[22ch] text-sm leading-snug opacity-65">{caption}</p>
    </div>
  );
}

function Stats({ children }: { children: ReactNode }) {
  return <div className="grid w-full gap-6 sm:grid-cols-2 lg:grid-cols-4 lg:gap-8">{children}</div>;
}

/** The line, drawn as the stations the garment actually passes through. */
function Stations({ items }: { items: { name: string; note: string }[] }) {
  return (
    <ol className="grid w-full gap-px overflow-hidden rounded-[var(--radius)] border border-current/15 bg-current/15 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {items.map((station, index) => (
        <li
          key={station.name}
          className="flex flex-col gap-1 bg-[var(--slide-surface)] p-4 lg:p-5"
        >
          <span className="font-mono text-[11px] tracking-[0.12em] opacity-45">
            {String(index + 1).padStart(2, "0")}
          </span>
          <span className="text-base leading-tight font-semibold sm:text-lg">{station.name}</span>
          <span className="text-sm leading-snug opacity-65">{station.note}</span>
        </li>
      ))}
    </ol>
  );
}

/* --- The deck --------------------------------------------------------- */

export const SLIDES: Slide[] = [
  {
    id: "title",
    tone: "dark",
    label: "XFOLD",
    Content: () => (
      <div className="flex w-full flex-col items-center gap-8 text-center">
        <XFoldLoader
          size={132}
          tone="dark"
          surface={DARK_SURFACE}
          decorative
          className="drop-shadow-[0_12px_40px_rgba(0,0,0,0.35)]"
        />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/brand/xfold-logo-reverse.svg"
          alt="XFOLD"
          width={320}
          height={96}
          className="w-[min(320px,62vw)]"
          draggable={false}
        />
        <p className="max-w-[26ch] text-[clamp(1.1rem,2.4vw,1.9rem)] leading-tight text-balance opacity-80">
          Nobody should fold shirts for a living.
        </p>
      </div>
    ),
  },
  {
    id: "problem",
    tone: "light",
    label: "The problem",
    Content: () => (
      <Stack>
        <Eyebrow>The problem</Eyebrow>
        <Headline>
          A folding machine does 1,000 shirts an hour. A person still has to feed it.
        </Headline>
        <Lede>
          Industrial folders are solved hardware — <em>once the garment is lying flat and square
          on the infeed</em>. Getting it there is still a human: take it from the pile, spread it,
          square it, check it, bag it. Eight hours a shift, and Europe can no longer fill those
          shifts.
        </Lede>
      </Stack>
    ),
  },
  {
    id: "why-hard",
    tone: "light",
    label: "Why it's unautomated",
    Content: () => (
      <Stack>
        <Eyebrow>Why it is still manual</Eyebrow>
        <Headline>Cloth has no shape to grab.</Headline>
        <Lede>
          A shirt has no fixed geometry, no two arrive the same way, and some of them are torn or
          stained. Classical pick-and-place assumes a rigid part in a known pose — which is exactly
          what a garment is not.
        </Lede>
      </Stack>
    ),
  },
  {
    id: "solution",
    tone: "dark",
    label: "The solution",
    Content: () => (
      <Stack>
        <Eyebrow>XFOLD</Eyebrow>
        <Headline>
          The whole station, automated — pile to sealed carton.
        </Headline>
        <Lede>
          One line, one controller, no human in the loop. We built it end to end in real physics,
          so the fold either comes out square or it does not — there is nothing to fake.
        </Lede>
      </Stack>
    ),
  },
  {
    id: "line",
    tone: "light",
    label: "The line",
    Content: () => (
      <div className="flex w-full flex-col gap-8">
        <Stack>
          <Eyebrow>How it works</Eyebrow>
          <Headline>Six stations, fourteen phases, one state machine.</Headline>
        </Stack>
        <Stations
          items={[
            { name: "Infeed", note: "Garment lands on the belt, any heading" },
            { name: "Turner", note: "Two lanes yaw it square, collar downstream" },
            { name: "Press", note: "Heated platen irons it flat on the belt" },
            { name: "QC", note: "Top-down shot; rejects go to the tote" },
            { name: "Folder", note: "Three flaps → a 31 × 33 cm pack" },
            { name: "Bagger", note: "Peel, bag, seal, RFID tag, carton" },
          ]}
        />
      </div>
    ),
  },
  {
    id: "variability",
    tone: "light",
    label: "Variability",
    Content: () => (
      <div className="flex w-full flex-col gap-10">
        <Stack>
          <Eyebrow>Generalization</Eyebrow>
          <Headline>Same controller, 30 garments and a torn one every time.</Headline>
        </Stack>
        <Stats>
          <Stat
            value="6"
            unit="SKUs"
            caption="Tee, work tee, jersey, tank, polo, dress — each its own mesh"
          />
          <Stat value="30" unit="variants" caption="Clean, torn, and three stain patterns per SKU" />
          <Stat value="∞" unit="poses" caption="Seeded heading and crumple; the line squares it" />
          <Stat value="1" unit="photo" caption="Any picture becomes a cut-out garment on the belt" />
        </Stats>
      </div>
    ),
  },
  {
    id: "qc",
    tone: "light",
    label: "Quality control",
    Content: () => (
      <Stack>
        <Eyebrow>Perceive · decide · execute</Eyebrow>
        <Headline>The line looks at every garment before it folds it.</Headline>
        <Lede>
          The belt stops under the QC camera and a flash fires. Torn and stained garments are lifted
          off to the reject tote; the rest go on. After the fold, a second camera scores the pack:
          100 minus wrinkle coverage, minus whatever sits off the deck.
        </Lede>
      </Stack>
    ),
  },
  {
    id: "physics",
    tone: "dark",
    label: "Real physics",
    Content: () => (
      <div className="flex w-full flex-col gap-10">
        <Stack>
          <Eyebrow>Not an animation</Eyebrow>
          <Headline>Deformable cloth, on two physics engines.</Headline>
          <Lede>
            The garment is a finite-element sheet, not a keyframe. The same controller steps MuJoCo
            on a laptop and NVIDIA Isaac Sim / PhysX on an L4 — and they agree.
          </Lede>
        </Stack>
        <Stats>
          <Stat value="29 / 29" caption="Identical events across both engines" />
          <Stat value="2" unit="mm" caption="Pack size agreement, MuJoCo vs PhysX" />
          <Stat value="1×" unit="realtime" caption="A 47 s cycle runs in 45 s on the GPU box" />
          <Stat value="20×" unit="speed" caption="Push the line until it drops the garment" />
        </Stats>
      </div>
    ),
  },
  {
    id: "control-room",
    tone: "light",
    label: "Control room",
    Content: () => (
      <Stack>
        <Eyebrow>The operator&apos;s view</Eyebrow>
        <Headline>Every cycle is launched, watched, and kept.</Headline>
        <Lede>
          A browser control room: launch a run or a batch, watch the camera live, scrub the replay,
          read the measurements. Every run is journalled with its video, its product shot and its
          numbers — so an improvement is something we can show, not something we claim.
        </Lede>
      </Stack>
    ),
  },
  {
    id: "closing",
    tone: "dark",
    label: "XFOLD",
    Content: () => (
      <div className="flex w-full flex-col items-center gap-8 text-center">
        <XFoldLoader size={104} tone="dark" surface={DARK_SURFACE} decorative />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/brand/xfold-logo-reverse.svg"
          alt="XFOLD"
          width={320}
          height={96}
          className="w-[min(260px,55vw)]"
          draggable={false}
        />
        <p className="max-w-[24ch] text-[clamp(1.1rem,2.4vw,1.9rem)] leading-tight text-balance">
          The plant is XML. The process is Python. The next line is hardware.
        </p>
        <p className="font-mono text-xs tracking-[0.14em] uppercase opacity-55">
          HackSpain &apos;26 · THEKER Robotics
        </p>
      </div>
    ),
  },
];
