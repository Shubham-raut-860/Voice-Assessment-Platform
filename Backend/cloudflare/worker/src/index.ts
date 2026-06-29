export interface Env {
  API_ORIGIN: string;
  ALLOWED_ORIGINS: string;
  ENVIRONMENT: "development" | "staging" | "production";
  VAPI_WEBHOOK_SECRET?: string;
}

const SIGNATURE_TOLERANCE_SECONDS = 300;
const EDGE_HEALTH_PATH = "/edge/health";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const requestId = crypto.randomUUID();
    const startedAt = Date.now();
    const origin = request.headers.get("Origin");
    const corsHeaders = buildCorsHeaders(origin, env);
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      const response = withEdgeHeaders(new Response(null, { status: 204, headers: corsHeaders }), env, requestId);
      logRequest(request, url, response.status, requestId, startedAt, "preflight");
      return response;
    }

    if (url.pathname === EDGE_HEALTH_PATH) {
      const response = withEdgeHeaders(
        Response.json(
          {
            status: "ok",
            service: "voice-assessment-edge-worker",
            environment: env.ENVIRONMENT,
            upstream: env.API_ORIGIN,
          },
          { headers: corsHeaders },
        ),
        env,
        requestId,
      );
      logRequest(request, url, response.status, requestId, startedAt, "edge_health");
      return response;
    }

    if (url.pathname === "/api/v1/webhooks/vapi") {
      const signatureResult = await validateVapiSignatureAtEdge(request, env);
      if (!signatureResult.ok) {
        const response = Response.json({ detail: signatureResult.error }, { status: 401, headers: corsHeaders });
        const securedResponse = withEdgeHeaders(response, env, requestId);
        logRequest(request, url, securedResponse.status, requestId, startedAt, "webhook_auth_failed");
        return securedResponse;
      }
    }

    const upstreamUrl = new URL(request.url);
    const apiOrigin = new URL(env.API_ORIGIN);
    upstreamUrl.protocol = apiOrigin.protocol;
    upstreamUrl.host = apiOrigin.host;

    const upstreamHeaders = new Headers(request.headers);
    upstreamHeaders.set("X-Request-ID", requestId);
    upstreamHeaders.set("X-Forwarded-Host", url.host);
    upstreamHeaders.set("X-Forwarded-Proto", url.protocol.replace(":", ""));

    const upstreamRequest = new Request(upstreamUrl, {
      method: request.method,
      headers: upstreamHeaders,
      body: request.body,
      redirect: "manual",
    });

    let upstreamResponse: Response;
    try {
      upstreamResponse = await fetch(upstreamRequest);
    } catch (error) {
      console.error(
        JSON.stringify({
          event: "upstream_fetch_failed",
          request_id: requestId,
          method: request.method,
          path: url.pathname,
          upstream: upstreamUrl.toString(),
          error: error instanceof Error ? error.message : String(error),
        }),
      );
      const response = withEdgeHeaders(
        Response.json({ detail: "upstream_unavailable", request_id: requestId }, { status: 502, headers: corsHeaders }),
        env,
        requestId,
      );
      logRequest(request, url, response.status, requestId, startedAt, "upstream_failed");
      return response;
    }

    const responseHeaders = new Headers(upstreamResponse.headers);
    for (const [key, value] of corsHeaders.entries()) {
      responseHeaders.set(key, value);
    }

    const response = withEdgeHeaders(
      new Response(upstreamResponse.body, {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: responseHeaders,
      }),
      env,
      requestId,
    );
    logRequest(request, url, response.status, requestId, startedAt, "proxied");
    return response;
  },
};

function buildCorsHeaders(origin: string | null, env: Env): Headers {
  const headers = new Headers();
  const allowedOrigins = parseAllowedOrigins(env.ALLOWED_ORIGINS);
  const allowOrigin = origin !== null && allowedOrigins.includes(origin) ? origin : allowedOrigins[0] ?? "";

  if (allowOrigin !== "") {
    headers.set("Access-Control-Allow-Origin", allowOrigin);
    headers.set("Vary", "Origin");
  }
  headers.set("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS");
  headers.set(
    "Access-Control-Allow-Headers",
    "Authorization,Content-Type,X-Vapi-Signature,X-Vapi-Secret,X-Request-ID",
  );
  headers.set("Access-Control-Allow-Credentials", "true");
  headers.set("Access-Control-Max-Age", "600");
  return headers;
}

function parseAllowedOrigins(value: string): string[] {
  const trimmed = value.trim();
  if (trimmed.startsWith("[")) {
    const decoded: unknown = JSON.parse(trimmed);
    if (Array.isArray(decoded) && decoded.every((item) => typeof item === "string")) {
      return decoded;
    }
    throw new Error("ALLOWED_ORIGINS JSON must be a string array");
  }
  return trimmed
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function withEdgeHeaders(response: Response, env: Env, requestId: string): Response {
  response.headers.set("X-Request-ID", requestId);
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("X-XSS-Protection", "1; mode=block");
  response.headers.set("Content-Security-Policy", "default-src 'self'");
  if (env.ENVIRONMENT === "production") {
    response.headers.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  }
  return response;
}

async function validateVapiSignatureAtEdge(
  request: Request,
  env: Env,
): Promise<{ ok: true } | { ok: false; error: string }> {
  if (env.VAPI_WEBHOOK_SECRET === undefined || env.VAPI_WEBHOOK_SECRET.trim() === "") {
    return { ok: false, error: "webhook_secret_not_configured" };
  }

  const signatureHeader = request.headers.get("X-Vapi-Signature");
  const sharedSecretHeader = request.headers.get("X-Vapi-Secret");
  if (signatureHeader === null || signatureHeader.trim() === "") {
    if (sharedSecretHeader === null || sharedSecretHeader.trim() === "") {
      return { ok: false, error: "invalid_signature" };
    }
    return constantTimeEqual(sharedSecretHeader, env.VAPI_WEBHOOK_SECRET)
      ? { ok: true }
      : { ok: false, error: "invalid_signature" };
  }

  const parts = parseSignatureHeader(signatureHeader);
  const timestamp = parts.get("t");
  const receivedDigest = parts.get("v1");
  if (timestamp === undefined || receivedDigest === undefined) {
    return { ok: false, error: "invalid_signature" };
  }

  const timestampSeconds = Number.parseInt(timestamp, 10);
  if (!Number.isFinite(timestampSeconds)) {
    return { ok: false, error: "invalid_signature" };
  }

  const nowSeconds = Math.floor(Date.now() / 1000);
  if (Math.abs(nowSeconds - timestampSeconds) > SIGNATURE_TOLERANCE_SECONDS) {
    return { ok: false, error: "invalid_signature" };
  }

  const bodyBytes = new Uint8Array(await request.clone().arrayBuffer());
  const prefixBytes = new TextEncoder().encode(`${timestamp}.`);
  const signedPayload = new Uint8Array(prefixBytes.length + bodyBytes.length);
  signedPayload.set(prefixBytes, 0);
  signedPayload.set(bodyBytes, prefixBytes.length);

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.VAPI_WEBHOOK_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = await crypto.subtle.sign("HMAC", key, signedPayload);
  const expectedDigest = bytesToHex(new Uint8Array(digest));

  return constantTimeEqual(expectedDigest, receivedDigest)
    ? { ok: true }
    : { ok: false, error: "invalid_signature" };
}

function parseSignatureHeader(signatureHeader: string): Map<string, string> {
  const parsed = new Map<string, string>();
  for (const part of signatureHeader.split(",")) {
    const [key, value] = part.trim().split("=", 2);
    if (key !== undefined && key.length > 0 && value !== undefined && value.length > 0) {
      parsed.set(key, value);
    }
  }
  return parsed;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function constantTimeEqual(left: string, right: string): boolean {
  const leftBytes = new TextEncoder().encode(left);
  const rightBytes = new TextEncoder().encode(right);
  let diff = leftBytes.length ^ rightBytes.length;
  const maxLength = Math.max(leftBytes.length, rightBytes.length);

  for (let index = 0; index < maxLength; index += 1) {
    const leftByte = leftBytes[index] ?? 0;
    const rightByte = rightBytes[index] ?? 0;
    diff |= leftByte ^ rightByte;
  }

  return diff === 0;
}

function logRequest(
  request: Request,
  url: URL,
  status: number,
  requestId: string,
  startedAt: number,
  outcome: string,
): void {
  const level = status >= 500 ? "error" : status >= 400 ? "warn" : "info";
  const payload = {
    event: "edge_request_completed",
    level,
    request_id: requestId,
    method: request.method,
    path: url.pathname,
    status,
    duration_ms: Date.now() - startedAt,
    outcome,
  };
  const serialized = JSON.stringify(payload);
  if (level === "error") {
    console.error(serialized);
  } else if (level === "warn") {
    console.warn(serialized);
  } else {
    console.log(serialized);
  }
}
