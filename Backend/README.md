# Voice Assessment API

FastAPI backend for voice-based assessment workflows. The service manages users, assessments, assessment sessions, Vapi webhooks, AI report generation through Anthropic or Azure OpenAI, Resend transactional email, analytics, and admin operations.

## Requirements

- Python 3.12
- PostgreSQL with the `pgcrypto` extension enabled for `gen_random_uuid()`
- Vapi account and webhook secret
- Anthropic API key or Azure OpenAI resource credentials
- Resend API key and verified sending domain

## Setup

Create and activate a virtual environment, then install the project dependencies:

```powershell
cd voice_assessment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

For local development and tests:

```powershell
pip install -e ".[dev]"
pytest -q
```

Run live API E2E tests against a migrated backend:

```powershell
$env:VOICE_E2E_BASE_URL="http://127.0.0.1:8000"
$env:VOICE_E2E_DATABASE_URL="postgresql+asyncpg://voice_assessment:local_voice_password@127.0.0.1:55432/voice_assessment"
$env:VAPI_WEBHOOK_SECRET="local-dev-vapi-webhook-secret"
pytest -q tests\test_api_e2e.py
```

Use the Supabase asyncpg URL for `VOICE_E2E_DATABASE_URL` when testing a deployed environment.

Create your environment file:

```powershell
Copy-Item .env.example .env
```

Fill every value in `.env`. Secrets must be real values in deployed environments.

## Environment Configuration

Required settings:

- `DATABASE_URL`: async SQLAlchemy PostgreSQL URL using `postgresql+asyncpg://`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `AI_REPORT_PROVIDER`: `anthropic` or `azure_openai`
- Anthropic provider: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ANTHROPIC_SMOKE_MODEL`
- Azure OpenAI provider: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`, `AZURE_CHAT_DEPLOYMENT`
- `VAPI_API_KEY`
- `VAPI_WEBHOOK_SECRET`
- `VAPI_API_URL`
- `VAPI_CALL_MODE`: `web` for browser calls, `phone` for outbound PSTN calls
- `VAPI_PHONE_NUMBER_ID`: required only when `VAPI_CALL_MODE=phone`
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL`
- `ADMIN_EMAIL`
- `JWT_SECRET`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REQUIRE_EMAIL_VERIFICATION`
- `REDIS_URL`: optional locally; required for server-side JWT revocation in deployed environments
- `ENVIRONMENT`
- `LOG_LEVEL`
- `CORS_ORIGINS`

`JWT_SECRET` must be at least 32 characters. `REQUIRE_EMAIL_VERIFICATION=false` is intended for local/demo use until the verification-email flow is enabled. `ENVIRONMENT=production` enables the HSTS security header.

For Supabase, use `postgresql+asyncpg://...` for the API and migrations. If you choose the Supabase transaction pooler on port `6543`, add `prepared_statement_cache_size=0` to avoid asyncpg prepared-statement errors.

## Database Migrations

Alembic reads `DATABASE_URL` from the environment.

```powershell
cd voice_assessment
alembic upgrade head
python scripts\verify_database_schema.py
```

This project does not use `Base.metadata.create_all()`.

## Run The Server

```powershell
cd voice_assessment
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

## Run The Report Worker

The webhook creates durable pending report records. Run a worker process so report generation is not dependent on request-scoped background state:

```powershell
voice-report-worker --batch-size 5 --poll-seconds 10 --stale-after-seconds 900
```

## API Groups

- `/api/v1/auth`: registration, login, current user, logout
- `/api/v1/assessments`: assessment CRUD and archive operations
- `/api/v1/sessions`: assessment session CRUD and Vapi call initiation
- `/api/v1/sessions/{session_id}/report`: report status or completed report
- `/api/v1/admin`: platform analytics, failed session review, report retry, user management
- `/api/v1/webhooks/vapi`: Vapi event webhook receiver

Admin endpoints require the `admin` role. Assessor and candidate access is restricted by route and service-level checks.

Start an outbound Vapi call:

```http
POST /api/v1/sessions/{session_id}/start-call
Content-Type: application/json

{"customer_number":"+15551234567"}
```

## Vapi Webhook Setup

Configure Vapi to send webhook events to:

```text
https://<your-api-host>/api/v1/webhooks/vapi
```

The webhook sender must include:

```text
X-Vapi-Signature: t=<timestamp>,v1=<hex_digest>
```

The service validates the HMAC using `VAPI_WEBHOOK_SECRET`, rejects signatures outside the five-minute replay window, stores webhook idempotency records, and acknowledges duplicate processed events with `200 OK`.

Supported event types:

- `call.started`
- `call.ended`
- `transcript.update`
- `analysis.done`

Unknown event types are accepted and logged without breaking delivery.

Provision the baseline assessment interviewer assistant:

```powershell
python scripts\provision_vapi_assistant.py --server-url https://api.your-domain.example
```

Store the returned assistant ID in each assessment's `vapi_assistant_id`.

## Alpha Demo Workflow

Use these commands after the database is migrated and `.env` has real database and Vapi values. This does not deploy anything; it prepares a repeatable local/live alpha test path.

For a company presentation, first start the local database if you are not using Supabase:

```powershell
$env:VOICE_ASSESSMENT_POSTGRES_PASSWORD="local_voice_password"
docker-compose up -d postgres migrate
```

Run the deterministic presentation path. This simulates Vapi webhook events but uses the real database, webhook/session/report services, Azure OpenAI report generation, and a real Resend email attempt if `RESEND_API_KEY` is configured:

```powershell
python scripts\run_presentation_demo.py --reset-passwords
```

For the fully live Vapi browser-call path, configure real `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`, Azure OpenAI credentials, Resend credentials, and `VAPI_CALL_MODE=web`, then expose the local backend through ngrok. `VAPI_PHONE_NUMBER_ID` is only required when `VAPI_CALL_MODE=phone`. Keep the backend running on port `8000` first:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Prepare the live demo assistant and session through ngrok:

```powershell
python scripts\prepare_live_vapi_demo.py --backend-url http://127.0.0.1:8000 --reset-passwords
```

The command verifies `/ready`, finds or starts an ngrok HTTPS tunnel for the backend, rejects placeholder Vapi credentials, provisions a Vapi assistant with `https://<ngrok-host>/api/v1/webhooks/vapi`, and seeds demo users plus a live assessment session. It prints the public webhook URL, assistant ID, session ID, candidate login, candidate URL, and verification command.

If you already started ngrok yourself, keep it pointed at the backend and run:

```powershell
ngrok http http://127.0.0.1:8000
python scripts\prepare_live_vapi_demo.py --no-start-ngrok --backend-url http://127.0.0.1:8000 --reset-passwords
```

After the assistant is provisioned, start the live browser-call path:

```powershell
cd "D:\Shubham\voice project\Frontend"
npm run dev -- --host 127.0.0.1 --port 3000
```

Then open the printed `/demo/<session-id>` candidate URL, sign in with the printed candidate credentials, check microphone access, and click **Start browser call**. Speak through the assessment and end the call.

Seed demo users, an active assessment, and a scheduled session:

```powershell
python scripts\seed_demo_data.py --vapi-assistant-id <vapi-assistant-uuid> --reset-passwords
```

The seed command prints the created or reused `session_id`. Start a real Vapi web call for that session:

```powershell
python scripts\start_demo_vapi_call.py --session-id <session-id>
```

Check the session, Vapi call ID, report status, score, and email delivery timestamp:

```powershell
python scripts\check_demo_session.py --session-id <session-id>
```

Poll until the full live chain is verified:

```powershell
python scripts\verify_live_e2e.py --session-id <session-id> --timeout-seconds 900 --poll-seconds 10
```

This exits successfully only after the real session has a Vapi call ID, completed status, transcript, completed AI report, generated timestamp, and email delivery timestamp. For early rehearsals before Resend sender verification, use `--allow-missing-email`; do not use that flag for the final company demo.

For outbound phone calls through a Vapi-provisioned number or Twilio-connected number, set `VAPI_CALL_MODE=phone` and `VAPI_PHONE_NUMBER_ID`, then use the Candidates page `Call phone` action. Full setup steps are in `docs/vapi-twilio-phone-calling.md`.

Default alpha login credentials created by the seed command:

- Admin: `[email-redacted]` / `DemoAdmin123!`
- Assessor: `[email-redacted]` / `DemoAssessor123!`
- Candidate: `[email-redacted]` / `DemoCandidate123!`

Change these with the seed script flags before sharing a demo outside your local test environment.

## Production Hardening

The API includes:

- Request IDs on every request
- Structured request logging
- Security headers middleware
- SlowAPI rate limiting
- CORS from configured origins
- Global unhandled exception response with request ID

Default rate limits:

- API routes: `100/minute`
- Auth login/register: `10/minute`
- Vapi webhook: `5/minute`

## Live Smoke Checks

After real `.env` values are present:

```powershell
python scripts\validate_live_readiness.py --public-api-url https://api.your-domain.example
python scripts\smoke_integrations.py
python scripts\smoke_integrations.py --send-email
```

The readiness command rejects placeholder secrets and non-public webhook URLs. The smoke command checks PostgreSQL, Vapi phone-number access, and the configured AI provider. The `--send-email` form also sends a real Resend admin alert email through the same retry-aware email service used by report delivery.

Send the Resend "Hello World" email after setting `RESEND_API_KEY` and `RESEND_FROM_EMAIL` in `.env`:

```powershell
python scripts\send_resend_test_email.py --to [email-redacted]
```

For Resend's sandbox sender, set `RESEND_FROM_EMAIL=[email-redacted]`. For production delivery, use a sender address from a verified Resend domain.

Verify Redis-backed logout revocation after `REDIS_URL` is configured:

```powershell
python scripts\verify_redis_revocation.py --base-url http://127.0.0.1:8000
```

Operational probe:

```powershell
python scripts\ops_probe.py
python scripts\ops_probe.py --send-alert-on-failure
```

Verify Resend production email readiness:

```powershell
python scripts\verify_resend_readiness.py
```

Verify Vapi assistant readiness:

```powershell
python scripts\verify_vapi_assistant_readiness.py --assistant-id "<vapi-assistant-id>" --server-url "https://api.your-domain.com"
```

## Cloudflare Worker Backend Entrypoint

The Worker in `cloudflare/worker` is the public backend entrypoint. It handles security headers, request IDs, CORS, upstream failure handling, and Vapi webhook validation before routing stateful application requests to the origin service.

```powershell
cd cloudflare\worker
npm install
npm run typecheck
cd ..\..
.\scripts\deploy_cloudflare_worker.ps1 `
  -Environment staging `
  -ApiOrigin "https://api-staging.your-domain.com" `
  -AllowedOrigins "https://app-staging.your-domain.com"
```

## Docker

```powershell
$env:VOICE_ASSESSMENT_POSTGRES_PASSWORD="set-a-local-password"
docker-compose up --build
```

Compose overrides `DATABASE_URL` inside containers so services use the `postgres` hostname. It runs migrations before the API starts, then starts the report worker after `/ready` is healthy.

More detail is in `docs/architecture.md`, `docs/production-alignment.md`, `docs/operations.md`, `docs/deployment.md`, `docs/cloudflare-worker-deployment.md`, `docs/resend-production-email.md`, `docs/live-e2e-runbook.md`, `docs/vapi-assistant-playbook.md`, `docs/vapi-twilio-phone-calling.md`, and `docs/backend-readiness-audit.md`.
