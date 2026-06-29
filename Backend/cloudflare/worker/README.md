# Voice Assessment Cloudflare Worker

This Worker is the first Cloudflare-backed backend phase for the voice assessment platform. It runs at the edge and forwards API traffic to the existing FastAPI service while providing:

- Public API gateway for frontend and Vapi traffic.
- CORS handling for local demo ports.
- Security headers.
- Request ID propagation.
- Structured edge request logs.
- Vapi webhook validation before forwarding to FastAPI.
- Edge health check at `/edge/health`.

## Local Setup

1. Start the FastAPI backend on port `8001`.

```powershell
cd "D:\Shubham\voice project\Backend"
C:\tmp\voice_backend_venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

2. Create local Worker secrets.

```powershell
cd "D:\Shubham\voice project\Backend\cloudflare\worker"
Copy-Item .dev.vars.example .dev.vars
```

Edit `.dev.vars` and set `VAPI_WEBHOOK_SECRET` to the same value as the FastAPI backend `.env`.

3. Start the Worker.

```powershell
npm run dev
```

4. Point the frontend to the Worker URL printed by Wrangler.

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8787"
npm run dev -- --host 127.0.0.1 --port 3001
```

5. For Vapi local testing, expose the Worker instead of FastAPI.

```powershell
ngrok http 8787
```

Set Vapi Server URL to:

```text
https://YOUR-NGROK-URL.ngrok-free.app/api/v1/webhooks/vapi
```

## Production Notes

This Worker is the Cloudflare backend entrypoint for the platform. It owns public API ingress, security headers, CORS, request IDs, and Vapi webhook pre-validation, then routes application requests to the origin service.

The remaining Cloudflare-native expansion path is:

1. Keep Worker as the public API surface.
2. Move webhook ingestion into Worker-native storage/queues.
3. Move auth/session endpoints or keep FastAPI behind the Worker.
4. Use Cloudflare Queues for report generation jobs.
5. Use Hyperdrive or Supabase HTTP APIs for PostgreSQL access from Workers.
6. Deploy frontend to Cloudflare Pages or migrate to Next.js on Cloudflare.
