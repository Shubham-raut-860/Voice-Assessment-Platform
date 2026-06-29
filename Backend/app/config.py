from __future__ import annotations

from enum import StrEnum
from json import loads
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AIReportProvider(StrEnum):
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"


class VapiCallMode(StrEnum):
    WEB = "web"
    PHONE = "phone"


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")
    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    ai_report_provider: AIReportProvider = Field(default=AIReportProvider.ANTHROPIC, alias="AI_REPORT_PROVIDER")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-6", alias="ANTHROPIC_MODEL")
    anthropic_smoke_model: str = Field(
        default="claude-haiku-4-5-20251001",
        alias="ANTHROPIC_SMOKE_MODEL",
    )
    azure_openai_endpoint: str | None = Field(default=None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str | None = Field(default=None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_api_version: str | None = Field(default=None, alias="AZURE_OPENAI_API_VERSION")
    azure_chat_deployment: str | None = Field(default=None, alias="AZURE_CHAT_DEPLOYMENT")
    vapi_api_key: str = Field(alias="VAPI_API_KEY")
    vapi_webhook_secret: str = Field(alias="VAPI_WEBHOOK_SECRET")
    vapi_api_url: str = Field(default="https://api.vapi.ai", alias="VAPI_API_URL")
    vapi_call_mode: VapiCallMode = Field(default=VapiCallMode.WEB, alias="VAPI_CALL_MODE")
    vapi_phone_number_id: str | None = Field(default=None, alias="VAPI_PHONE_NUMBER_ID")
    resend_api_key: str = Field(alias="RESEND_API_KEY")
    resend_from_email: str = Field(
        default="Voice Assessment <[email-redacted]>",
        alias="RESEND_FROM_EMAIL",
    )
    admin_email: str = Field(alias="ADMIN_EMAIL")
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    require_email_verification: bool = Field(default=False, alias="REQUIRE_EMAIL_VERIFICATION")
    staff_signup_invite_code: str | None = Field(default=None, alias="STAFF_SIGNUP_INVITE_CODE")
    admin_signup_invite_code: str | None = Field(default=None, alias="ADMIN_SIGNUP_INVITE_CODE")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    environment: Environment = Field(alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: Annotated[list[str], NoDecode] = Field(alias="CORS_ORIGINS")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
        populate_by_name=True,
        case_sensitive=False,
    )

    @field_validator("database_url")
    @classmethod
    def validate_asyncpg_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return value

    @field_validator(
        "anthropic_model",
        "anthropic_smoke_model",
        "supabase_service_role_key",
        "vapi_api_key",
        "vapi_webhook_secret",
        "resend_api_key",
        "jwt_secret",
    )
    @classmethod
    def validate_secret_present(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("secret values must not be empty")
        return value

    @field_validator("staff_signup_invite_code", "admin_signup_invite_code", mode="before")
    @classmethod
    def normalize_optional_secret(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        raise ValueError("optional secret values must be strings")

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret_strength(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("only HS256 is supported by this scaffold")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized: str = value.upper()
        allowed_levels: set[str] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed_levels:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        return normalized

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        if isinstance(value, str):
            stripped: str = value.strip()
            if stripped.startswith("["):
                parsed: object = loads(stripped)
                if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                    return parsed
                raise ValueError("CORS_ORIGINS JSON must be a list of strings")
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        raise ValueError("CORS_ORIGINS must be a JSON list or comma-separated string")

    @model_validator(mode="after")
    def validate_production_cors(self) -> Self:
        if self.environment == Environment.PRODUCTION and "*" in self.cors_origins:
            raise ValueError("wildcard CORS origin is not allowed in production")
        return self

    @model_validator(mode="after")
    def validate_ai_provider_credentials(self) -> Self:
        if self.ai_report_provider == AIReportProvider.ANTHROPIC:
            if self.anthropic_api_key is None or self.anthropic_api_key.strip() == "":
                raise ValueError("ANTHROPIC_API_KEY is required when AI_REPORT_PROVIDER=anthropic")
            return self

        missing_fields: list[str] = []
        if self.azure_openai_endpoint is None or self.azure_openai_endpoint.strip() == "":
            missing_fields.append("AZURE_OPENAI_ENDPOINT")
        if self.azure_openai_api_key is None or self.azure_openai_api_key.strip() == "":
            missing_fields.append("AZURE_OPENAI_API_KEY")
        if self.azure_openai_api_version is None or self.azure_openai_api_version.strip() == "":
            missing_fields.append("AZURE_OPENAI_API_VERSION")
        if self.azure_chat_deployment is None or self.azure_chat_deployment.strip() == "":
            missing_fields.append("AZURE_CHAT_DEPLOYMENT")
        if missing_fields:
            raise ValueError(f"{', '.join(missing_fields)} required when AI_REPORT_PROVIDER=azure_openai")
        return self

    @model_validator(mode="after")
    def validate_vapi_phone_mode_requirements(self) -> Self:
        if self.vapi_call_mode == VapiCallMode.PHONE:
            if self.vapi_phone_number_id is None or self.vapi_phone_number_id.strip() == "":
                raise ValueError("VAPI_PHONE_NUMBER_ID is required when VAPI_CALL_MODE=phone")
        return self
