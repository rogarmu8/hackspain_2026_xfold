"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Eraser, Paintbrush } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { CUTOUT_SIZE, composeCutout } from "@/lib/garment-cutout";

type Tool = "paint" | "erase";

const BRUSH = 18;

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
  const maskRef = useRef<HTMLCanvasElement | null>(null);
  const sourceRef = useRef<HTMLImageElement | null>(null);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);
  const [tool, setTool] = useState<Tool>("paint");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toolRef = useRef<Tool>(tool);
  toolRef.current = tool;

  const paintView = useCallback(() => {
    const view = viewRef.current;
    const mask = maskRef.current;
    const source = sourceRef.current;
    if (!view || !mask || !source) return;
    const ctx = view.getContext("2d");
    if (!ctx) return;
    const size = CUTOUT_SIZE;
    ctx.fillStyle = "#f6f6f8";
    ctx.fillRect(0, 0, size, size);
    ctx.globalAlpha = 0.38;
    ctx.drawImage(source, 0, 0, size, size);
    ctx.globalAlpha = 1;
    ctx.save();
    ctx.drawImage(source, 0, 0, size, size);
    ctx.globalCompositeOperation = "destination-in";
    ctx.drawImage(mask, 0, 0, size, size);
    ctx.restore();
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
      const mask = document.createElement("canvas");
      mask.width = CUTOUT_SIZE;
      mask.height = CUTOUT_SIZE;
      const mctx = mask.getContext("2d");
      if (!mctx) return;
      mctx.drawImage(maskImg, 0, 0, CUTOUT_SIZE, CUTOUT_SIZE);
      maskRef.current = mask;
      sourceRef.current = source;
      const view = viewRef.current;
      if (view) {
        view.width = CUTOUT_SIZE;
        view.height = CUTOUT_SIZE;
      }
      paintView();
    };
    source.onload = ready;
    maskImg.onload = ready;
    source.src = sourceUrl;
    maskImg.src = maskUrl;
    return () => {
      cancelled = true;
    };
  }, [open, sourceUrl, maskUrl, paintView]);

  function canvasPoint(event: React.PointerEvent<HTMLCanvasElement>) {
    const view = viewRef.current;
    if (!view) return null;
    const rect = view.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * CUTOUT_SIZE;
    const y = ((event.clientY - rect.top) / rect.height) * CUTOUT_SIZE;
    return { x, y };
  }

  function stamp(from: { x: number; y: number } | null, to: { x: number; y: number }) {
    const mask = maskRef.current;
    if (!mask) return;
    const ctx = mask.getContext("2d");
    if (!ctx) return;
    const paint = toolRef.current === "paint";
    ctx.globalCompositeOperation = paint ? "source-over" : "destination-out";
    ctx.strokeStyle = "#ffffff";
    ctx.fillStyle = "#ffffff";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = BRUSH * 2;
    if (from) {
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(to.x, to.y, BRUSH, 0, Math.PI * 2);
      ctx.fill();
    }
    paintView();
  }

  async function save() {
    const mask = maskRef.current;
    if (!mask) return;
    setBusy(true);
    setError(null);
    try {
      const next = await composeCutout(sourceUrl, mask.toDataURL("image/png"));
      if (next.outline.length < 3) {
        setError("Paint a garment region before saving.");
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
            Paint to add cloth, erase to cut it away. Save sends this silhouette with Launch.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant={tool === "paint" ? "default" : "outline"}
              aria-pressed={tool === "paint"}
              onClick={() => setTool("paint")}
            >
              <Paintbrush className="size-3.5" aria-hidden />
              Paint
            </Button>
            <Button
              type="button"
              size="sm"
              variant={tool === "erase" ? "default" : "outline"}
              aria-pressed={tool === "erase"}
              onClick={() => setTool("erase")}
            >
              <Eraser className="size-3.5" aria-hidden />
              Erase
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
            onPointerUp={() => {
              drawing.current = false;
              last.current = null;
            }}
            onPointerCancel={() => {
              drawing.current = false;
              last.current = null;
            }}
          />
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              The faded photo is the original crop so you can paint pixels back.
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
