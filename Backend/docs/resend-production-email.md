# Resend Production Email Readiness

This project already sends transactional email through Resend. Production readiness requires a verified sender domain, correct DNS records, and a successful live send test.

## Current Demo Limitation

`[email-redacted]` is useful for Resend's first-email test, but it is not a production sender for this platform. In test mode, Resend can restrict delivery to the account owner's email address.

For production, set:

```text
RESEND_FROM_EMAIL="Voice Assessment <[email-redacted]>"
ADMIN_EMAIL=[email-redacted]
```

## Domain Setup

1. Open Resend dashboard.
2. Go to **Domains**.
3. Add your sending domain, for example:

```text
your-domain.com
```

4. Add the DNS records Resend gives you at your DNS provider.
5. Click **Verify DNS Records** in Resend.
6. Wait until the domain status is `verified`.

Resend's domain API returns each domain with status and sending capability. The project readiness script uses that API to confirm the configured sender domain is production-ready.

## DNS Records

The exact record names and values come from Resend. Production launch requires:

- SPF/return-path records requested by Resend.
- DKIM records requested by Resend.
- DMARC record on the root domain.

Minimal DMARC starter record:

```text
Name: _dmarc
Type: TXT
Value: v=DMARC1; p=none; rua=mailto:[email-redacted]
```

Move from `p=none` to `quarantine` or `reject` only after you confirm legitimate mail is aligned.

## Readiness Check

Run from the backend directory:

```powershell
cd "D:\Shubham\voice project\Backend"
C:\tmp\voice_backend_venv\Scripts\python.exe scripts\verify_resend_readiness.py
```

Expected production-ready result:

```text
matched_domain=your-domain.com status=verified sending_enabled=true
ready=true
```

Optional live send test:

```powershell
C:\tmp\voice_backend_venv\Scripts\python.exe scripts\verify_resend_readiness.py --send-test-to [email-redacted]
```

Before domain verification, use the Resend account owner's email for test sends. After domain verification, test a real candidate email.

## App-Level Email Checks

Send a direct Resend test email:

```powershell
C:\tmp\voice_backend_venv\Scripts\python.exe scripts\send_resend_test_email.py --to [email-redacted]
```

Then run the integration smoke test:

```powershell
C:\tmp\voice_backend_venv\Scripts\python.exe scripts\smoke_integrations.py --send-email
```

## Launch Acceptance Criteria

Email is production-ready only when all are true:

- `RESEND_FROM_EMAIL` uses your verified domain, not `[email-redacted]`.
- `verify_resend_readiness.py` exits with `ready=true`.
- A live report email sends to a non-owner candidate email.
- `AssessmentReport.email_sent_at` updates only after successful delivery request.
- Resend dashboard logs show the message id for support debugging.
- SPF, DKIM, and DMARC records exist in DNS.

## Failure Handling

The app already:

- Logs every email attempt with recipient, subject, template name, success/failure, and Resend message id when available.
- Retries transient send failures.
- Does not set `email_sent_at` unless Resend accepts the send.
- Raises `EmailDeliveryError` so the caller can choose retry/recovery behavior.

Common blockers:

- `RESEND_FROM_EMAIL` still uses `[email-redacted]`.
- Domain exists in Resend but status is `not_started`, `pending`, or `failed`.
- Sender address domain does not match a Resend domain.
- Resend API key belongs to a different account than the verified domain.
- DNS records have not propagated yet.
