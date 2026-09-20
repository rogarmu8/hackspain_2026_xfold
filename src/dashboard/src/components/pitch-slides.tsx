"use client";

import type { ReactNode } from "react";
import { XFoldLoader } from "@/components/XFoldLoader";

export type SlideTone = "light" | "dark";

export type Slide = {
  id: string;
  /** Surface the slide paints; the deck chrome follows it. */
  tone: SlideTone;
  /** Short name for the footer and the screen-reader announcement. */
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
    <h2 className="max-w-[16ch] text-[clamp(2.25rem,6vw,4.75rem)] leading-[1.02] font-semibold tracking-[-0.02em] text-balance">
      {children}
    </h2>
  );
}

function Lede({ children }: { children: ReactNode }) {
  return (
    <p className="max-w-[40ch] text-[clamp(1.05rem,1.9vw,1.6rem)] leading-[1.4] opacity-70 text-pretty">
      {children}
    </p>
  );
}

function Stack({ children }: { children: ReactNode }) {
  return <div className="flex flex-col items-start gap-6 sm:gap-8">{children}</div>;
}

/** The orange rule that carries a number. */
function Stat({ value, caption }: { value: string; caption: string }) {
  return (
    <div className="border-t-2 border-[var(--primary)] pt-3">
      <p className="tabular text-[clamp(1.75rem,3.6vw,3rem)] leading-none font-semibold">{value}</p>
      <p className="mt-2 max-w-[18ch] text-sm leading-snug opacity-65">{caption}</p>
    </div>
  );
}

/** The line, drawn as the stations the garment actually passes through. */
function Stations({ items }: { items: string[] }) {
  return (
    <ol className="grid w-full gap-px overflow-hidden rounded-[var(--radius)] border border-current/15 bg-current/15 sm:grid-cols-3 lg:grid-cols-6">
      {items.map((name, index) => (
        <li key={name} className="flex flex-col gap-2 bg-[var(--slide-surface)] p-4 lg:p-5">
          <span className="font-mono text-[11px] tracking-[0.12em] opacity-40">
            {String(index + 1).padStart(2, "0")}
          </span>
          <span className="text-base leading-tight font-semibold sm:text-lg">{name}</span>
        </li>
      ))}
    </ol>
  );
}

/* --- The deck --------------------------------------------------------- */

export const SLIDES: Slide[] = [
  {
    id: "portada",
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
        <p className="max-w-[22ch] text-[clamp(1.1rem,2.4vw,1.9rem)] leading-tight text-balance opacity-80">
          Nadie debería doblar camisetas para vivir.
        </p>
      </div>
    ),
  },
  {
    id: "problema",
    tone: "light",
    label: "El problema",
    Content: () => (
      <Stack>
        <Eyebrow>El problema</Eyebrow>
        <Headline>Mil camisetas por hora. Y una persona dándoselas.</Headline>
        <Lede>La plegadora ya existe. Coger, estirar, cuadrar, revisar y embolsar, no.</Lede>
      </Stack>
    ),
  },
  {
    id: "solucion",
    tone: "dark",
    label: "La solución",
    Content: () => (
      <div className="flex w-full flex-col gap-10">
        <Stack>
          <Eyebrow>La solución</Eyebrow>
          <Headline>La estación entera, automatizada.</Headline>
        </Stack>
        <Stations items={["Entrada", "Girador", "Prensa", "Control", "Plegado", "Embolsado"]} />
      </div>
    ),
  },
  {
    id: "resultados",
    tone: "light",
    label: "Resultados",
    Content: () => (
      <div className="flex w-full flex-col gap-10">
        <Stack>
          <Eyebrow>Medido, no prometido</Eyebrow>
          <Headline>Física real, dos motores.</Headline>
        </Stack>
        <div className="grid w-full gap-6 sm:grid-cols-2 lg:grid-cols-4 lg:gap-8">
          <Stat value="30" caption="Prendas: rotas, manchadas, torcidas" />
          <Stat value="29 / 29" caption="Mismos eventos en MuJoCo y en Isaac Sim" />
          <Stat value="31 × 33 cm" caption="Paquete doblado, ±2 mm entre motores" />
          <Stat value="1×" caption="Tiempo real: ciclo de 47 s" />
        </div>
      </div>
    ),
  },
  {
    id: "cierre",
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
        <p className="max-w-[20ch] text-[clamp(1.1rem,2.4vw,1.9rem)] leading-tight text-balance">
          Nadie en el bucle.
        </p>
        <p className="font-mono text-xs tracking-[0.14em] uppercase opacity-55">
          HackSpain &apos;26 · THEKER Robotics
        </p>
      </div>
    ),
  },
];
