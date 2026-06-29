# Operations Runbook

## Local Verification

```powershell
cd voice_assessment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
```

The API E2E test is opt-in because it mutates a real migrated database:

```powershell
$env:VOICE_E2E_BASE_URL="https://api.your-domain.example"
$env:VOICE_E2E_DATABASE_URL="postgresql+asyncpg://..."
$env:VAPI_WEBHOOK_SECRET="..."
pytest -q tests\test_api_e2e.py
```

It covers auth, admin role promotion, assessment creation, session creation, signed Vapi webhooks, webhook idempotency, report status, and admin stats.

## Database Migration

Alembic reads `DATABASE_URL` from the process environment or `.env`.

```powershell
alembic upgrade head
python scripts\verify_database_schema.py
```

For Supabase, prefer the direct connection or Supavisor session-mode connection for this long-running FastAPI backend. If you use Supabase transaction pooler on port `6543`, add `prepared_statement_cache_size=0` to the SQLAlchemy asyncpg URL:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?prepared_statement_cache_size=0"
```

Keep a separate native libpq URL for `pg_dump`/`pg_restore`; those commands do not understand the SQLAlchemy `postgresql+asyncpg://` scheme.

Offline SQL verification:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://user:password@host:5432/voice_assessment"
alembic upgrade head --sql
```

## API Runtime

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For full deployment sequencing, including migrations, API readiness, report worker startup, and Docker Compose, use `docs/deployment.md`.

Health and readiness checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Both endpoints verify PostgreSQL connectivity. Use `/health` for liveness and `/ready` for readiness; both return `503` when the database cannot be reached.

## Report Worker

Run one worker process per deployment environment:

```powershell
voice-report-worker --batch-size 5 --poll-seconds 10 --stale-after-seconds 900
```

The worker claims `pending` reports and stale `generating` reports. This prevents request-scoped background state from being the only path to report generation.

## Live Integration Smoke Tests

After `.env` contains real credentials:

```powershell
python scripts\validate_live_readiness.py --public-api-url https://api.your-domain.example
python scripts\smoke_integrations.py
```

To also send a real Resend admin-alert email:

```powershell
python scripts\smoke_integrations.py --send-email
```

Use `docs/live-e2e-runbook.md` for the complete Vapi call through report email validation path.

## Vapi Assistant Provisioning

Create the baseline assessment interviewer assistant after the public API or Worker URL is available:

```powershell
python scripts\provision_vapi_assistant.py --server-url https://api.your-domain.example
```

Use the returned assistant ID as the `vapi_assistant_id` when creating assessments.

## Cloudflare Worker

```powershell
cd cloudflare\worker
npm install
npm run typecheck
wrangler secret put VAPI_WEBHOOK_SECRET
wrangler deploy
```

Set `API_ORIGIN`, `ALLOWED_ORIGINS`, and `ENVIRONMENT` in `wrangler.toml` or environment-specific Wrangler config.

## Backups

For Supabase production projects, enable point-in-time recovery in Supabase. For self-hosted PostgreSQL, run scheduled `pg_dump` backups from a trusted host. Use a native libpq URL such as `postgresql://`, not the SQLAlchemy `postgresql+asyncpg://` URL:

```powershell
pg_dump --format=custom --file=voice_assessment.dump $env:POSTGRES_BACKUP_URL
```

Restore drill:

```powershell
pg_restore --clean --if-exists --dbname=$env:POSTGRES_BACKUP_URL voice_assessment.dump
```

Pre-production backup acceptance criteria:

- A scheduled backup exists for the target database.
- At least one restore drill has been completed into a separate database.
- The restored database passes `python scripts\verify_database_schema.py`.
- The restore procedure lists who can access the backup secret and where restore logs are stored.

## Monitoring Signals

Track these logs and metrics:

- API 5xx count and p95 latency by route.
- `vapi_webhook_processing_failed` and `vapi_webhook_transaction_failed`.
- `assessment_report_generation_failed`.
- `email_send_attempt` with `success=false`.
- Report worker claim count and stale report recovery count.
- PostgreSQL connection pool usage and slow queries.
- Resend delivery events in the Resend dashboard.
- Vapi call failures and webhook retry volume in the Vapi dashboard.

## Alert Rules

Use the `/ready` endpoint for load balancer readiness. It returns `503` when PostgreSQL cannot be reached.

Run the operations probe from CI, a scheduler, or an operations host:

```powershell
python scripts\ops_probe.py
```

Send an admin alert email when the probe fails:

```powershell
python scripts\ops_probe.py --send-alert-on-failure
```

This uses `ADMIN_EMAIL`, `RESEND_API_KEY`, and `RESEND_FROM_EMAIL`. Treat a failed alert send as a Resend key or verified sender-domain issue.

Recommended alert conditions:

- `/ready` returns non-200 for two consecutive checks.
- API 5xx rate is greater than 1% over five minutes.
- p95 API latency exceeds 1000 ms over five minutes.
- `vapi_webhook_processing_failed` count is greater than 0 over five minutes.
- `vapi_webhook_transaction_failed` count is greater than 0 over five minutes.
- `assessment_report_generation_failed` count is greater than 0 over ten minutes.
- `email_send_attempt success=false` count is greater than 0 over ten minutes.
- `ops_probe.py` reports `failed_reports`, `failed_webhooks`, `failed_sessions`, or `stale_generating_reports` above threshold.
- `unsent_completed_reports` grows for more than fifteen minutes.

For production, send these alerts to the on-call channel and `ADMIN_EMAIL`.

## Retry And Queue Model

The current pre-production queue is database-backed:

- Vapi `analysis.done` creates or resets an `assessment_reports` row to `pending`.
- `voice-report-worker` claims `pending` and stale `generating` rows with `FOR UPDATE SKIP LOCKED`.
- Stale `generating` reports are retried after `--stale-after-seconds`.
- AI provider calls retry rate limits, transient connection errors, and selected server errors.
- Resend email sends retry transient failures and avoid retrying permanent sender/auth failures.

For higher production scale, move report generation and email delivery to a managed queue such as Cloudflare Queues, Redis Queue, or a hosted job runner. Keep the database status fields as the source of truth even after adding a queue.

## Triage Queries

Failed reports:

```sql
select id, session_id, generation_status, left(generation_error, 500) as error, updated_at
from assessment_reports
where deleted_at is null and generation_status = 'failed'
order by updated_at desc
limit 20;
```

Stale report jobs:

```sql
select id, session_id, generation_status, updated_at
from assessment_reports
where deleted_at is null
  and generation_status = 'generating'
  and updated_at < now() - interval '15 minutes'
order by updated_at asc;
```

Webhook processing errors:

```sql
select event_type, vapi_event_id, left(error, 500) as error, processed_at
from webhook_events
where deleted_at is null and error is not null
order by processed_at desc
limit 20;
```

Completed reports with unsent email:

```sql
select id, session_id, generated_at
from assessment_reports
where deleted_at is null
  and generation_status = 'completed'
  and email_sent_at is null
order by generated_at asc
limit 20;
```
