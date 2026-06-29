# Cloudflare Worker Deployment

This project uses Cloudflare Workers as the public backend entrypoint for frontend and Vapi traffic. The Worker handles API ingress, CORS, security headers, request IDs, upstream failure handling, and Vapi webhook validation before routing stateful requests to the origin application service.

## Deployment Model

```text
Frontend / Vapi
  -> Cloudflare Worker
  -> Origin application service
  -> PostgreSQL / Redis / Azure OpenAI / Resend
```

The Worker is configured with named environments:

- `staging`: `voice-assessment-edge-staging`
- `production`: `voice-assessment-edge-production`

Runtime values are passed at deploy time so production URLs and secrets are not committed.

## Required Values

- `API_ORIGIN`: HTTPS origin service URL, for example the deployed API service URL.
- `ALLOWED_ORIGINS`: frontend origins allowed by CORS.
- `VAPI_WEBHOOK_SECRET`: same secret configured in Vapi and the origin backend.
- Optional Cloudflare route or custom domain.

## Dry-Run Deployment

Run this first. It validates TypeScript and asks Wrangler to compile the Worker without uploading it.

```powershell
cd "D:\Shubham\voice project\Backend"
.\scripts\deploy_cloudflare_worker.ps1 `
  -Environment staging `
  -ApiOrigin "https://api-staging.your-domain.com" `
  -AllowedOrigins "https://app-staging.your-domain.com"
```

## Real Staging Deployment

Set the secret only in the shell or provide a local secrets file. Do not commit it.

```powershell
cd "D:\Shubham\voice project\Backend"
$env:VAPI_WEBHOOK_SECRET="same-secret-used-in-vapi"
.\scripts\deploy_cloudflare_worker.ps1 `
  -Environment staging `
  -ApiOrigin "https://api-staging.your-domain.com" `
  -AllowedOrigins "https://app-staging.your-domain.com" `
  -Domains "api-staging.your-domain.com" `
  -Deploy
```

## Real Production Deployment

Production must use HTTPS for both API origin and frontend origin.

```powershell
cd "D:\Shubham\voice project\Backend"
$env:VAPI_WEBHOOK_SECRET="same-secret-used-in-vapi"
.\scripts\deploy_cloudflare_worker.ps1 `
  -Environment production `
  -ApiOrigin "https://api.your-domain.com" `
  -AllowedOrigins "https://app.your-domain.com" `
  -Domains "api.your-domain.com" `
  -Deploy
```

## Post-Deploy Verification

Replace the URL with the deployed Worker domain.

```powershell
Invoke-RestMethod "https://api.your-domain.com/edge/health"
Invoke-RestMethod "https://api.your-domain.com/health"
python scripts\validate_live_readiness.py --public-api-url "https://api.your-domain.com"
python scripts\smoke_integrations.py
```

Then update Vapi:

```text
Server URL = https://api.your-domain.com/api/v1/webhooks/vapi
Header     = X-Vapi-Secret: same-secret-used-in-vapi
```

Run one real E2E rehearsal:

```powershell
python scripts\prepare_live_vapi_demo.py --backend-url "https://api.your-domain.com" --reset-passwords
python scripts\verify_live_e2e.py --session-id <session-id> --timeout-seconds 900
```

## Rollback

1. Re-deploy the previous Worker version from Cloudflare Dashboard or Wrangler release history.
2. Restore the previous origin service release if needed.
3. Confirm:

```powershell
Invoke-RestMethod "https://api.your-domain.com/edge/health"
Invoke-RestMethod "https://api.your-domain.com/ready"
python scripts\ops_probe.py
```

4. Re-run the Vapi webhook smoke test before routing a live demo through the Worker.
