/** Detect a garment on a plain backdrop and crop it to a square print + outline. */

export const CUTOUT_SIZE = 512;
const DETECT_SIZE = 256;
const CLOTH = { r: 246, g: 246, b: 248 };

export type GarmentCutout = {
  /** Square crop of the photo, unmasked — paint/erase can restore pixels. */
  sourceUrl: string;
  /** Square print the operator sees (mask applied, cloth-white ground). */
  previewUrl: string;
  /** White-on-transparent mask at CUTOUT_SIZE. */
  maskUrl: string;
  outline: number[][];
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function drawToCanvas(
  source: CanvasImageSource,
  width: number,
  height: number,
): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("Could not read the image.");
  ctx.drawImage(source, 0, 0, width, height);
  return canvas;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Could not read the image."));
    img.src = src;
  });
}

function borderBackground(data: Uint8ClampedArray, w: number, h: number) {
  const samples: number[] = [];
  const push = (i: number) => {
    samples.push(data[i], data[i + 1], data[i + 2]);
  };
  for (let x = 0; x < w; x++) {
    push((x * 4));
    push(((h - 1) * w + x) * 4);
  }
  for (let y = 0; y < h; y++) {
    push((y * w) * 4);
    push((y * w + (w - 1)) * 4);
  }
  const count = samples.length / 3;
  const mid = (channel: number) => {
    const vals: number[] = [];
    for (let i = channel; i < samples.length; i += 3) vals.push(samples[i]);
    vals.sort((a, b) => a - b);
    return vals[Math.floor(vals.length / 2)] ?? 255;
  };
  if (count < 4) return { r: 255, g: 255, b: 255 };
  return { r: mid(0), g: mid(1), b: mid(2) };
}

function autoThresh(data: Uint8ClampedArray, w: number, h: number, bg: { r: number; g: number; b: number }) {
  const ring: number[] = [];
  const distAt = (i: number) =>
    Math.max(
      Math.abs(data[i] - bg.r),
      Math.abs(data[i + 1] - bg.g),
      Math.abs(data[i + 2] - bg.b),
    );
  for (let x = 0; x < w; x++) {
    ring.push(distAt(x * 4), distAt(((h - 1) * w + x) * 4));
  }
  for (let y = 0; y < h; y++) {
    ring.push(distAt((y * w) * 4), distAt((y * w + w - 1) * 4));
  }
  ring.sort((a, b) => a - b);
  const p88 = ring[Math.floor(ring.length * 0.88)] ?? 20;
  return Math.max(22, p88 + 10);
}

function floodBackground(
  isBg: Uint8Array,
  w: number,
  h: number,
): Uint8Array {
  const flooded = new Uint8Array(w * h);
  const stack: number[] = [];
  const tryPush = (x: number, y: number) => {
    if (x < 0 || y < 0 || x >= w || y >= h) return;
    const i = y * w + x;
    if (flooded[i] || !isBg[i]) return;
    flooded[i] = 1;
    stack.push(i);
  };
  for (let x = 0; x < w; x++) {
    tryPush(x, 0);
    tryPush(x, h - 1);
  }
  for (let y = 0; y < h; y++) {
    tryPush(0, y);
    tryPush(w - 1, y);
  }
  while (stack.length) {
    const i = stack.pop()!;
    const x = i % w;
    const y = (i / w) | 0;
    tryPush(x - 1, y);
    tryPush(x + 1, y);
    tryPush(x, y - 1);
    tryPush(x, y + 1);
  }
  return flooded;
}

function largestComponent(fg: Uint8Array, w: number, h: number): Uint8Array {
  const seen = new Uint8Array(w * h);
  const out = new Uint8Array(w * h);
  let best: number[] = [];
  for (let i = 0; i < fg.length; i++) {
    if (!fg[i] || seen[i]) continue;
    const blob: number[] = [];
    const stack = [i];
    seen[i] = 1;
    while (stack.length) {
      const cur = stack.pop()!;
      blob.push(cur);
      const x = cur % w;
      const y = (cur / w) | 0;
      const neigh = [cur - 1, cur + 1, cur - w, cur + w];
      const ok = [x > 0, x + 1 < w, y > 0, y + 1 < h];
      for (let k = 0; k < 4; k++) {
        if (!ok[k]) continue;
        const n = neigh[k];
        if (n >= 0 && n < fg.length && fg[n] && !seen[n]) {
          seen[n] = 1;
          stack.push(n);
        }
      }
    }
    if (blob.length > best.length) best = blob;
  }
  for (const i of best) out[i] = 1;
  return out;
}

function detectMask(image: ImageData): Uint8Array {
  const { data, width: w, height: h } = image;
  const bg = borderBackground(data, w, h);
  const thresh = autoThresh(data, w, h, bg);
  const isBg = new Uint8Array(w * h);
  for (let i = 0, p = 0; i < w * h; i++, p += 4) {
    const d = Math.max(
      Math.abs(data[p] - bg.r),
      Math.abs(data[p + 1] - bg.g),
      Math.abs(data[p + 2] - bg.b),
    );
    isBg[i] = d <= thresh ? 1 : 0;
  }
  const flooded = floodBackground(isBg, w, h);
  const fg = new Uint8Array(w * h);
  let count = 0;
  for (let i = 0; i < fg.length; i++) {
    if (!flooded[i]) {
      fg[i] = 1;
      count++;
    }
  }
  const frac = count / fg.length;
  if (frac < 0.02) {
    throw new Error(
      "No garment in view; try a plainer backdrop with the clothing centred.",
    );
  }
  if (frac > 0.94) {
    fg.fill(1);
    return fg;
  }
  return largestComponent(fg, w, h);
}

function maskBBox(mask: Uint8Array, w: number, h: number) {
  let minX = w;
  let minY = h;
  let maxX = 0;
  let maxY = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (!mask[y * w + x]) continue;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
  }
  if (maxX < minX) return null;
  const pad = 4;
  return {
    x: Math.max(0, minX - pad),
    y: Math.max(0, minY - pad),
    w: Math.min(w - 1, maxX + pad) - Math.max(0, minX - pad) + 1,
    h: Math.min(h - 1, maxY + pad) - Math.max(0, minY - pad) + 1,
  };
}

/** Neighbours clockwise from west; index 8 never occurs (that is the centre). */
const STEP = [
  [-1, 0], [-1, -1], [0, -1], [1, -1],
  [1, 0], [1, 1], [0, 1], [-1, 1],
] as const;
/** Offset (dx+1)*3 + (dy+1) back to its STEP index. */
const STEP_OF = [1, 0, 7, 2, -1, 6, 3, 4, 5] as const;

/**
 * Moore-neighbour walk round the rim of a blob, in pixels.
 *
 * The backtrack is always the last *background* neighbour looked at, so the
 * walk hugs the rim instead of stepping inside — which is what lets a notch
 * or a waist survive the trace.
 */
function traceRing(mask: Uint8Array, w: number, h: number): number[][] {
  let start = -1;
  for (let i = 0; i < mask.length; i++) {
    if (mask[i]) {
      start = i;
      break;
    }
  }
  if (start < 0) return [];
  const sx = start % w;
  const sy = (start / w) | 0;
  const on = (x: number, y: number) =>
    x >= 0 && y >= 0 && x < w && y < h && mask[y * w + x] === 1;
  const ring: number[][] = [];
  let cx = sx;
  let cy = sy;
  let back = 0;                       // west of the first raster hit is empty
  const first = back;
  const limit = 8 * (w + h) + 16;
  for (let n = 0; n < limit; n++) {
    ring.push([cx, cy]);
    let found = -1;
    let prev = back;
    for (let k = 0; k < 8; k++) {
      const d = (back + k) % 8;
      if (on(cx + STEP[d][0], cy + STEP[d][1])) {
        found = d;
        break;
      }
      prev = d;
    }
    if (found < 0) break;             // a lone pixel
    const nx = cx + STEP[found][0];
    const ny = cy + STEP[found][1];
    // Stand on the empty neighbour we looked at just before this one.
    const bx = cx + STEP[prev][0] - nx;
    const by = cy + STEP[prev][1] - ny;
    back = STEP_OF[(bx + 1) * 3 + (by + 1)];
    if (back < 0) break;
    cx = nx;
    cy = ny;
    if (cx === sx && cy === sy && back === first) break;
  }
  return ring;
}

function rdp(points: number[][], eps: number): number[][] {
  if (points.length < 3) return points;
  const [ax, ay] = points[0];
  const [bx, by] = points[points.length - 1];
  const dx = bx - ax;
  const dy = by - ay;
  const norm = Math.hypot(dx, dy);
  let worst = 0;
  let at = 0;
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = points[i];
    const d =
      norm < 1e-9
        ? Math.hypot(px - ax, py - ay)
        : Math.abs(dy * px - dx * py + bx * ay - by * ax) / norm;
    if (d > worst) {
      worst = d;
      at = i;
    }
  }
  if (worst <= eps) return [points[0], points[points.length - 1]];
  const left = rdp(points.slice(0, at + 1), eps);
  const right = rdp(points.slice(at), eps);
  return [...left.slice(0, -1), ...right];
}

const OUTLINE_MAX_POINTS = 160;

/**
 * Closed loop round the mask, in the letterboxed unit square the sim reads.
 *
 * This follows the rim pixel by pixel, so a neckline notch or the gap between
 * two legs survives into the sewing loop the mesh is cut to.
 */
function maskOutline(
  mask: Uint8Array,
  w: number,
  h: number,
  box: { x: number; y: number; w: number; h: number },
): number[][] {
  let ring = traceRing(largestComponent(mask, w, h), w, h);
  if (ring.length < 4) return [];
  const span = Math.max(box.w, box.h);
  let eps = span * 0.002;
  ring = rdp(ring, eps);
  while (ring.length > OUTLINE_MAX_POINTS && eps < span) {
    eps *= 1.6;
    ring = rdp(ring, eps);
  }
  if (ring.length < 3) return [];
  const ox = box.x - (span - box.w) / 2;
  const oy = box.y - (span - box.h) / 2;
  const denom = Math.max(span - 1, 1);
  const uv = ring.map(([x, y]) => [
    clamp((x - ox) / denom, 0, 1),
    clamp((y - oy) / denom, 0, 1),
  ]);
  const first = uv[0];
  const last = uv[uv.length - 1];
  if (first[0] !== last[0] || first[1] !== last[1]) uv.push([first[0], first[1]]);
  return uv;
}

function letterbox(boxW: number, boxH: number, size: number) {
  const scale = Math.min(size / Math.max(boxW, 1), size / Math.max(boxH, 1));
  const nw = Math.max(1, Math.round(boxW * scale));
  const nh = Math.max(1, Math.round(boxH * scale));
  return {
    nw,
    nh,
    dx: Math.floor((size - nw) / 2),
    dy: Math.floor((size - nh) / 2),
  };
}

function canvasPng(canvas: HTMLCanvasElement): string {
  return canvas.toDataURL("image/png");
}

function paintSquare(
  img: HTMLImageElement,
  detectCanvas: HTMLCanvasElement,
  mask: Uint8Array,
  box: { x: number; y: number; w: number; h: number },
): { sourceUrl: string; previewUrl: string; maskUrl: string; outline: number[][] } {
  const dw = detectCanvas.width;
  const dh = detectCanvas.height;
  const sx = img.naturalWidth / dw;
  const sy = img.naturalHeight / dh;
  const crop = {
    x: box.x * sx,
    y: box.y * sy,
    w: box.w * sx,
    h: box.h * sy,
  };
  const size = CUTOUT_SIZE;
  const { nw, nh, dx, dy } = letterbox(box.w, box.h, size);

  const source = document.createElement("canvas");
  source.width = size;
  source.height = size;
  const sctx = source.getContext("2d");
  if (!sctx) throw new Error("Could not cut out the garment.");
  sctx.fillStyle = `rgb(${CLOTH.r}, ${CLOTH.g}, ${CLOTH.b})`;
  sctx.fillRect(0, 0, size, size);
  sctx.drawImage(img, crop.x, crop.y, crop.w, crop.h, dx, dy, nw, nh);

  const bits = new Uint8Array(size * size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = (x - dx) / Math.max(nw - 1, 1);
      const v = (y - dy) / Math.max(nh - 1, 1);
      if (u < 0 || v < 0 || u > 1 || v > 1) continue;
      const mx = box.x + Math.round(u * Math.max(box.w - 1, 1));
      const my = box.y + Math.round(v * Math.max(box.h - 1, 1));
      if (mx < 0 || my < 0 || mx >= dw || my >= dh) continue;
      if (mask[my * dw + mx]) bits[y * size + x] = 1;
    }
  }
  const maskCanvas = document.createElement("canvas");
  maskCanvas.width = size;
  maskCanvas.height = size;
  const mctx = maskCanvas.getContext("2d");
  if (!mctx) throw new Error("Could not cut out the garment.");
  const maskImage = mctx.createImageData(size, size);
  for (let i = 0; i < bits.length; i++) {
    const p = i * 4;
    const on = bits[i] ? 255 : 0;
    maskImage.data[p] = 255;
    maskImage.data[p + 1] = 255;
    maskImage.data[p + 2] = 255;
    maskImage.data[p + 3] = on;
  }
  mctx.putImageData(maskImage, 0, 0);

  const preview = document.createElement("canvas");
  preview.width = size;
  preview.height = size;
  const pctx = preview.getContext("2d");
  if (!pctx) throw new Error("Could not cut out the garment.");
  pctx.drawImage(source, 0, 0);
  pctx.globalCompositeOperation = "destination-in";
  pctx.drawImage(maskCanvas, 0, 0);
  pctx.globalCompositeOperation = "destination-over";
  pctx.fillStyle = `rgb(${CLOTH.r}, ${CLOTH.g}, ${CLOTH.b})`;
  pctx.fillRect(0, 0, size, size);
  pctx.globalCompositeOperation = "source-over";

  const fitted = maskBBox(bits, size, size);
  const outline = fitted ? maskOutline(bits, size, size, fitted) : [];
  return {
    sourceUrl: canvasPng(source),
    previewUrl: canvasPng(preview),
    maskUrl: canvasPng(maskCanvas),
    outline,
  };
}

export async function composeCutout(
  sourceUrl: string,
  maskUrl: string,
): Promise<{ previewUrl: string; outline: number[][]; maskUrl: string }> {
  const source = await loadImage(sourceUrl);
  const mask = await loadImage(maskUrl);
  const size = CUTOUT_SIZE;
  const preview = document.createElement("canvas");
  preview.width = size;
  preview.height = size;
  const pctx = preview.getContext("2d");
  if (!pctx) throw new Error("Could not update the outline.");
  pctx.fillStyle = `rgb(${CLOTH.r}, ${CLOTH.g}, ${CLOTH.b})`;
  pctx.fillRect(0, 0, size, size);
  pctx.drawImage(source, 0, 0, size, size);
  pctx.globalCompositeOperation = "destination-in";
  pctx.drawImage(mask, 0, 0, size, size);
  pctx.globalCompositeOperation = "destination-over";
  pctx.fillRect(0, 0, size, size);

  const maskCanvas = document.createElement("canvas");
  maskCanvas.width = size;
  maskCanvas.height = size;
  const mctx = maskCanvas.getContext("2d", { willReadFrequently: true });
  if (!mctx) throw new Error("Could not update the outline.");
  mctx.drawImage(mask, 0, 0, size, size);
  const data = mctx.getImageData(0, 0, size, size);
  const bits = new Uint8Array(size * size);
  for (let i = 0; i < bits.length; i++) {
    bits[i] = data.data[i * 4 + 3] > 32 ? 1 : 0;
  }
  const box = maskBBox(bits, size, size);
  return {
    previewUrl: canvasPng(preview),
    maskUrl: canvasPng(maskCanvas),
    outline: box ? maskOutline(bits, size, size, box) : [],
  };
}

/** Width of the editable outline stroke, in CUTOUT_SIZE pixels. */
export const OUTLINE_STROKE = 4;

function readBits(source: CanvasImageSource, size = CUTOUT_SIZE): Uint8Array {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("Could not read the outline.");
  ctx.drawImage(source, 0, 0, size, size);
  const data = ctx.getImageData(0, 0, size, size).data;
  const bits = new Uint8Array(size * size);
  for (let i = 0; i < bits.length; i++) bits[i] = data[i * 4 + 3] > 32 ? 1 : 0;
  return bits;
}

/**
 * Trace the rim of a filled mask into a stroke the operator can draw on.
 *
 * The editor works on this line, not on the silhouette: a pixel is on the rim
 * when it is inside the mask and touches something that is not.
 */
export function maskToOutlineCanvas(
  mask: CanvasImageSource,
  stroke = OUTLINE_STROKE,
): HTMLCanvasElement {
  const size = CUTOUT_SIZE;
  const bits = readBits(mask, size);
  const out = document.createElement("canvas");
  out.width = size;
  out.height = size;
  const ctx = out.getContext("2d");
  if (!ctx) throw new Error("Could not read the outline.");
  ctx.fillStyle = "#ffffff";
  const r = Math.max(1, Math.round(stroke / 2));
  const span = r * 2 + 1;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      if (!bits[y * size + x]) continue;
      const edge =
        x === 0 ||
        y === 0 ||
        x === size - 1 ||
        y === size - 1 ||
        !bits[y * size + x - 1] ||
        !bits[y * size + x + 1] ||
        !bits[(y - 1) * size + x] ||
        !bits[(y + 1) * size + x];
      if (edge) ctx.fillRect(x - r, y - r, span, span);
    }
  }
  return out;
}

export type OutlineFill = {
  /** Outline plus everything it encloses. */
  bits: Uint8Array;
  /** Pixels strictly inside the loop. Zero means the loop leaks. */
  interior: number;
  /** Pixels of drawn line. */
  stroke: number;
};

/** Flood the frame from its border; whatever the line keeps out is the garment. */
export function fillOutline(outline: CanvasImageSource): OutlineFill {
  const size = CUTOUT_SIZE;
  const line = readBits(outline, size);
  const open = new Uint8Array(size * size);
  let stroke = 0;
  for (let i = 0; i < line.length; i++) {
    if (line[i]) stroke++;
    else open[i] = 1;
  }
  const flooded = floodBackground(open, size, size);
  const bits = new Uint8Array(size * size);
  let interior = 0;
  for (let i = 0; i < bits.length; i++) {
    if (flooded[i]) continue;
    bits[i] = 1;
    if (!line[i]) interior++;
  }
  return { bits, interior, stroke };
}

const MIN_INTERIOR = Math.round(CUTOUT_SIZE * CUTOUT_SIZE * 0.004);

/** Bake an edited outline back into the preview / mask / polygon triple. */
export async function outlineToCutout(
  sourceUrl: string,
  outline: CanvasImageSource,
): Promise<{ previewUrl: string; maskUrl: string; outline: number[][] }> {
  const { bits, interior, stroke } = fillOutline(outline);
  if (!stroke) throw new Error("Draw the outline before saving.");
  if (interior < MIN_INTERIOR) {
    throw new Error("The outline is open — close the loop so it encircles the garment.");
  }
  const size = CUTOUT_SIZE;
  const maskCanvas = document.createElement("canvas");
  maskCanvas.width = size;
  maskCanvas.height = size;
  const mctx = maskCanvas.getContext("2d");
  if (!mctx) throw new Error("Could not update the outline.");
  const image = mctx.createImageData(size, size);
  for (let i = 0; i < bits.length; i++) {
    const p = i * 4;
    image.data[p] = 255;
    image.data[p + 1] = 255;
    image.data[p + 2] = 255;
    image.data[p + 3] = bits[i] ? 255 : 0;
  }
  mctx.putImageData(image, 0, 0);

  const source = await loadImage(sourceUrl);
  const preview = document.createElement("canvas");
  preview.width = size;
  preview.height = size;
  const pctx = preview.getContext("2d");
  if (!pctx) throw new Error("Could not update the outline.");
  pctx.fillStyle = `rgb(${CLOTH.r}, ${CLOTH.g}, ${CLOTH.b})`;
  pctx.fillRect(0, 0, size, size);
  pctx.drawImage(source, 0, 0, size, size);
  pctx.globalCompositeOperation = "destination-in";
  pctx.drawImage(maskCanvas, 0, 0);
  pctx.globalCompositeOperation = "destination-over";
  pctx.fillRect(0, 0, size, size);

  const box = maskBBox(bits, size, size);
  return {
    previewUrl: canvasPng(preview),
    maskUrl: canvasPng(maskCanvas),
    outline: box ? maskOutline(bits, size, size, box) : [],
  };
}

export async function cutOutGarment(file: File): Promise<GarmentCutout> {
  const src = URL.createObjectURL(file);
  try {
    const img = await loadImage(src);
    const detectW = DETECT_SIZE;
    const detectH = Math.max(
      32,
      Math.round((img.naturalHeight / Math.max(img.naturalWidth, 1)) * DETECT_SIZE),
    );
    const detectCanvas = drawToCanvas(img, detectW, detectH);
    const ctx = detectCanvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) throw new Error("Could not read the image.");
    const image = ctx.getImageData(0, 0, detectW, detectH);
    const mask = detectMask(image);
    const box = maskBBox(mask, detectW, detectH);
    if (!box) {
      throw new Error(
        "No garment in view; try a plainer backdrop with the clothing centred.",
      );
    }
    const baked = paintSquare(img, detectCanvas, mask, box);
    return baked;
  } finally {
    URL.revokeObjectURL(src);
  }
}
