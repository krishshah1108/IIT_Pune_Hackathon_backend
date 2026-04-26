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
