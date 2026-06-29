# Backend Readiness Audit

Last updated: 2026-06-01

This audit maps the backend against the assigned AI voice assessment platform deliverables. It is intentionally strict: local/mock verification is not counted as live production verification.

## Current Verdict

The backend is functionally scaffolded and locally verified. It is not yet production-launched because live Supabase, public HTTPS deployment, monitoring dashboards, and provider dashboards have not all been configured. Azure OpenAI, Vapi, and Resend credentials are configured for local demo use.

## Verification Evidence

Latest local checks:

```text
pytest -q: 14 passed, 1 skipped
pytest -q tests\test_api_e2e.py with local API/DB: 1 passed
alembic check: No new upgrade operations detected
verify_database_schema.py: ok
ops_probe.py: ok with local threshold
cloudflare/worker npm run typecheck: passed
/health: db connected
/ready: ready
```

Live-readiness check:

```text
validate_live_readiness.py: failed
```

That failure is expected with the current `.env` because several values are intentionally local placeholders.

## Deliverable Matrix

| Area | Status | Evidence | Remaining Blocker |
| --- | --- | --- | --- |
| FastAPI backend APIs | Done locally | Auth, assessment, session, report, admin, webhook routers exist and E2E test passes locally. | Live deployment URL and production credentials. |
| PostgreSQL schema | Done locally | Alembic initial schema, UUID PKs, timestamps, soft deletes, indexes, schema verifier passing. | Apply migrations to real Supabase/PostgreSQL. |
| Supabase alignment | Ready, blocked live | Asyncpg URL validation, Supabase pooler guidance, schema verifier. | Real `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. |
| Auth/RBAC | Done locally | JWT auth, bcrypt, admin/assessor/candidate role checks, E2E auth flow. | Production user provisioning/admin bootstrap policy. |
| Vapi outbound call integration | Partially blocked by provider policy | `/sessions/{id}/start-call`, payload tests, live Vapi smoke passes. | Free Vapi number does not support +91 international outbound calls. Use US/Canada number, paid/international-capable carrier, or browser web call path. |
| Vapi browser call integration | Demo ready | Frontend uses `@vapi-ai/web`, Vapi public key, assistant ID from session, and binds returned call ID to backend session. | Must complete one real browser call and verify webhook/report/email chain. |
| Vapi webhook integration | Done locally | HMAC validation, replay window, idempotency, transcript/status update, E2E signed webhooks. | Public HTTPS webhook URL and real Vapi delivery. |
| Vapi assistant workflow | Partially done | `scripts/provision_vapi_assistant.py` builds and posts assistant payload. | Must run against real Vapi and store returned assistant ID. |
| Azure OpenAI report generation | Live smoke passed | Structured prompt, JSON parsing/retry, token storage, failure state handling, Azure smoke check passed. | Complete one full Vapi transcript to Azure report live E2E. |
| Report worker | Done locally | Worker claims pending/stale reports with fresh DB sessions. | Must run as deployed process/service. |
| Resend email delivery | Demo ready | Async SDK adapter, templates, message ID logging, retry handling, sandbox email send passed. | Verified sender domain required for production sender identity. |
| Admin analytics | Done locally | SQL aggregate service and admin route; E2E caught and fixed JSONB bug. | Production-volume performance validation. |
| Cloudflare Worker edge | Ready, not deployed | Worker source, HMAC pre-validation, headers, CORS, typecheck passes. | Wrangler deploy and real `API_ORIGIN`/secrets. |
| Monitoring and ops visibility | Ready | `/ready`, structured logs, ops probe, alert rules, triage SQL. | Hook logs/probes into actual monitoring/on-call system. |
| Docker/deployment packaging | Ready, not runtime-tested in Docker | Dockerfile, compose migration/API/worker dependency chain, compose config valid. | Docker daemon unavailable locally; run compose in deployment environment. |
| Automated tests | Done locally | Unit/contract tests and opt-in real API E2E test. | Add CI wiring against disposable Postgres/Supabase branch DB. |
| Backups/recovery | Documented only | Operations docs include backup/restore guidance. | Configure Supabase PITR or scheduled backups and perform restore drill. |
| Production launch | Blocked | Readiness gate prevents placeholder launch. | Real credentials, public HTTPS API/Worker, live E2E pass. |

## Placeholder Values Blocking Live Readiness

Current `.env` still contains placeholder/local values for:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## Required Live Launch Sequence

1. Create/choose Supabase project.
2. Set production `.env` values.
3. Run:

```powershell
python scripts\validate_live_readiness.py --public-api-url https://api.your-domain.example
alembic upgrade head
python scripts\verify_database_schema.py
```

4. Start API and worker or use Docker Compose deployment chain.
5. Deploy Cloudflare Worker with `VAPI_WEBHOOK_SECRET`.
6. Run:

```powershell
python scripts\smoke_integrations.py
python scripts\smoke_integrations.py --send-email
```

7. Provision Vapi assistant:

```powershell
python scripts\provision_vapi_assistant.py --server-url https://api.your-domain.example
```

8. Create an active assessment using the returned `assistant_id`.
9. Run live Vapi call E2E and verify final state:

```text
assessment_sessions.status = completed
assessment_sessions.raw_transcript is present
assessment_sessions.vapi_analysis is present
assessment_reports.generation_status = completed
assessment_reports.generated_at is present
assessment_reports.email_sent_at is present
```

10. Run:

```powershell
python scripts\ops_probe.py
pytest -q tests\test_api_e2e.py
```

## Honest Alignment With Original Assignment

Aligned:

- Backend API contracts, auth, RBAC, database schema, migrations, Vapi webhook handling, report generation pipeline, Resend email integration, admin analytics, Cloudflare Worker edge proxy, security headers, rate limiting, structured logs, operations docs, deployment docs, and automated tests are implemented.

Not fully complete until live credentials/infrastructure exist:

- Real Supabase database migration.
- Real Vapi assistant creation and voice call.
- Full Vapi transcript to Azure OpenAI report generation E2E.
- Real Resend delivery.
- Production monitoring dashboard/on-call integration.
- Backup/PITR configuration and restore drill.
- Cloudflare Worker deployment.

Out of backend scope:

- Next.js frontend migration.
- Full candidate/recruiter/admin frontend UX depth.
- SPF/DKIM/DMARC DNS setup, though Resend sender verification is called out in docs.
