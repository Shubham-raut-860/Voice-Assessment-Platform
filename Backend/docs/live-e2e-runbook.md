# Live E2E Runbook

This runbook validates the production path:

```text
Frontend or operator -> FastAPI/Worker -> Vapi call -> signed Vapi webhook -> PostgreSQL -> Azure OpenAI or Anthropic report -> Resend email
```

## Scope

Run this only after Phase 1 through Phase 5 local checks pass. This is not a mock test. It sends real requests to Vapi, Anthropic, and optionally Resend.

## Required Values

Set these in `.env` or the deployment secret store:

- `DATABASE_URL`: Supabase or production PostgreSQL asyncpg URL.
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- Anthropic settings when `AI_REPORT_PROVIDER=anthropic`, or Azure OpenAI settings when `AI_REPORT_PROVIDER=azure_openai`.
- `VAPI_API_KEY`
- `VAPI_WEBHOOK_SECRET`
- `VAPI_API_URL`
- `VAPI_PHONE_NUMBER_ID` only when `VAPI_CALL_MODE=phone`
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL`
- `ADMIN_EMAIL`
- `JWT_SECRET`
- `CORS_ORIGINS`

The public API URL must be HTTPS and reachable by Vapi. For production, prefer the Cloudflare Worker URL or a deployed API URL, not a local tunnel.

For Supabase transaction pooler connections on port `6543`, append `prepared_statement_cache_size=0` to the SQLAlchemy asyncpg URL. Direct and session-mode Supabase connections do not need this workaround.

## Preflight

From `D:\Shubham\voice project\Backend`:

```powershell
python -B scripts\validate_live_readiness.py --public-api-url https://api.your-domain.example
python -B scripts\smoke_integrations.py
python -B scripts\smoke_integrations.py --send-email
```

Expected:

- `validate_live_readiness.py` ends with `live_readiness: ok`.
- `smoke_integrations.py` reports `database: ok`, `vapi: ok`, and the configured AI provider as `ok`.
- With `--send-email`, `resend: ok` and the admin inbox receives the alert.

## Database

Apply migrations against the target database:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://..."
alembic upgrade head
python scripts\verify_database_schema.py
```

If you are using a `.env` file in the backend directory, Alembic loads it automatically. An explicit process-level `DATABASE_URL` still wins when set.

Verify:

```sql
select version_num from alembic_version;
select count(*) from users;
```

## Runtime

Start the API and the worker:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
voice-report-worker --batch-size 5 --poll-seconds 10 --stale-after-seconds 900
```

Verify:

```powershell
Invoke-RestMethod https://api.your-domain.example/health
Invoke-RestMethod https://api.your-domain.example/ready
```

Expected:

```json
{"status":"ready","environment":"staging","db":"connected"}
```

## Cloudflare Worker

Use the Worker when you want edge security headers, CORS, request IDs, and Vapi HMAC pre-validation before proxying to FastAPI.

Set:

```powershell
cd cloudflare\worker
wrangler secret put VAPI_WEBHOOK_SECRET
wrangler deploy
```

Configure:

- `API_ORIGIN`: public or private origin for the FastAPI API.
- `ALLOWED_ORIGINS`: frontend origins.
- `ENVIRONMENT`: `staging` or `production`.

Then use the Worker URL as the public API URL.

## Vapi Assistant

Provision the tuned assessment interviewer assistant:

```powershell
python scripts\provision_vapi_assistant.py --server-url https://api.your-domain.example --name "Voice Assessment Interviewer"
```

The assistant uses a controlled enterprise interview flow: one question at a time, evidence-seeking follow-ups, no protected-class questions, no scoring disclosure, silence handling, and structured Vapi analysis prompts. Store the returned assistant ID as `vapi_assistant_id` when creating an assessment.

Webhook URL configured on the assistant:

```text
https://api.your-domain.example/api/v1/webhooks/vapi
```

## Live Assessment Flow

1. Register or choose an admin/assessor user.
2. Create a candidate user.
3. Create an active assessment with the real Vapi assistant ID.
4. Create an assessment session for the candidate.
5. Start the call in `VAPI_CALL_MODE=phone`:

```http
POST /api/v1/sessions/{session_id}/start-call
Authorization: Bearer <admin_or_assessor_token>
Content-Type: application/json

{"customer_number":"+15551234567"}
```

6. Confirm the API returns `call_id`.
7. Complete the call on the phone.
8. Confirm Vapi sends webhook events.
9. Confirm database state:

```sql
select status, vapi_call_id, raw_transcript is not null as has_transcript, vapi_analysis is not null as has_analysis
from assessment_sessions
where id = '<session_id>';

select generation_status, generation_error, generated_at, email_sent_at
from assessment_reports
where session_id = '<session_id>';
```

Expected final state:

- `assessment_sessions.status = completed`
- `assessment_sessions.raw_transcript` is present
- `assessment_reports.generation_status = completed`
- `assessment_reports.generated_at` is present
- `assessment_reports.email_sent_at` is present after Resend success

## Browser Voice Flow

Use this path when Vapi outbound phone numbers cannot call the candidate's country.

1. Start the backend and ngrok.
2. Run `python scripts\prepare_live_vapi_demo.py --backend-url http://127.0.0.1:8000 --reset-passwords`.
3. Start the frontend.
4. Sign in as the printed candidate account.
5. Open the printed `/demo/<session-id>` URL.
6. Load the session if needed, check microphone, then click **Start browser call**.

The frontend uses the Vapi public key, starts the assistant attached to the assessment, receives the browser call ID, and binds that call ID to the backend session. Vapi webhooks can then update the same session and trigger Azure OpenAI report generation.

Automated live-chain verifier:

```powershell
python scripts\verify_live_e2e.py --session-id <session-id> --timeout-seconds 900 --poll-seconds 10
```

This polls PostgreSQL until the real session has a Vapi call ID, completed session status, transcript, completed report, generated timestamp, and email timestamp. It exits non-zero if the chain times out or reaches a terminal failure. During early rehearsals without a verified Resend sender, use `--allow-missing-email`; do not use that flag for the final company demo.

## Automated API E2E Test

After the backend is migrated and reachable, run:

```powershell
$env:VOICE_E2E_BASE_URL="https://api.your-domain.example"
$env:VOICE_E2E_DATABASE_URL="postgresql+asyncpg://..."
$env:VAPI_WEBHOOK_SECRET="..."
pytest -q tests\test_api_e2e.py
```

This test creates isolated users, promotes one test user to admin through the database, creates an assessment/session, posts signed Vapi webhook events, verifies duplicate webhook idempotency, verifies report status behavior, and checks admin stats.

## Failure Triage

Vapi call creation fails:

- Check `VAPI_API_KEY`.
- Check `VAPI_PHONE_NUMBER_ID` only when using `VAPI_CALL_MODE=phone`.
- Check the assessment `vapi_assistant_id`.
- Check logs for `vapi_call_creation_status_failed`.

Webhook returns 401:

- Check `VAPI_WEBHOOK_SECRET` matches Vapi.
- Check timestamp skew is under 300 seconds.
- Check Vapi is sending `X-Vapi-Signature`.

Report stays pending:

- Confirm report worker is running.
- Check logs for `report_worker_claimed_reports`.
- Check `assessment_reports.generation_status`.

Report failed:

- Check `assessment_report_generation_failed`.
- Check the configured AI provider credentials.
- Check `AZURE_OPENAI_*` values when `AI_REPORT_PROVIDER=azure_openai`.
- Check `ANTHROPIC_*` values when `AI_REPORT_PROVIDER=anthropic`.

Email not sent:

- Check `email_send_attempt success=false`.
- Check `RESEND_API_KEY`.
- Check `RESEND_FROM_EMAIL` uses a verified Resend domain.
- Check Resend dashboard delivery logs.

## Launch Gate

Do not call the backend production-ready until all are true:

- Migrations applied to target PostgreSQL/Supabase.
- API health is `db=connected`.
- Worker or API has a public HTTPS URL.
- Vapi assistant created with the correct webhook URL.
- Vapi browser call or phone-call creation succeeds with a real candidate session.
- Signed Vapi webhooks are received and idempotency is verified.
- Azure OpenAI report generation completes with token usage stored.
- Resend report email is delivered and `email_sent_at` is set.
- `scripts\smoke_integrations.py --send-email` passes.
- Logs/alerts are wired for API 5xx, webhook failures, report failures, and email failures.
