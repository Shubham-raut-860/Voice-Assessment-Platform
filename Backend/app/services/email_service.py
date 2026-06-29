from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol, cast

import structlog

from app.config import Settings
from app.exceptions import EmailDeliveryError
from app.models.assessment import Assessment
from app.models.assessment_report import AssessmentReport
from app.models.assessment_session import AssessmentSession
from app.models.user import User
from app.schemas.enums import PassFail, ReportStatus

logger = structlog.get_logger(__name__)
EMAIL_SEND_MAX_ATTEMPTS = 3
EMAIL_SEND_RETRY_DELAYS_SECONDS: tuple[float, ...] = (1.0, 3.0)
_resend_sdk_lock = asyncio.Lock()


class AsyncResendEmailsClient(Protocol):
    send: Callable[[dict[str, object]], Awaitable[object]]


class AsyncResendClient(Protocol):
    emails: AsyncResendEmailsClient


class ResendAsyncEmailsAdapter:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def send(self, payload: dict[str, object]) -> object:
        import resend
        from resend.async_request import AsyncRequest

        async with _resend_sdk_lock:
            previous_api_key = resend.api_key
            resend.api_key = self._api_key
            try:
                return await AsyncRequest[object](
                    path="/emails",
                    params=payload,
                    verb="post",
                    options=None,
                ).perform_with_content()
            finally:
                resend.api_key = previous_api_key


class ResendAsyncClientAdapter:
    def __init__(self, api_key: str) -> None:
        self.emails: AsyncResendEmailsClient = ResendAsyncEmailsAdapter(api_key)


def build_report_email_html(
    report: AssessmentReport,
    candidate: User,
    assessment: Assessment,
) -> str:
    candidate_name = _escape_html(candidate.full_name)
    assessment_title = _escape_html(assessment.title)
    score = _format_score(report.overall_score)
    badge_text = report.pass_fail.value.upper()
    badge_color = _pass_fail_color(report.pass_fail)
    strengths_html = _build_findings_list(report.strengths)
    weaknesses_html = _build_findings_list(report.weaknesses)
    recommendations = _format_paragraphs(report.recommendations)

    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background-color:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f7fb;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="width:640px;max-width:100%;background-color:#ffffff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
            <tr>
              <td style="background-color:#0f172a;padding:28px 32px;color:#ffffff;">
                <div style="font-size:14px;letter-spacing:0.08em;text-transform:uppercase;color:#93c5fd;">Voice Assessment</div>
                <h1 style="margin:8px 0 0;font-size:24px;line-height:32px;font-weight:700;">Your assessment report is ready</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <p style="margin:0 0 16px;font-size:16px;line-height:24px;">Hello {candidate_name},</p>
                <p style="margin:0 0 24px;font-size:16px;line-height:24px;">Your report for <strong>{assessment_title}</strong> has been generated.</p>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin-bottom:28px;">
                  <tr>
                    <td style="padding:16px;background-color:#f8fafc;border:1px solid #e5e7eb;border-radius:6px;">
                      <div style="font-size:13px;color:#64748b;margin-bottom:6px;">Overall Score</div>
                      <div style="font-size:32px;line-height:40px;font-weight:700;color:#111827;">{score}</div>
                    </td>
                    <td width="16"></td>
                    <td style="padding:16px;background-color:#f8fafc;border:1px solid #e5e7eb;border-radius:6px;">
                      <div style="font-size:13px;color:#64748b;margin-bottom:10px;">Result</div>
                      <span style="display:inline-block;background-color:{badge_color};color:#ffffff;border-radius:999px;padding:8px 14px;font-size:13px;font-weight:700;letter-spacing:0.04em;">{badge_text}</span>
                    </td>
                  </tr>
                </table>
                <h2 style="margin:0 0 12px;font-size:18px;line-height:26px;color:#111827;">Strengths</h2>
                {strengths_html}
                <h2 style="margin:28px 0 12px;font-size:18px;line-height:26px;color:#111827;">Areas To Improve</h2>
                {weaknesses_html}
                <h2 style="margin:28px 0 12px;font-size:18px;line-height:26px;color:#111827;">Recommendations</h2>
                <div style="font-size:15px;line-height:23px;color:#374151;">{recommendations}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px;background-color:#f8fafc;border-top:1px solid #e5e7eb;color:#64748b;font-size:12px;line-height:18px;">
                Voice Assessment Platform<br>
                This transactional email was sent because an assessment report was generated for your account.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


async def send_report_email(
    report: AssessmentReport,
    session: AssessmentSession,
    settings: Settings,
) -> str:
    if report.generation_status != ReportStatus.COMPLETED:
        logger.info(
            "email_send_skipped_report_not_completed",
            to_email=session.candidate.email,
            subject="Assessment report ready",
            template_name="report_ready",
            report_id=str(report.id),
            generation_status=report.generation_status.value,
            resend_message_id=None,
            success=False,
        )
        raise EmailDeliveryError("report_generation_not_completed", "report_not_completed")

    subject = f"Your assessment report is ready: {session.assessment.title}"
    html = build_report_email_html(report, session.candidate, session.assessment)
    message_id = await _send_email(
        settings=settings,
        to_email=session.candidate.email,
        subject=subject,
        template_name="report_ready",
        payload={
            "from": settings.resend_from_email,
            "to": [session.candidate.email],
            "subject": subject,
            "html": html,
        },
    )
    report.email_sent_at = datetime.now(UTC)
    return message_id


async def send_assessment_scheduled_email(
    session: AssessmentSession,
    settings: Settings,
) -> str:
    subject = f"Assessment scheduled: {session.assessment.title}"
    scheduled_at = (
        session.scheduled_at.isoformat() if session.scheduled_at is not None else "Your assessor will confirm the time."
    )
    html = f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background-color:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f7fb;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:600px;max-width:100%;background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;">
            <tr>
              <td style="padding:28px 32px;background:#0f172a;color:#ffffff;border-radius:8px 8px 0 0;">
                <div style="font-size:14px;letter-spacing:0.08em;text-transform:uppercase;color:#93c5fd;">Voice Assessment</div>
                <h1 style="margin:8px 0 0;font-size:22px;line-height:30px;">Assessment Scheduled</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;font-size:16px;line-height:24px;">
                <p style="margin:0 0 16px;">Hello {_escape_html(session.candidate.full_name)},</p>
                <p style="margin:0 0 16px;">Your assessment <strong>{_escape_html(session.assessment.title)}</strong> has been scheduled.</p>
                <p style="margin:0;"><strong>Scheduled time:</strong> {_escape_html(scheduled_at)}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #e5e7eb;color:#64748b;font-size:12px;">Voice Assessment Platform</td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return await _send_email(
        settings=settings,
        to_email=session.candidate.email,
        subject=subject,
        template_name="assessment_scheduled",
        payload={
            "from": settings.resend_from_email,
            "to": [session.candidate.email],
            "subject": subject,
            "html": html,
        },
    )


async def send_admin_alert_email(subject: str, body: str, settings: Settings) -> None:
    await _send_email(
        settings=settings,
        to_email=settings.admin_email,
        subject=subject,
        template_name="admin_alert",
        payload={
            "from": settings.resend_from_email,
            "to": [settings.admin_email],
            "subject": subject,
            "text": body,
        },
    )


async def send_resend_test_email(to_email: str, settings: Settings) -> str:
    subject = "Hello World"
    html = "<p>Congrats on sending your <strong>first email</strong>!</p>"
    return await _send_email(
        settings=settings,
        to_email=to_email,
        subject=subject,
        template_name="resend_hello_world",
        payload={
            "from": settings.resend_from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        },
    )


async def _send_email(
    settings: Settings,
    to_email: str,
    subject: str,
    template_name: str,
    payload: dict[str, object],
) -> str:
    resend_message_id: str | None = None
    client = _create_async_resend_client(settings.resend_api_key)
    last_error: Exception | None = None

    for attempt in range(1, EMAIL_SEND_MAX_ATTEMPTS + 1):
        try:
            response = await client.emails.send(payload)
            resend_message_id = _extract_message_id(response)
            logger.info(
                "email_send_attempt",
                to_email=to_email,
                subject=subject,
                template_name=template_name,
                resend_message_id=resend_message_id,
                success=True,
                attempt=attempt,
            )
            return resend_message_id
        except EmailDeliveryError as exc:
            logger.exception(
                "email_send_attempt",
                to_email=to_email,
                subject=subject,
                template_name=template_name,
                resend_message_id=resend_message_id,
                success=False,
                attempt=attempt,
                error=str(exc),
            )
            raise
        except Exception as exc:
            last_error = exc
            should_retry = _should_retry_email_error(exc) and attempt < EMAIL_SEND_MAX_ATTEMPTS
            logger.exception(
                "email_send_attempt",
                to_email=to_email,
                subject=subject,
                template_name=template_name,
                resend_message_id=resend_message_id,
                success=False,
                attempt=attempt,
                will_retry=should_retry,
                error=str(exc),
            )
            if not should_retry:
                raise EmailDeliveryError(f"email_delivery_failed:{template_name}") from exc
            await asyncio.sleep(EMAIL_SEND_RETRY_DELAYS_SECONDS[attempt - 1])

    raise EmailDeliveryError(f"email_delivery_failed:{template_name}") from last_error


def _create_async_resend_client(api_key: str) -> AsyncResendClient:
    try:
        import resend
    except ImportError as exc:
        raise EmailDeliveryError("resend_sdk_not_installed") from exc

    async_resend_factory = getattr(resend, "AsyncResend", None)
    if callable(async_resend_factory):
        client = async_resend_factory(api_key=api_key)
        return cast(AsyncResendClient, client)

    default_async_http_client = getattr(resend, "default_async_http_client", None)
    async_request_module = getattr(resend, "async_request", None)
    if default_async_http_client is not None and async_request_module is not None:
        return ResendAsyncClientAdapter(api_key)

    raise EmailDeliveryError("resend_async_client_unavailable")


def _extract_message_id(response: object) -> str:
    if isinstance(response, dict):
        message_id = response.get("id")
        if isinstance(message_id, str) and message_id.strip() != "":
            return message_id

    message_id_attr = getattr(response, "id", None)
    if isinstance(message_id_attr, str) and message_id_attr.strip() != "":
        return message_id_attr

    raise EmailDeliveryError("resend_message_id_missing")


def _should_retry_email_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code == 429 or status_code >= 500

    message = str(exc).lower()
    permanent_markers = (
        "api key is invalid",
        "invalid api key",
        "validation_error",
        "invalid `from`",
        "domain is not verified",
        "forbidden",
        "unauthorized",
    )
    if any(marker in message for marker in permanent_markers):
        return False

    transient_markers = (
        "timeout",
        "temporarily",
        "connection",
        "rate",
        "too many requests",
        "server error",
        "service unavailable",
    )
    return any(marker in message for marker in transient_markers)


def _build_findings_list(findings: list[dict[str, object]]) -> str:
    if not findings:
        return '<p style="margin:0;color:#64748b;font-size:15px;line-height:23px;">No items were identified.</p>'

    items = []
    for finding in findings:
        area = _escape_html(str(finding.get("area", "Assessment area")))
        evidence = _escape_html(str(finding.get("evidence", "No evidence provided.")))
        score = _escape_html(_format_score_value(finding.get("score")))
        items.append(
            f'<li style="margin:0 0 10px;"><strong>{area}</strong> '
            f'<span style="color:#64748b;">({score})</span><br>'
            f'<span style="color:#374151;">{evidence}</span></li>'
        )
    return f'<ul style="margin:0;padding-left:22px;font-size:15px;line-height:23px;">{"".join(items)}</ul>'


def _format_paragraphs(value: str) -> str:
    paragraphs = [part.strip() for part in value.split("\n") if part.strip()]
    if not paragraphs:
        return "<p style=\"margin:0;\">No recommendations were provided.</p>"
    return "".join(f'<p style="margin:0 0 12px;">{_escape_html(paragraph)}</p>' for paragraph in paragraphs)


def _format_score(score: Decimal | None) -> str:
    if score is None:
        return "N/A"
    return f"{score.quantize(Decimal('0.01'))}/100"


def _format_score_value(value: object) -> str:
    if isinstance(value, int | float | Decimal):
        return f"{float(value):.1f}/100"
    return "unscored"


def _pass_fail_color(pass_fail: PassFail) -> str:
    color_by_result: dict[PassFail, str] = {
        PassFail.PASS: "#15803d",
        PassFail.FAIL: "#b91c1c",
        PassFail.INCONCLUSIVE: "#92400e",
    }
    return color_by_result[pass_fail]


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
