from __future__ import annotations


class AppError(Exception):
    message: str
    code: str

    def __init__(self, message: str, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class ReportGenerationError(AppError):
    def __init__(self, message: str, code: str = "report_generation_error") -> None:
        super().__init__(message=message, code=code)


class WebhookValidationError(AppError):
    def __init__(self, message: str, code: str = "webhook_validation_error") -> None:
        super().__init__(message=message, code=code)


class AssessmentNotFoundError(AppError):
    def __init__(self, message: str, code: str = "assessment_not_found") -> None:
        super().__init__(message=message, code=code)


class SessionNotFoundError(AppError):
    def __init__(self, message: str, code: str = "session_not_found") -> None:
        super().__init__(message=message, code=code)


class EmailDeliveryError(AppError):
    def __init__(self, message: str, code: str = "email_delivery_error") -> None:
        super().__init__(message=message, code=code)
