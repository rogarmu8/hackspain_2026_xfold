"use client";

import Link from "next/link";
import { useState } from "react";
import { XFoldLoader } from "@/components/XFoldLoader";

// Mark frame (96 units = 28 px) with the shirt 4 px below the top, like the centred 28 px mark in a 36 px row; 40 px tall so the packaging box (canvas y ≤ 123) stays visible.
const UNIT = 96 / 28;
const BRAND_VIEWBOX = `8 ${4 - 4 * UNIT} 96 ${40 * UNIT}`;

/** A single-cycle easter egg; the link still navigates normally. */
export function XFoldBrandLink() {
  const [cycle, setCycle] = useState(0);
  const [active, setActive] = useState(false);
  const play = () => {
    if (active || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    setCycle((value) => value + 1);
    setActive(true);
  };
  return (
    <Link href="/" aria-label="XFOLD · runs" title="XFOLD · runs" className="flex shrink-0 items-center text-ink no-underline" onPointerEnter={(event) => { if (event.pointerType !== "touch") play(); }} onFocus={play}>
      <span className="relative flex h-9 w-7 items-center justify-center">
        <XFoldLoader size={28} height={40} viewBox={BRAND_VIEWBOX} playing={active} loop={false} replayKey={cycle} decorative className="absolute top-0 left-0" onComplete={() => setActive(false)} />
      </span>
      <span className="relative block h-[29px] w-[68px] overflow-hidden max-[640px]:hidden" aria-hidden="true">
        {/* Crop only the mark from the approved horizontal asset; preserve its lettering. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/xfold-logo-primary.svg" alt="" width={96} height={29} className="absolute top-0 left-[-28px] max-w-none" draggable={false} />
      </span>
    </Link>
  );
}
