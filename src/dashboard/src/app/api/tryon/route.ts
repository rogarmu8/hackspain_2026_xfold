/**
 * Product shot → fal.ai → a model wearing the garment.
 *
 * Browser → Next (:3000) → fal.ai
 *
 * The call is server-side on purpose: the key stays out of the browser
 * bundle. The QC shot is read from the bridge here rather than posted by the
 * client, so the browser never has to re-upload an image it already has.
 *
 * Env:
 *   FAL_KEY     required — "<id>:<secret>" from fal.ai. Put it in
 *               src/dashboard/.env.local (gitignored), never in the repo.
 *   FAL_MODEL   optional — default fal-ai/nano-banana/edit (image + prompt).
 *   FAL_PROMPT  optional — override the wording below.
 *   FAL_BASE_URL optional — default https://fal.run. Point it at a gateway,
 *               or at a stand-in when testing without spending calls.
 */

import type { NextRequest } from "next/server";
import { bridgeOrigin } from "@/lib/bridge-origin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Image generation is slow; well past the default serverless budget.
export const maxDuration = 120;

const DEFAULT_MODEL = "fal-ai/nano-banana/edit";
const DEFAULT_BASE_URL = "https://fal.run";

const DEFAULT_PROMPT = [
  "Full-body studio photograph of a fashion model wearing this exact garment.",
  "The reference image is a flat-lay product shot taken from directly above:",
  "keep its silhouette, colour, print and any visible stain or tear exactly as shown.",
  "Neutral light-grey seamless background, soft even lighting, e-commerce catalogue style, sharp focus.",
].join(" ");

/** Pull the generated image URL out of whichever shape the model returns. */
function pickImageUrl(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const body = payload as Record<string, unknown>;
  const images = body.images;
  if (Array.isArray(images) && images.length) {
    const first = images[0];
    if (typeof first === "string") return first;
    if (first && typeof first === "object") {
      const url = (first as Record<string, unknown>).url;
      if (typeof url === "string") return url;
    }
  }
  const image = body.image;
  if (image && typeof image === "object") {
    const url = (image as Record<string, unknown>).url;
    if (typeof url === "string") return url;
  }
  if (typeof body.url === "string") return body.url;
  return null;
}

function fail(error: string, detail: string, status: number) {
  return Response.json({ ok: false, error, detail }, { status });
}

export async function POST(req: NextRequest) {
  const key = process.env.FAL_KEY?.trim();
  if (!key) {
    return fail(
      "missing_key",
      "Falta FAL_KEY. Añádela a src/dashboard/.env.local y reinicia el dashboard.",
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
  if (!runId) return fail("bad_request", "Falta runId.", 400);

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
      `El bridge no tiene foto de producto para ${runId} (HTTP ${photo.status}).`,
      404,
    );
  }
  const mime = photo.headers.get("content-type") ?? "image/jpeg";
  const dataUri = `data:${mime};base64,${Buffer.from(
    await photo.arrayBuffer(),
  ).toString("base64")}`;

  // 2. fal.ai. Model is configurable because the catalogue moves faster than
  //    this repo does; anything taking {prompt, image_urls} will slot in.
  const model = process.env.FAL_MODEL?.trim() || DEFAULT_MODEL;
  const prompt = process.env.FAL_PROMPT?.trim() || DEFAULT_PROMPT;
  const base = (process.env.FAL_BASE_URL?.trim() || DEFAULT_BASE_URL).replace(/\/$/, "");

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/${model}`, {
      method: "POST",
      headers: {
        Authorization: `Key ${key}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        prompt,
        image_urls: [dataUri],
        num_images: 1,
      }),
      signal: AbortSignal.timeout(110_000),
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "fal.ai unreachable";
    return fail("fal_unreachable", detail, 502);
  }

  const text = await upstream.text();
  let payload: unknown = null;
  try {
    payload = JSON.parse(text);
  } catch {
    /* non-JSON error body; reported raw below */
  }

  if (!upstream.ok) {
    const reported =
      payload && typeof payload === "object"
        ? (payload as Record<string, unknown>).detail
        : undefined;
    const detail =
      typeof reported === "string" && reported
        ? reported
        : text.slice(0, 300) || `HTTP ${upstream.status}`;
    return fail("fal_error", detail, upstream.status === 401 ? 401 : 502);
  }

  const url = pickImageUrl(payload);
  if (!url) {
    return fail(
      "no_image",
      `${model} respondió sin imagen: ${text.slice(0, 300)}`,
      502,
    );
  }
  return Response.json({ ok: true, url, model });
}
