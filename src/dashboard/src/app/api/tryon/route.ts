/**
 * Product shot → OpenAI image edit → a model wearing the garment.
 *
 * Browser → Next (:3000) → api.openai.com
 *
 * The call is server-side on purpose: the key stays out of the browser
 * bundle. The QC shot is read from the bridge here rather than posted by the
 * client, so the browser never has to re-upload an image it already has.
 *
 * `gpt-image-1` returns base64, not a hosted URL, so this hands the browser a
 * data URI. That keeps the panel a plain <img> with nothing to store.
 *
 * Env:
 *   OPENAI_API_KEY       required. Put it in src/dashboard/.env.local
 *                        (gitignored), never in the repo.
 *   OPENAI_IMAGE_MODEL   optional — default gpt-image-1.
 *   OPENAI_IMAGE_SIZE    optional — default 1024x1024 (the QC shot is square).
 *   OPENAI_IMAGE_QUALITY optional — low | medium | high | auto. Unset lets the
 *                        API decide; high is slow.
 *   OPENAI_BASE_URL      optional — default https://api.openai.com/v1. Point it
 *                        at a gateway, or a stand-in when testing.
 *   TRYON_PROMPT         optional — override the wording below.
 */

import type { NextRequest } from "next/server";
import { bridgeOrigin } from "@/lib/bridge-origin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Image generation is slow; well past the default serverless budget.
export const maxDuration = 120;

const DEFAULT_MODEL = "gpt-image-1";
const DEFAULT_BASE_URL = "https://api.openai.com/v1";
const DEFAULT_SIZE = "1024x1024";

const DEFAULT_PROMPT = [
  "Full-body studio photograph of a fashion model wearing this exact garment.",
  "The reference image is a flat-lay product shot taken from directly above:",
  "keep its silhouette, colour, print and any visible stain or tear exactly as shown.",
  "Neutral light-grey seamless background, soft even lighting, e-commerce catalogue style, sharp focus.",
].join(" ");

type Shot = { bytes: ArrayBuffer; mime: string };

function fail(error: string, detail: string, status: number) {
  return Response.json({ ok: false, error, detail }, { status });
}

/** `data[0]` is base64 on gpt-image-1, a URL on the older dall-e models. */
function pickImage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const data = (payload as Record<string, unknown>).data;
  if (!Array.isArray(data) || !data.length) return null;
  const first = data[0];
  if (!first || typeof first !== "object") return null;
  const row = first as Record<string, unknown>;
  if (typeof row.b64_json === "string" && row.b64_json) {
    return `data:image/png;base64,${row.b64_json}`;
  }
  if (typeof row.url === "string" && row.url) return row.url;
  return null;
}

/** OpenAI errors are {error:{message}}; fall back to whatever came back. */
function errorDetail(payload: unknown, text: string, status: number): string {
  if (payload && typeof payload === "object") {
    const err = (payload as Record<string, unknown>).error;
    if (err && typeof err === "object") {
      const message = (err as Record<string, unknown>).message;
      if (typeof message === "string" && message) return message;
    }
  }
  return text.slice(0, 300) || `HTTP ${status}`;
}

function buildForm(
  shot: Shot,
  model: string,
  prompt: string,
  size: string,
  quality: string | undefined,
  fidelity: boolean,
): FormData {
  const form = new FormData();
  form.append("model", model);
  form.append("prompt", prompt);
  form.append("n", "1");
  form.append("size", size);
  if (quality) form.append("quality", quality);
  // Keeps the print and the defect recognisable rather than re-imagined.
  if (fidelity) form.append("input_fidelity", "high");
  const ext = shot.mime.includes("png") ? "png" : "jpg";
  form.append("image", new Blob([shot.bytes], { type: shot.mime }), `product.${ext}`);
  return form;
}

export async function POST(req: NextRequest) {
  const key = process.env.OPENAI_API_KEY?.trim();
  if (!key) {
    return fail(
      "missing_key",
      "OPENAI_API_KEY is missing. Add it to src/dashboard/.env.local and restart the dashboard.",
      501,
    );
  }

  let runId = "";
  try {
    const body = (await req.json()) as { runId?: unknown };
    if (typeof body.runId === "string") runId = body.runId.trim();
  } catch {
    /* handled by the guard below */
  }
  if (!runId) return fail("bad_request", "Missing runId.", 400);

  // 1. The QC shot, straight from the bridge.
  let photo: Response;
  try {
    photo = await fetch(
      `${bridgeOrigin()}/runs/${encodeURIComponent(runId)}/photo`,
      { cache: "no-store", signal: AbortSignal.timeout(10_000) },
    );
  } catch (err) {
    const detail = err instanceof Error ? err.message : "bridge unreachable";
    return fail("bridge_unreachable", detail, 502);
  }
  if (!photo.ok) {
    return fail(
      "no_photo",
      `The bridge has no product photo for ${runId} (HTTP ${photo.status}).`,
      404,
    );
  }
  const shot: Shot = {
    bytes: await photo.arrayBuffer(),
    mime: photo.headers.get("content-type") ?? "image/jpeg",
  };

  // 2. OpenAI images/edits — the garment photo is the input, not a reference.
  const model = process.env.OPENAI_IMAGE_MODEL?.trim() || DEFAULT_MODEL;
  const prompt = process.env.TRYON_PROMPT?.trim() || DEFAULT_PROMPT;
  const size = process.env.OPENAI_IMAGE_SIZE?.trim() || DEFAULT_SIZE;
  const quality = process.env.OPENAI_IMAGE_QUALITY?.trim() || undefined;
  const base = (process.env.OPENAI_BASE_URL?.trim() || DEFAULT_BASE_URL).replace(
    /\/$/,
    "",
  );

  async function call(fidelity: boolean) {
    const res = await fetch(`${base}/images/edits`, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}` },
      body: buildForm(shot, model, prompt, size, quality, fidelity),
      signal: AbortSignal.timeout(110_000),
    });
    const text = await res.text();
    let payload: unknown = null;
    try {
      payload = JSON.parse(text);
    } catch {
      /* non-JSON error body; reported raw */
    }
    return { res, text, payload };
  }

  let attempt: Awaited<ReturnType<typeof call>>;
  try {
    attempt = await call(true);
    // input_fidelity is gpt-image-1 only and fairly new. If this deployment
    // has not got it, lose the flag rather than the whole feature.
    if (attempt.res.status === 400) {
      const detail = errorDetail(attempt.payload, attempt.text, 400);
      if (/input_fidelity/i.test(detail)) attempt = await call(false);
    }
  } catch (err) {
    const detail = err instanceof Error ? err.message : "OpenAI unreachable";
    return fail("openai_unreachable", detail, 502);
  }

  const { res, text, payload } = attempt;
  if (!res.ok) {
    return fail(
      "openai_error",
      errorDetail(payload, text, res.status),
      res.status === 401 || res.status === 403 ? res.status : 502,
    );
  }

  const url = pickImage(payload);
  if (!url) {
    return fail("no_image", `${model} returned no image: ${text.slice(0, 300)}`, 502);
  }
  return Response.json({ ok: true, url, model });
}
