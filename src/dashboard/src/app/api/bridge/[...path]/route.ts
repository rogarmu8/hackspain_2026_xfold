/**
 * Same-origin proxy to the XFOLD Python bridge.
 *
 * Browser → Next (:3000) → Bridge (:8765)
 * Avoids cross-origin CORS pitfalls for long-poll JPEG frames and keeps a
 * single origin for Control (journal SSE still hits the bridge directly
 * via EventSource, which already works cross-origin).
 *
 * Env: NEXT_PUBLIC_XFOLD_BRIDGE_URL or http://127.0.0.1:8765
 */

import type { NextRequest } from "next/server";
import { bridgeOrigin } from "@/lib/bridge-origin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  // fetch() already decodes; forwarding these yields an empty body on Vercel.
  "content-encoding",
]);

function outboundHeaders(upstream: Response): Headers {
  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      out.set(key, value);
    }
  });
  out.set("Cache-Control", "no-store");
  return out;
}

async function proxy(
  req: NextRequest,
  pathParts: string[],
): Promise<Response> {
  const path = pathParts.map(encodeURIComponent).join("/");
  const target = new URL(`${bridgeOrigin()}/${path}`);
  target.search = req.nextUrl.search;
  const stream = path === "events/stream";

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body:
        req.method === "GET" || req.method === "HEAD"
          ? undefined
          : await req.arrayBuffer(),
      cache: "no-store",
      // Long-poll frames can wait up to ~5s; SSE is streamed until this fires.
      signal: AbortSignal.timeout(stream ? 55_000 : 12_000),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "bridge unreachable";
    return Response.json(
      { ok: false, error: "bridge_unreachable", detail: message },
      { status: 502 },
    );
  }

  const out = outboundHeaders(upstream);
  if (stream) {
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: out,
    });
  }

  const body = await upstream.arrayBuffer();
  return new Response(body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: out,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function POST(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function HEAD(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path);
}
