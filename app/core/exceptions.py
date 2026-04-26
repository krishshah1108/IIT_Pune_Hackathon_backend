"""Custom application exceptions."""


class AppError(Exception):
    """Base application exception."""


class ValidationError(AppError):
    """Raised for domain-level validation errors."""


class NotFoundError(AppError):
    """Raised when requested resource cannot be found."""


class ConflictError(AppError):
    """Raised on duplicate or conflicting state."""


class UnauthorizedError(AppError):
    """Raised when authentication fails."""


class RetryableAgentError(AppError):
    """Raised for transient agent failures that can be retried."""


class V0PaymentRequiredError(AppError):
    """v0 API returned 402; resolve billing, credits, or plan on the v0.dev account."""
