from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.enums import UserRole


class TokenResponse(BaseModel):
    access_token: str = Field(min_length=1)
    token_type: str = Field(default="bearer", min_length=1)
    expires_in: int = Field(gt=0)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.CANDIDATE
    invite_code: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, value: str) -> str:
        has_letter = any(character.isalpha() for character in value)
        has_digit = any(character.isdigit() for character in value)
        if not has_letter or not has_digit:
            raise ValueError("password must contain at least one letter and one number")
        return value
