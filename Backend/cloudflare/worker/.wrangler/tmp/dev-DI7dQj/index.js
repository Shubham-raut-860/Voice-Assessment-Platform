var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/index.ts
var SIGNATURE_TOLERANCE_SECONDS = 300;
var EDGE_HEALTH_PATH = "/edge/health";
var src_default = {
  async fetch(request, env) {
    const requestId = crypto.randomUUID();
    const startedAt = Date.now();
    const origin = request.headers.get("Origin");
    const corsHeaders = buildCorsHeaders(origin, env);
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      const response2 = withEdgeHeaders(new Response(null, { status: 204, headers: corsHeaders }), env, requestId);
      logRequest(request, url, response2.status, requestId, startedAt, "preflight");
      return response2;
    }
    if (url.pathname === EDGE_HEALTH_PATH) {
      const response2 = withEdgeHeaders(
        Response.json(
          {
            status: "ok",
            service: "voice-assessment-edge-worker",
            environment: env.ENVIRONMENT,
            upstream: env.API_ORIGIN
          },
          { headers: corsHeaders }
        ),
        env,
        requestId
      );
      logRequest(request, url, response2.status, requestId, startedAt, "edge_health");
      return response2;
    }
    if (url.pathname === "/api/v1/webhooks/vapi") {
      const signatureResult = await validateVapiSignatureAtEdge(request, env);
      if (!signatureResult.ok) {
        const response2 = Response.json({ detail: signatureResult.error }, { status: 401, headers: corsHeaders });
        const securedResponse = withEdgeHeaders(response2, env, requestId);
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
      redirect: "manual"
    });
    let upstreamResponse;
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
          error: error instanceof Error ? error.message : String(error)
        })
      );
      const response2 = withEdgeHeaders(
        Response.json({ detail: "upstream_unavailable", request_id: requestId }, { status: 502, headers: corsHeaders }),
        env,
        requestId
      );
      logRequest(request, url, response2.status, requestId, startedAt, "upstream_failed");
      return response2;
    }
    const responseHeaders = new Headers(upstreamResponse.headers);
    for (const [key, value] of corsHeaders.entries()) {
      responseHeaders.set(key, value);
    }
    const response = withEdgeHeaders(
      new Response(upstreamResponse.body, {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: responseHeaders
      }),
      env,
      requestId
    );
    logRequest(request, url, response.status, requestId, startedAt, "proxied");
    return response;
  }
};
function buildCorsHeaders(origin, env) {
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
    "Authorization,Content-Type,X-Vapi-Signature,X-Vapi-Secret,X-Request-ID"
  );
  headers.set("Access-Control-Allow-Credentials", "true");
  headers.set("Access-Control-Max-Age", "600");
  return headers;
}
__name(buildCorsHeaders, "buildCorsHeaders");
function parseAllowedOrigins(value) {
  const trimmed = value.trim();
  if (trimmed.startsWith("[")) {
    const decoded = JSON.parse(trimmed);
    if (Array.isArray(decoded) && decoded.every((item) => typeof item === "string")) {
      return decoded;
    }
    throw new Error("ALLOWED_ORIGINS JSON must be a string array");
  }
  return trimmed.split(",").map((item) => item.trim()).filter((item) => item.length > 0);
}
__name(parseAllowedOrigins, "parseAllowedOrigins");
function withEdgeHeaders(response, env, requestId) {
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
__name(withEdgeHeaders, "withEdgeHeaders");
async function validateVapiSignatureAtEdge(request, env) {
  if (env.VAPI_WEBHOOK_SECRET === void 0 || env.VAPI_WEBHOOK_SECRET.trim() === "") {
    return { ok: false, error: "webhook_secret_not_configured" };
  }
  const signatureHeader = request.headers.get("X-Vapi-Signature");
  const sharedSecretHeader = request.headers.get("X-Vapi-Secret");
  if (signatureHeader === null || signatureHeader.trim() === "") {
    if (sharedSecretHeader === null || sharedSecretHeader.trim() === "") {
      return { ok: false, error: "invalid_signature" };
    }
    return constantTimeEqual(sharedSecretHeader, env.VAPI_WEBHOOK_SECRET) ? { ok: true } : { ok: false, error: "invalid_signature" };
  }
  const parts = parseSignatureHeader(signatureHeader);
  const timestamp = parts.get("t");
  const receivedDigest = parts.get("v1");
  if (timestamp === void 0 || receivedDigest === void 0) {
    return { ok: false, error: "invalid_signature" };
  }
  const timestampSeconds = Number.parseInt(timestamp, 10);
  if (!Number.isFinite(timestampSeconds)) {
    return { ok: false, error: "invalid_signature" };
  }
  const nowSeconds = Math.floor(Date.now() / 1e3);
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
    ["sign"]
  );
  const digest = await crypto.subtle.sign("HMAC", key, signedPayload);
  const expectedDigest = bytesToHex(new Uint8Array(digest));
  return constantTimeEqual(expectedDigest, receivedDigest) ? { ok: true } : { ok: false, error: "invalid_signature" };
}
__name(validateVapiSignatureAtEdge, "validateVapiSignatureAtEdge");
function parseSignatureHeader(signatureHeader) {
  const parsed = /* @__PURE__ */ new Map();
  for (const part of signatureHeader.split(",")) {
    const [key, value] = part.trim().split("=", 2);
    if (key !== void 0 && key.length > 0 && value !== void 0 && value.length > 0) {
      parsed.set(key, value);
    }
  }
  return parsed;
}
__name(parseSignatureHeader, "parseSignatureHeader");
function bytesToHex(bytes) {
  return Array.from(bytes).map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
__name(bytesToHex, "bytesToHex");
function constantTimeEqual(left, right) {
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
__name(constantTimeEqual, "constantTimeEqual");
function logRequest(request, url, status, requestId, startedAt, outcome) {
  const level = status >= 500 ? "error" : status >= 400 ? "warn" : "info";
  const payload = {
    event: "edge_request_completed",
    level,
    request_id: requestId,
    method: request.method,
    path: url.pathname,
    status,
    duration_ms: Date.now() - startedAt,
    outcome
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
__name(logRequest, "logRequest");

// node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    return Response.json(error, {
      status: 500,
      headers: { "MF-Experimental-Error-Stack": "true" }
    });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-ZjHTYv/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = src_default;

// node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-ZjHTYv/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class ___Facade_ScheduledController__ {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  static {
    __name(this, "__Facade_ScheduledController__");
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof ___Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = /* @__PURE__ */ __name((request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    }, "#fetchDispatcher");
    #dispatcher = /* @__PURE__ */ __name((type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    }, "#dispatcher");
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=index.js.map
