"""Stable application errors with safe, non-secret messages."""
from __future__ import annotations


class CoreError(Exception):
    status = 400
    code = "core_error"

    def __init__(self, message: str):
        super().__init__(message)


class MissingCredential(CoreError):
    status = 422
    code = "missing_credential"


class ProviderUnavailable(CoreError):
    status = 503
    code = "provider_unavailable"


class BudgetExceeded(CoreError):
    status = 429
    code = "budget_exceeded"


class UpstreamError(CoreError):
    status = 502
    code = "upstream_error"

    def __init__(self, status_code: int, retry_after: int | None = None):
        super().__init__("upstream request failed (HTTP " + str(status_code) + ")")
        self.status_code = status_code
        self.retry_after = retry_after


class InvalidRequest(CoreError):
    status = 422
    code = "invalid_request"


class UnsafeURL(CoreError):
    status = 422
    code = "unsafe_url"
