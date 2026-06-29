# Production Alignment Plan

This project uses Cloudflare Workers as the public backend entrypoint for frontend and Vapi traffic. The Worker owns API ingress, request IDs, CORS, security headers, and Vapi webhook pre-validation, while the origin application service owns stateful product behavior such as auth, RBAC, PostgreSQL persistence, report generation, analytics, and email workflow state.

## Accepted Runtime Decisions

### Cloudflare Worker Backend Entrypoint

Decision: route public API traffic through the Cloudflare Worker and keep the stateful application service behind it.

Why this aligns with the assignment:

- The Worker handles serverless backend ingress: request IDs, security headers, CORS, upstream failure handling, and Vapi webhook validation.
- The origin application service owns stateful product behavior: auth, RBAC, assessment CRUD, Vapi webhook persistence, report generation state, analytics, and admin APIs.
- Alembic remains the migration source of truth for Supabase/PostgreSQL.
- The report worker can run independently from request-scoped webhooks.

Production acceptance criteria:

- Worker deployed with `API_ORIGIN`, `ALLOWED_ORIGINS`, and `VAPI_WEBHOOK_SECRET`.
- FastAPI origin is not exposed without TLS.
- `/ready` is monitored at the Worker URL and the origin URL.
- Live E2E passes through the Worker URL, not only localhost or ngrok.

### Vite React Frontend

Decision: keep Vite React for now.

Why this is acceptable for the demo/pre-production stage:

- The backend API contracts are framework-neutral.
- The frontend already integrates with the real FastAPI APIs.
- Migrating to Next.js is not required to prove the voice assessment workflow.

Production acceptance criteria:

- Frontend environment points to the Worker/API URL.
- Auth token handling and protected routes are verified in browser E2E.
- Static hosting has HTTPS, custom domain, and error-page routing for SPA refreshes.

## Remaining Go-Live Work

### Redis JWT Revocation

Status: implemented, tested, and wired into Docker Compose.

Activation:

```powershell
$env:VOICE_ASSESSMENT_POSTGRES_PASSWORD="local_voice_password"
docker-compose up --build
python scripts\verify_redis_revocation.py --base-url http://127.0.0.1:8000
```

For hosted environments, set:

```text
REDIS_URL=rediss://<user>:<password>@<redis-host>:<port>/0
```

Acceptance criteria:

- `POST /api/v1/auth/logout` returns `{"status":"revoked"}`.
- The same token receives `401` from `GET /api/v1/auth/me`.
- Redis persistence, backup, and memory eviction policy are configured by the hosting provider.

### Monitoring And Alerting

Status: operational probe exists; production scheduler and alert routing still need environment setup.

Required monitors:

- `/ready` every minute.
- API 5xx rate and p95 latency.
- `vapi_webhook_processing_failed`.
- `assessment_report_generation_failed`.
- `email_send_attempt success=false`.
- `ops_probe.py` on a 5-15 minute schedule.

Acceptance criteria:

- Alerts route to the company on-call channel and `ADMIN_EMAIL`.
- A failed report, failed webhook, or unsent completed report creates an alert within 15 minutes.
- Logs include request IDs and can be searched by `session_id`, `vapi_call_id`, and `report_id`.

### Backups

Status: documented; must be enabled in Supabase or the PostgreSQL host.

Acceptance criteria:

- Point-in-time recovery is enabled for production Supabase.
- Weekly restore drill into a separate database.
- Restored database passes `python scripts\verify_database_schema.py`.
- Backup secrets are restricted to operators only.

### Vapi Assistant Business Tuning

Status: baseline assistant provisioning exists; final business tuning requires stakeholder review.

Acceptance criteria:

- Assistant persona, scoring rubric, disqualifying signals, and closing script are approved.
- At least five trial calls are reviewed against expected scoring outcomes.
- Vapi webhook events are confirmed through the public Worker URL.
- Transcript quality is acceptable for the target accent, role, and interview style.

### SPF, DKIM, And DMARC

Status: infrastructure task; cannot be completed from backend code.

Acceptance criteria:

- Sender domain verified in Resend.
- DNS has Resend SPF/DKIM records.
- DMARC exists with at least `p=none` during warm-up, then stricter policy after validation.
- Report email delivery succeeds from the production sender domain, not only `[email-redacted]`.

## Demo Completion Evidence

The current local live proof has passed:

```text
Vapi browser call -> webhook -> transcript -> Azure report -> Resend email
```

For final demo proof, rerun:

```powershell
python scripts\verify_live_e2e.py --session-id <session-id> --timeout-seconds 900 --poll-seconds 10
```

The command must return:

```text
live_e2e: ok
```
