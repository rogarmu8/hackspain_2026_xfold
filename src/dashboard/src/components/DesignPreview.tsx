"use client";

import { Pencil } from "lucide-react";

type DesignPreviewProps = {
  src: string;
  outline: number[][];
  onEdit?: () => void;
};

/** Detected garment: preview is clipped to the same outline the sim mesh uses. */
export function DesignPreview({ src, outline, onEdit }: DesignPreviewProps) {
  const points = outline.map(([u, v]) => `${u},${v}`).join(" ");
  const clip =
    outline.length >= 3
      ? `polygon(${outline.map(([u, v]) => `${u * 100}% ${v * 100}%`).join(", ")})`
      : undefined;

  return (
    <div className="overflow-hidden rounded-[var(--radius-sm)] border border-border bg-muted/40">
      <div className="mx-auto w-full max-w-[20rem]">
        <div className="group relative aspect-square w-full overflow-hidden bg-[#f6f6f8]">
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
          {onEdit ? (
            <button
              type="button"
              onClick={onEdit}
              className="absolute right-2 top-2 inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] bg-white/90 px-2 py-1.5 text-[12px] font-semibold text-ink shadow-sm ring-1 ring-divider transition-[padding,background-color] duration-[var(--motion-feedback)] hover:bg-white group-hover:px-2.5"
            >
              <Pencil className="size-3.5" aria-hidden />
              <span className="max-w-0 overflow-hidden whitespace-nowrap opacity-0 transition-[max-width,opacity] duration-[var(--motion-feedback)] group-hover:max-w-[7rem] group-hover:opacity-100 group-focus-within:max-w-[7rem] group-focus-within:opacity-100 [@media(hover:none)]:max-w-[7rem] [@media(hover:none)]:opacity-100">
                Edit outline
              </span>
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
