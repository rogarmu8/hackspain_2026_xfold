/** Detect a garment on a plain backdrop and crop it to a square print + outline. */

export const CUTOUT_SIZE = 512;
const DETECT_SIZE = 256;
const CLOTH = { r: 246, g: 246, b: 248 };

export type GarmentCutout = {
  previewUrl: string;
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

function maskOutline(mask: Uint8Array, w: number, h: number, box: { x: number; y: number; w: number; h: number }): number[][] {
  const pts: number[][] = [];
  const step = Math.max(1, Math.floor(box.h / 40));
  for (let y = box.y; y < box.y + box.h; y += step) {
    let left = -1;
    let right = -1;
    for (let x = box.x; x < box.x + box.w; x++) {
      if (!mask[y * w + x]) continue;
      if (left < 0) left = x;
      right = x;
    }
    if (left >= 0) pts.push([left, y]);
    if (right >= 0 && right !== left) {
      /* collect rights later */
    }
  }
  const rights: number[][] = [];
  for (let y = box.y + box.h - 1; y >= box.y; y -= step) {
    let right = -1;
    for (let x = box.x; x < box.x + box.w; x++) {
      if (mask[y * w + x]) right = x;
    }
    if (right >= 0) rights.push([right, y]);
  }
  const all = [...pts, ...rights];
  if (!all.length) return [];
  const size = Math.max(box.w, box.h);
  const ox = box.x - (size - box.w) / 2;
  const oy = box.y - (size - box.h) / 2;
  const uv = all.map(([x, y]) => [
    clamp((x - ox) / Math.max(size - 1, 1), 0, 1),
    clamp((y - oy) / Math.max(size - 1, 1), 0, 1),
  ]);
  if (uv[0][0] !== uv[uv.length - 1][0] || uv[0][1] !== uv[uv.length - 1][1]) {
    uv.push(uv[0]);
  }
  return uv;
}

function paintSquare(
  img: HTMLImageElement,
  detectCanvas: HTMLCanvasElement,
  mask: Uint8Array,
  box: { x: number; y: number; w: number; h: number },
): string {
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
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not cut out the garment.");
  ctx.fillStyle = `rgb(${CLOTH.r}, ${CLOTH.g}, ${CLOTH.b})`;
  const scale = Math.min(size / Math.max(crop.w, 1), size / Math.max(crop.h, 1));
  const nw = Math.max(1, Math.round(crop.w * scale));
  const nh = Math.max(1, Math.round(crop.h * scale));
  const dx = Math.floor((size - nw) / 2);
  const dy = Math.floor((size - nh) / 2);
  const maskCanvas = document.createElement("canvas");
  maskCanvas.width = box.w;
  maskCanvas.height = box.h;
  const mctx = maskCanvas.getContext("2d");
  if (!mctx) throw new Error("Could not cut out the garment.");
  const maskImage = mctx.createImageData(box.w, box.h);
  for (let y = 0; y < box.h; y++) {
    for (let x = 0; x < box.w; x++) {
      const on = mask[(box.y + y) * dw + (box.x + x)];
      const i = (y * box.w + x) * 4;
      maskImage.data[i] = 255;
      maskImage.data[i + 1] = 255;
      maskImage.data[i + 2] = 255;
      maskImage.data[i + 3] = on ? 255 : 0;
    }
  }
  mctx.putImageData(maskImage, 0, 0);
  ctx.clearRect(0, 0, size, size);
  ctx.drawImage(img, crop.x, crop.y, crop.w, crop.h, dx, dy, nw, nh);
  ctx.globalCompositeOperation = "destination-in";
  ctx.drawImage(maskCanvas, 0, 0, box.w, box.h, dx, dy, nw, nh);
  ctx.globalCompositeOperation = "destination-over";
  ctx.fillRect(0, 0, size, size);
  ctx.globalCompositeOperation = "source-over";
  return canvas.toDataURL("image/png");
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
    const previewUrl = paintSquare(img, detectCanvas, mask, box);
    return { previewUrl, outline: maskOutline(mask, detectW, detectH, box) };
  } finally {
    URL.revokeObjectURL(src);
  }
}
