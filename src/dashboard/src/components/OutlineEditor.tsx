"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Eraser, PenLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  CUTOUT_SIZE,
  OUTLINE_STROKE,
  fillOutline,
  maskToOutlineCanvas,
  outlineToCutout,
} from "@/lib/garment-cutout";

type Tool = "draw" | "erase";

/** The line is thin so it can be placed precisely; the rubber is fatter. */
const NIB = OUTLINE_STROKE;
const RUBBER = 16;

const LINE_RGB = [255, 122, 0] as const;
const FILL_RGB = [255, 122, 0] as const;

export function OutlineEditor({
  open,
  sourceUrl,
  maskUrl,
  onOpenChange,
  onSave,
}: {
  open: boolean;
  sourceUrl: string;
  maskUrl: string;
  onOpenChange: (open: boolean) => void;
  onSave: (next: { previewUrl: string; maskUrl: string; outline: number[][] }) => void;
}) {
  const viewRef = useRef<HTMLCanvasElement>(null);
  const lineRef = useRef<HTMLCanvasElement | null>(null);
  const sourceRef = useRef<HTMLImageElement | null>(null);
  const fillRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);
  const [tool, setTool] = useState<Tool>("draw");
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toolRef = useRef<Tool>("draw");

  function pickTool(next: Tool) {
    toolRef.current = next;
    setTool(next);
  }

  /** Repaint the canvas: photo, then the region the line encloses, then the line. */
  const paintView = useCallback(() => {
    const view = viewRef.current;
    const line = lineRef.current;
    const source = sourceRef.current;
    if (!view || !line || !source) return;
    const ctx = view.getContext("2d");
    if (!ctx) return;
    const size = CUTOUT_SIZE;
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "#f6f6f8";
    ctx.fillRect(0, 0, size, size);
    ctx.drawImage(source, 0, 0, size, size);
    const fill = fillRef.current;
    if (fill) ctx.drawImage(fill, 0, 0);
    // Tint the line itself: the layer stores white, the operator sees accent.
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.drawImage(tinted(line, LINE_RGB, 1), 0, 0);
    ctx.restore();
  }, []);

  /** Re-flood after a stroke so the enclosed area (and the warning) stay honest. */
  const refill = useCallback(() => {
    const line = lineRef.current;
    if (!line) return;
    const { bits, interior } = fillOutline(line);
    const size = CUTOUT_SIZE;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const image = ctx.createImageData(size, size);
    for (let i = 0; i < bits.length; i++) {
      const p = i * 4;
      image.data[p] = FILL_RGB[0];
      image.data[p + 1] = FILL_RGB[1];
      image.data[p + 2] = FILL_RGB[2];
      image.data[p + 3] = bits[i] ? 56 : 0;
    }
    ctx.putImageData(image, 0, 0);
    fillRef.current = canvas;
    setClosed(interior > 0);
  }, []);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const source = new Image();
    const maskImg = new Image();
    let pending = 2;
    const ready = () => {
      pending -= 1;
      if (pending || cancelled) return;
      lineRef.current = maskToOutlineCanvas(maskImg);
      sourceRef.current = source;
      const view = viewRef.current;
      if (view) {
        view.width = CUTOUT_SIZE;
        view.height = CUTOUT_SIZE;
      }
      refill();
      paintView();
    };
    source.onload = ready;
    maskImg.onload = ready;
    source.src = sourceUrl;
    maskImg.src = maskUrl;
    return () => {
      cancelled = true;
    };
  }, [open, sourceUrl, maskUrl, paintView, refill]);

  function canvasPoint(event: React.PointerEvent<HTMLCanvasElement>) {
    const view = viewRef.current;
    if (!view) return null;
    const rect = view.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * CUTOUT_SIZE,
      y: ((event.clientY - rect.top) / rect.height) * CUTOUT_SIZE,
    };
  }

  function stamp(from: { x: number; y: number } | null, to: { x: number; y: number }) {
    const line = lineRef.current;
    if (!line) return;
    const ctx = line.getContext("2d");
    if (!ctx) return;
    setError(null);
    const draw = toolRef.current === "draw";
    const width = draw ? NIB : RUBBER;
    ctx.globalCompositeOperation = draw ? "source-over" : "destination-out";
    ctx.strokeStyle = "#ffffff";
    ctx.fillStyle = "#ffffff";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = width;
    if (from) {
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(to.x, to.y, width / 2, 0, Math.PI * 2);
      ctx.fill();
    }
    paintView();
  }

  function endStroke() {
    if (!drawing.current) return;
    drawing.current = false;
    last.current = null;
    refill();
    paintView();
  }

  async function save() {
    const line = lineRef.current;
    if (!line) return;
    setBusy(true);
    setError(null);
    try {
      const next = await outlineToCutout(sourceUrl, line);
      if (next.outline.length < 3) {
        setError("Close the outline around the garment before saving.");
        return;
      }
      onSave(next);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the outline.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-4 overflow-hidden rounded-[var(--radius-sm)] border border-divider bg-surface p-5 sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-[17px] font-semibold">Edit outline</DialogTitle>
          <DialogDescription className="text-[13px]">
            Draw or rub out the cut line. The photo underneath never changes — only
            the line does, and the sim cuts along it.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant={tool === "draw" ? "default" : "outline"}
              aria-pressed={tool === "draw"}
              onClick={() => pickTool("draw")}
            >
              <PenLine className="size-3.5" aria-hidden />
              Draw line
            </Button>
            <Button
              type="button"
              size="sm"
              variant={tool === "erase" ? "default" : "outline"}
              aria-pressed={tool === "erase"}
              onClick={() => pickTool("erase")}
            >
              <Eraser className="size-3.5" aria-hidden />
              Erase line
            </Button>
          </div>
          <canvas
            ref={viewRef}
            className="aspect-square w-full touch-none border border-divider bg-[#f6f6f8]"
            style={{ cursor: tool === "erase" ? "cell" : "crosshair" }}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              drawing.current = true;
              const point = canvasPoint(event);
              last.current = point;
              if (point) stamp(null, point);
            }}
            onPointerMove={(event) => {
              if (!drawing.current) return;
              const point = canvasPoint(event);
              if (!point) return;
              stamp(last.current, point);
              last.current = point;
            }}
            onPointerUp={endStroke}
            onPointerCancel={endStroke}
            onPointerLeave={endStroke}
          />
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : closed ? (
            <p className="text-[13px] text-muted-foreground">
              Shaded area is what the sim keeps.
            </p>
          ) : (
            <p className="text-[13px] text-destructive" role="status">
              The line has a gap — close the loop or nothing is enclosed.
            </p>
          )}
        </div>
        <DialogFooter className="-mx-5 -mb-5 gap-2 border-t border-divider px-5 py-3">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save outline"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Recolour a white-on-transparent layer without touching its alpha. */
function tinted(
  layer: HTMLCanvasElement,
  rgb: readonly [number, number, number],
  alpha: number,
): HTMLCanvasElement {
  const out = document.createElement("canvas");
  out.width = layer.width;
  out.height = layer.height;
  const ctx = out.getContext("2d");
  if (!ctx) return layer;
  ctx.drawImage(layer, 0, 0);
  ctx.globalCompositeOperation = "source-in";
  ctx.fillStyle = `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
  ctx.fillRect(0, 0, out.width, out.height);
  return out;
}
