"use client";

type DesignPreviewProps = {
  src: string;
  outline: number[][];
  attached: boolean;
};

/** Detected garment: preview is clipped to the same outline the sim mesh uses. */
export function DesignPreview({ src, outline, attached }: DesignPreviewProps) {
  const points = outline.map(([u, v]) => `${u},${v}`).join(" ");
  const clip =
    outline.length >= 3
      ? `polygon(${outline.map(([u, v]) => `${u * 100}% ${v * 100}%`).join(", ")})`
      : undefined;

  return (
    <div className="overflow-hidden rounded-[var(--radius-sm)] border border-border bg-muted/40">
      <div className="mx-auto w-full max-w-[20rem]">
        <div className="relative aspect-square w-full overflow-hidden bg-[#f6f6f8]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt=""
            className="absolute inset-0 size-full object-contain"
            style={clip ? { clipPath: clip } : undefined}
          />
          {outline.length >= 3 ? (
            <svg
              viewBox="0 0 1 1"
              className="pointer-events-none absolute inset-0 size-full"
              aria-hidden
            >
              <polygon
                points={points}
                fill="none"
                stroke="#fff"
                strokeWidth={0.012}
                strokeLinejoin="round"
              />
              <polygon
                points={points}
                fill="none"
                stroke="#2b1810"
                strokeWidth={0.005}
                strokeLinejoin="round"
              />
            </svg>
          ) : null}
        </div>
      </div>
      <p className="px-3 py-2 text-[13px] text-muted-foreground">
          Cut-out
        {attached
          ? " · ready: the mesh follows the outline, print on both faces."
          : " · press Upload garment to use it in the simulation."}
      </p>
    </div>
  );
}
