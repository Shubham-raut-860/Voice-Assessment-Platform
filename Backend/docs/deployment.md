# Deployment Runbook

This runbook defines the production startup order for the backend.

## Deployment Contract

The backend is considered started only after:

1. Environment values pass live-readiness validation.
2. Alembic migrations are applied.
3. Database schema verification passes.
4. API `/ready` returns `200`.
5. Report worker starts after the API is ready.
6. Integration smoke checks pass.

## Required Processes

- API process:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Report worker process:

```powershell
voice-report-worker --batch-size 5 --poll-seconds 10 --stale-after-seconds 900
```

- Cloudflare Worker:

```powershell
.\scripts\deploy_cloudflare_worker.ps1 `
  -Environment staging `
  -ApiOrigin "https://api-staging.your-domain.com" `
  -AllowedOrigins "https://app-staging.your-domain.com"
```

## Non-Docker Startup

Run from `D:\Shubham\voice project\Backend` with the deployment `.env` in place:

```powershell
python scripts\validate_live_readiness.py --public-api-url https://api.your-domain.example
alembic upgrade head
python scripts\verify_database_schema.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In a second process:

```powershell
voice-report-worker --batch-size 5 --poll-seconds 10 --stale-after-seconds 900
```

After the API is reachable:

```powershell
Invoke-RestMethod https://api.your-domain.example/ready
python scripts\smoke_integrations.py
python scripts\smoke_integrations.py --send-email
python scripts\ops_probe.py
```

For an ngrok-backed pre-production demo, use the local API origin and public tunnel:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
python scripts\prepare_live_vapi_demo.py --backend-url http://127.0.0.1:8000 --reset-passwords
python scripts\verify_live_e2e.py --session-id <session-id> --timeout-seconds 900
```

## Docker Compose Startup

Set the compose-only Postgres password in the shell, not in the app `.env`, because app settings intentionally reject unknown environment keys:

```powershell
$env:VOICE_ASSESSMENT_POSTGRES_PASSWORD="replace-with-local-compose-password"
```

For Docker Compose local development, compose overrides `DATABASE_URL` for the containerized API, migration, and worker services so they use the `postgres` service hostname. Your host-local `.env` may still point at `127.0.0.1` for non-container development.

Start:

```powershell
docker-compose up --build
```

The compose graph enforces:

```text
postgres healthy -> migrate exits 0 -> api /ready healthy -> report-worker starts
```

## Release Verification

Run before routing real users:

```powershell
python scripts\validate_live_readiness.py --public-api-url https://api.your-domain.example
python scripts\verify_database_schema.py
python scripts\smoke_integrations.py
python scripts\smoke_integrations.py --send-email
python scripts\verify_resend_readiness.py
python scripts\verify_vapi_assistant_readiness.py --assistant-id <assistant-id> --server-url https://api.your-domain.example
python scripts\ops_probe.py
```

Run the automated API E2E test against staging:

```powershell
$env:VOICE_E2E_BASE_URL="https://api-staging.your-domain.example"
$env:VOICE_E2E_DATABASE_URL="postgresql+asyncpg://..."
$env:VAPI_WEBHOOK_SECRET="..."
pytest -q tests\test_api_e2e.py
```

Run one real Vapi E2E rehearsal before a company demo:

```powershell
python scripts\prepare_live_vapi_demo.py --backend-url http://127.0.0.1:8000 --reset-passwords
python scripts\run_presentation_demo.py --mode live-vapi --vapi-assistant-id <assistant-id> --customer-number +15551234567 --reset-passwords
python scripts\verify_live_e2e.py --session-id <session-id> --timeout-seconds 900
```

The rehearsal is passing only when `verify_live_e2e.py` exits with `live_e2e: ok`.

## Rollback

Prefer rolling forward with a new migration. If rollback is unavoidable:

1. Stop API and worker processes.
2. Restore the previous application image or release artifact.
3. Restore database from the latest verified backup if the failed release applied incompatible migrations.
4. Run `python scripts\verify_database_schema.py`.
5. Start API.
6. Confirm `/ready`.
7. Start worker.
8. Run `python scripts\ops_probe.py`.
9. Run `python scripts\verify_live_e2e.py --session-id <known-test-session-id>` in staging before reopening live traffic.

## Launch Blockers

Do not deploy to production while any of these are true:

- `validate_live_readiness.py` fails.
- `alembic check` reports ungenerated migrations.
- `verify_database_schema.py` fails.
- `/ready` returns non-200.
- `smoke_integrations.py` fails against production credentials.
- `verify_resend_readiness.py` fails.
- `verify_vapi_assistant_readiness.py` fails for the active Riley assistant.
- Resend sender domain is not verified.
- Vapi assistant webhook URL does not point at the deployed HTTPS API or Worker.
- The report worker is not running.
