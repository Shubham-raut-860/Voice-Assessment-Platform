from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from json import JSONDecodeError
from typing import cast
from uuid import UUID

import anthropic
import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.config import AIReportProvider, Settings
from app.exceptions import EmailDeliveryError, ReportGenerationError, SessionNotFoundError
from app.models.assessment_report import AssessmentReport
from app.models.assessment_session import AssessmentSession
from app.schemas.enums import PassFail, ReportStatus
from app.services.email_service import send_report_email

logger = structlog.get_logger(__name__)
DEFAULT_REPORT_MODEL = "pending"
PROMPT_VERSION = "assessment_report_v1"
MAX_REPORT_TOKENS = 4096

ASSESSMENT_SYSTEM_PROMPT: str = """
You are an expert voice-assessment evaluator for a production hiring and skills assessment platform.
Analyze the candidate's voice-based assessment transcript for the provided role, assessment title,
and assessment context. Evaluate only what is supported by the transcript and supplied context.

Your job:
- Score the performance fairly from 0 to 100.
- Identify concrete strengths and weaknesses.
- Cite specific transcript moments as evidence.
- Use calibrated judgment. Score inflation is a defect. A polished but shallow answer should not
  receive a high score. Strong evidence, specificity, reasoning quality, communication clarity,
  and role fit should drive the score.
- Use "inconclusive" when the transcript is missing, too short, corrupted, or does not contain
  enough assessment signal.

Output ONLY valid JSON. Do not include markdown, code fences, comments, preamble, or trailing text.
The JSON must match this exact structure:
{
  "overall_score": float,
  "pass_fail": "pass"|"fail"|"inconclusive",
  "strengths": [{"area": str, "evidence": str, "score": float}],
  "weaknesses": [{"area": str, "evidence": str, "score": float}],
  "detailed_analysis": str,
  "recommendations": str
}

Validation rules:
- overall_score must be between 0 and 100.
- Every strength and weakness score must be between 0 and 100.
- evidence fields must reference specific transcript content or explicitly say the transcript
  was insufficient.
- detailed_analysis must explain the scoring rationale.
- recommendations must be actionable and appropriate for the candidate's observed performance.
""".strip()


class ReportFindingContent(BaseModel):
    area: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=100.0)

    model_config = ConfigDict(extra="forbid")


class AnthropicReportPayload(BaseModel):
    overall_score: Decimal = Field(ge=Decimal("0.00"), le=Decimal("100.00"), max_digits=5)
    pass_fail: PassFail
    strengths: list[ReportFindingContent]
    weaknesses: list[ReportFindingContent]
    detailed_analysis: str = Field(min_length=1)
    recommendations: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


class ReportContent(AnthropicReportPayload):
    anthropic_model_used: str = Field(min_length=1, max_length=100)
    anthropic_prompt_tokens: int = Field(ge=0)
    anthropic_completion_tokens: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class AzureChatMessage(BaseModel):
    content: str | None = None

    model_config = ConfigDict(extra="ignore")


class AzureChatChoice(BaseModel):
    message: AzureChatMessage

    model_config = ConfigDict(extra="ignore")


class AzureChatUsage(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="ignore")


class AzureChatCompletionResponse(BaseModel):
    choices: list[AzureChatChoice] = Field(min_length=1)
    model: str | None = None
    usage: AzureChatUsage | None = None

    model_config = ConfigDict(extra="ignore")


async def build_assessment_prompt(session: AssessmentSession) -> str:
    assessment = session.assessment
    transcript = _format_transcript(session.raw_transcript)
    vapi_analysis = _format_vapi_analysis(session.vapi_analysis)

    return "\n".join(
        [
            f"Prompt version: {PROMPT_VERSION}",
            f"Assessment title: {assessment.title}",
            "Assessment description:",
            assessment.description,
            f"Passing score configured by platform: {assessment.passing_score}",
            f"Time limit minutes: {assessment.time_limit_minutes}",
            f"Session ID: {session.id}",
            f"Candidate ID: {session.candidate_id}",
            "Vapi structured analysis:",
            vapi_analysis,
            "Transcript:",
            transcript,
        ]
    )


async def generate_report(session: AssessmentSession, settings: Settings) -> ReportContent:
    if settings.ai_report_provider == AIReportProvider.AZURE_OPENAI:
        return await _generate_report_with_azure_openai(session, settings)
    return await _generate_report_with_anthropic(session, settings)


async def _generate_report_with_anthropic(session: AssessmentSession, settings: Settings) -> ReportContent:
    prompt = await build_assessment_prompt(session)
    if settings.anthropic_api_key is None:
        raise ReportGenerationError("anthropic_api_key_missing", "anthropic_configuration_error")
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]

    first_response = await _create_message_with_retries(client, messages, settings.anthropic_model)
    first_text = _extract_text(first_response)

    try:
        return _parse_report_content(
            raw_text=first_text,
            model_used=first_response.model,
            prompt_tokens=first_response.usage.input_tokens,
            completion_tokens=first_response.usage.output_tokens,
            provider_code="anthropic",
        )
    except ReportGenerationError as first_error:
        logger.warning(
            "anthropic_report_json_parse_failed_retrying",
            session_id=str(session.id),
            error=first_error.message,
        )

    repair_messages: list[dict[str, str]] = [
        *messages,
        {"role": "assistant", "content": first_text},
        {
            "role": "user",
            "content": (
                "Your previous response was not valid JSON matching the required schema. "
                "Return ONLY corrected valid JSON with the exact required keys and no markdown."
            ),
        },
    ]
    repair_response = await _create_message_with_retries(client, repair_messages, settings.anthropic_model)
    repair_text = _extract_text(repair_response)
    return _parse_report_content(
        raw_text=repair_text,
        model_used=repair_response.model,
        prompt_tokens=repair_response.usage.input_tokens,
        completion_tokens=repair_response.usage.output_tokens,
        provider_code="anthropic",
    )


async def _generate_report_with_azure_openai(session: AssessmentSession, settings: Settings) -> ReportContent:
    prompt = await build_assessment_prompt(session)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": ASSESSMENT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    first_response = await _create_azure_chat_completion_with_retries(messages, settings)
    first_text = _extract_azure_text(first_response)

    try:
        return _parse_report_content(
            raw_text=first_text,
            model_used=first_response.model or _require_setting(settings.azure_chat_deployment, "AZURE_CHAT_DEPLOYMENT"),
            prompt_tokens=first_response.usage.prompt_tokens if first_response.usage is not None else 0,
            completion_tokens=first_response.usage.completion_tokens if first_response.usage is not None else 0,
            provider_code="azure_openai",
        )
    except ReportGenerationError as first_error:
        logger.warning(
            "azure_openai_report_json_parse_failed_retrying",
            session_id=str(session.id),
            error=first_error.message,
        )

    repair_messages: list[dict[str, str]] = [
        *messages,
        {"role": "assistant", "content": first_text},
        {
            "role": "user",
            "content": (
                "Your previous response was not valid JSON matching the required schema. "
                "Return ONLY corrected valid JSON with the exact required keys and no markdown."
            ),
        },
    ]
    repair_response = await _create_azure_chat_completion_with_retries(repair_messages, settings)
    repair_text = _extract_azure_text(repair_response)
    return _parse_report_content(
        raw_text=repair_text,
        model_used=repair_response.model or _require_setting(settings.azure_chat_deployment, "AZURE_CHAT_DEPLOYMENT"),
        prompt_tokens=repair_response.usage.prompt_tokens if repair_response.usage is not None else 0,
        completion_tokens=repair_response.usage.completion_tokens if repair_response.usage is not None else 0,
        provider_code="azure_openai",
    )


async def trigger_report_generation(
    session_id: UUID,
    db: AsyncSession,
    settings: Settings,
    send_email: bool = True,
    claimed: bool = False,
) -> None:
    report: AssessmentReport | None = None

    try:
        session = await _load_session(db, session_id)
        report = await _get_or_create_report(db, session_id)
        if report.generation_status == ReportStatus.GENERATING and not claimed:
            logger.info(
                "assessment_report_generation_already_in_progress",
                session_id=str(session_id),
                report_id=str(report.id),
            )
            return
        if report.generation_status == ReportStatus.COMPLETED and not claimed:
            logger.info(
                "assessment_report_generation_already_completed",
                session_id=str(session_id),
                report_id=str(report.id),
            )
            return
        report.generation_status = ReportStatus.GENERATING
        report.generation_error = None
        await db.commit()
        logger.info(
            "assessment_report_generation_started",
            session_id=str(session_id),
            report_id=str(report.id),
        )

        content = await generate_report(session, settings)

        report.overall_score = content.overall_score
        report.pass_fail = content.pass_fail
        report.strengths = _findings_to_json(content.strengths)
        report.weaknesses = _findings_to_json(content.weaknesses)
        report.detailed_analysis = content.detailed_analysis
        report.recommendations = content.recommendations
        report.anthropic_model_used = content.anthropic_model_used
        report.anthropic_prompt_tokens = content.anthropic_prompt_tokens
        report.anthropic_completion_tokens = content.anthropic_completion_tokens
        report.generation_status = ReportStatus.COMPLETED
        report.generation_error = None
        report.generated_at = datetime.now(UTC)

        await db.commit()
        logger.info(
            "assessment_report_generation_completed",
            session_id=str(session_id),
            report_id=str(report.id),
            prompt_tokens=report.anthropic_prompt_tokens,
            completion_tokens=report.anthropic_completion_tokens,
        )

        if not send_email:
            logger.info(
                "assessment_report_email_skipped",
                session_id=str(session_id),
                report_id=str(report.id),
                reason="disabled_by_caller",
            )
            return

        try:
            await send_report_email(report, session, settings)
            await db.commit()
            logger.info(
                "assessment_report_email_sent",
                session_id=str(session_id),
                report_id=str(report.id),
                email_sent_at=report.email_sent_at.isoformat() if report.email_sent_at is not None else None,
            )
        except EmailDeliveryError as exc:
            await db.rollback()
            logger.warning(
                "assessment_report_email_delivery_failed",
                session_id=str(session_id),
                report_id=str(report.id),
                error=f"{exc.code}: {exc.message}",
            )
    except (ReportGenerationError, SessionNotFoundError) as exc:
        error_code = str(getattr(exc, "code", type(exc).__name__))
        await _mark_report_failed(db, report, session_id, f"{error_code}: {exc}")
    except SQLAlchemyError as exc:
        logger.exception("assessment_report_database_error", session_id=str(session_id), error=str(exc))
        await _mark_report_failed(db, report, session_id, f"database_error: {exc}")
    except Exception as exc:
        logger.exception("assessment_report_unexpected_error", session_id=str(session_id), error=str(exc))
        await _mark_report_failed(db, report, session_id, f"unexpected_error: {exc}")


async def trigger_report_generation_background(
    session_id: UUID,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    claimed: bool = False,
) -> None:
    async with session_factory() as db:
        await trigger_report_generation(session_id, db, settings, claimed=claimed)


async def _create_message_with_retries(
    client: anthropic.AsyncAnthropic,
    messages: list[dict[str, str]],
    model: str,
) -> anthropic.types.Message:
    rate_limit_attempts = 0
    connection_attempts = 0
    status_attempts = 0

    while True:
        try:
            return await client.messages.create(
                model=model,
                max_tokens=MAX_REPORT_TOKENS,
                temperature=0.2,
                system=ASSESSMENT_SYSTEM_PROMPT,
                messages=messages,
            )
        except anthropic.RateLimitError as exc:
            rate_limit_attempts += 1
            if rate_limit_attempts > 2:
                raise ReportGenerationError("anthropic_rate_limit_exhausted", "anthropic_rate_limited") from exc
            delay_seconds = float(2**rate_limit_attempts)
            logger.warning("anthropic_rate_limited", attempt=rate_limit_attempts, delay_seconds=delay_seconds)
            await asyncio.sleep(delay_seconds)
        except anthropic.APIConnectionError as exc:
            connection_attempts += 1
            if connection_attempts > 2:
                raise ReportGenerationError(
                    "anthropic_connection_retries_exhausted",
                    "anthropic_connection_error",
                ) from exc
            delay_seconds = float(connection_attempts)
            logger.warning(
                "anthropic_connection_error_retrying",
                attempt=connection_attempts,
                delay_seconds=delay_seconds,
            )
            await asyncio.sleep(delay_seconds)
        except anthropic.APIStatusError as exc:
            status_attempts += 1
            if exc.status_code < 500 or status_attempts > 1:
                raise ReportGenerationError(
                    f"anthropic_status_error:{exc.status_code}",
                    "anthropic_status_error",
                ) from exc
            logger.warning("anthropic_status_error_retrying", status_code=exc.status_code)
            await asyncio.sleep(1.0)
        except anthropic.APIError as exc:
            raise ReportGenerationError("anthropic_api_error", "anthropic_api_error") from exc


async def _create_azure_chat_completion_with_retries(
    messages: list[dict[str, str]],
    settings: Settings,
) -> AzureChatCompletionResponse:
    endpoint = _require_setting(settings.azure_openai_endpoint, "AZURE_OPENAI_ENDPOINT").rstrip("/")
    api_key = _require_setting(settings.azure_openai_api_key, "AZURE_OPENAI_API_KEY")
    api_version = _require_setting(settings.azure_openai_api_version, "AZURE_OPENAI_API_VERSION")
    deployment = _require_setting(settings.azure_chat_deployment, "AZURE_CHAT_DEPLOYMENT")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions"
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    params = {"api-version": api_version}
    rate_limit_attempts = 0
    connection_attempts = 0
    status_attempts = 0
    use_response_format = True
    use_max_completion_tokens = True
    include_temperature = True

    while True:
        payload: dict[str, object] = {
            "messages": messages,
        }
        if include_temperature:
            payload["temperature"] = 0.2
        if use_max_completion_tokens:
            payload["max_completion_tokens"] = MAX_REPORT_TOKENS
        else:
            payload["max_tokens"] = MAX_REPORT_TOKENS
        if use_response_format:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(url, headers=headers, params=params, json=payload)
                response.raise_for_status()
            decoded: object = response.json()
            return AzureChatCompletionResponse.model_validate(decoded)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            response_text = exc.response.text.lower()
            if status_code == 400 and "response_format" in response_text and use_response_format:
                use_response_format = False
                logger.warning("azure_openai_json_response_format_rejected_retrying_without_it")
                continue
            if status_code == 400 and "max_completion_tokens" in response_text and use_max_completion_tokens:
                use_max_completion_tokens = False
                logger.warning("azure_openai_max_completion_tokens_rejected_retrying_with_max_tokens")
                continue
            if status_code == 400 and "max_tokens" in response_text and not use_max_completion_tokens:
                use_max_completion_tokens = True
                logger.warning("azure_openai_max_tokens_rejected_retrying_with_max_completion_tokens")
                continue
            if status_code == 400 and "temperature" in response_text and include_temperature:
                include_temperature = False
                logger.warning("azure_openai_temperature_rejected_retrying_without_temperature")
                continue
            if status_code == 429:
                rate_limit_attempts += 1
                if rate_limit_attempts > 2:
                    raise ReportGenerationError(
                        "azure_openai_rate_limit_exhausted",
                        "azure_openai_rate_limited",
                    ) from exc
                delay_seconds = float(2**rate_limit_attempts)
                logger.warning(
                    "azure_openai_rate_limited",
                    attempt=rate_limit_attempts,
                    delay_seconds=delay_seconds,
                )
                await asyncio.sleep(delay_seconds)
                continue
            status_attempts += 1
            if status_code < 500 or status_attempts > 1:
                raise ReportGenerationError(
                    f"azure_openai_status_error:{status_code}",
                    "azure_openai_status_error",
                ) from exc
            logger.warning("azure_openai_status_error_retrying", status_code=status_code)
            await asyncio.sleep(1.0)
        except httpx.RequestError as exc:
            connection_attempts += 1
            if connection_attempts > 2:
                raise ReportGenerationError(
                    "azure_openai_connection_retries_exhausted",
                    "azure_openai_connection_error",
                ) from exc
            delay_seconds = float(connection_attempts)
            logger.warning(
                "azure_openai_connection_error_retrying",
                attempt=connection_attempts,
                delay_seconds=delay_seconds,
            )
            await asyncio.sleep(delay_seconds)
        except ValidationError as exc:
            raise ReportGenerationError(
                "azure_openai_response_schema_invalid",
                "azure_openai_schema_invalid",
            ) from exc
        except JSONDecodeError as exc:
            raise ReportGenerationError("azure_openai_non_json_response", "azure_openai_non_json_response") from exc


def _extract_text(response: anthropic.types.Message) -> str:
    text_parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            text_parts.append(text)
    combined = "".join(text_parts).strip()
    if combined == "":
        raise ReportGenerationError("anthropic_empty_response", "anthropic_empty_response")
    return combined


def _extract_azure_text(response: AzureChatCompletionResponse) -> str:
    content = response.choices[0].message.content
    if content is None or content.strip() == "":
        raise ReportGenerationError("azure_openai_empty_response", "azure_openai_empty_response")
    return content.strip()


def _parse_report_content(
    raw_text: str,
    model_used: str,
    prompt_tokens: int,
    completion_tokens: int,
    provider_code: str,
) -> ReportContent:
    try:
        decoded: object = json.loads(raw_text)
    except JSONDecodeError as exc:
        raise ReportGenerationError(f"{provider_code}_malformed_json", f"{provider_code}_malformed_json") from exc

    try:
        content = AnthropicReportPayload.model_validate(decoded)
    except ValidationError as exc:
        raise ReportGenerationError(
            f"{provider_code}_report_schema_invalid",
            f"{provider_code}_schema_invalid",
        ) from exc

    return ReportContent(
        **content.model_dump(),
        anthropic_model_used=model_used,
        anthropic_prompt_tokens=prompt_tokens,
        anthropic_completion_tokens=completion_tokens,
    )


def _require_setting(value: str | None, name: str) -> str:
    if value is None or value.strip() == "":
        raise ReportGenerationError(f"{name.lower()}_missing", "ai_provider_configuration_error")
    return value


async def _load_session(db: AsyncSession, session_id: UUID) -> AssessmentSession:
    try:
        query: Select[tuple[AssessmentSession]] = (
            select(AssessmentSession)
            .options(
                selectinload(AssessmentSession.assessment),
                selectinload(AssessmentSession.candidate),
            )
            .where(
                AssessmentSession.id == session_id,
                AssessmentSession.deleted_at.is_(None),
            )
        )
        result = await db.execute(query)
        session = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("assessment_session_load_failed", session_id=str(session_id), error=str(exc))
        raise

    if session is None:
        raise SessionNotFoundError(f"session_not_found:{session_id}")
    return session


async def _get_or_create_report(db: AsyncSession, session_id: UUID) -> AssessmentReport:
    try:
        query: Select[tuple[AssessmentReport]] = (
            select(AssessmentReport)
            .where(
                AssessmentReport.session_id == session_id,
                AssessmentReport.deleted_at.is_(None),
            )
            .with_for_update()
        )
        result = await db.execute(query)
        report = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.exception("assessment_report_lookup_failed", session_id=str(session_id), error=str(exc))
        raise

    if report is not None:
        return report

    report = AssessmentReport(
        session_id=session_id,
        version=1,
        overall_score=None,
        pass_fail=PassFail.INCONCLUSIVE,
        strengths=[],
        weaknesses=[],
        detailed_analysis="Report generation has not completed.",
        recommendations="Report generation has not completed.",
        anthropic_model_used=DEFAULT_REPORT_MODEL,
        anthropic_prompt_tokens=0,
        anthropic_completion_tokens=0,
        generation_status=ReportStatus.PENDING,
    )
    db.add(report)
    await db.flush()
    return report


async def _mark_report_failed(
    db: AsyncSession,
    report: AssessmentReport | None,
    session_id: UUID,
    error: str,
) -> None:
    try:
        await db.rollback()
        if report is None:
            report = await _find_report(db, session_id)
        if report is None:
            logger.info(
                "assessment_report_generation_failed_without_report",
                session_id=str(session_id),
                error=error[:4000],
            )
            return
        report.generation_status = ReportStatus.FAILED
        report.generation_error = error[:4000]
        await db.commit()
        logger.info(
            "assessment_report_generation_failed",
            session_id=str(session_id),
            report_id=str(report.id),
            error=report.generation_error,
        )
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.exception(
            "assessment_report_failure_state_update_failed",
            session_id=str(session_id),
            original_error=error,
            error=str(exc),
        )


async def _find_report(db: AsyncSession, session_id: UUID) -> AssessmentReport | None:
    query: Select[tuple[AssessmentReport]] = select(AssessmentReport).where(
        AssessmentReport.session_id == session_id,
        AssessmentReport.deleted_at.is_(None),
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


def _format_transcript(raw_transcript: str | None) -> str:
    if raw_transcript is None or raw_transcript.strip() == "":
        return "No transcript is available. Treat the report as inconclusive unless Vapi analysis supplies enough evidence."

    try:
        decoded: object = json.loads(raw_transcript)
    except JSONDecodeError:
        return raw_transcript

    if not isinstance(decoded, list):
        return raw_transcript

    lines: list[str] = []
    for item in decoded:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "unknown")
        content = item.get("content", "")
        timestamp = item.get("timestamp", "unknown")
        lines.append(f"[{timestamp}] {role}: {content}")

    if not lines:
        return "Transcript data was present but contained no readable turns."
    return "\n".join(lines)


def _format_vapi_analysis(vapi_analysis: dict[str, object] | None) -> str:
    if vapi_analysis is None:
        return "No Vapi structured analysis is available."
    return json.dumps(vapi_analysis, ensure_ascii=False, indent=2)


def _findings_to_json(findings: list[ReportFindingContent]) -> list[dict[str, object]]:
    return [cast(dict[str, object], finding.model_dump(mode="json")) for finding in findings]
