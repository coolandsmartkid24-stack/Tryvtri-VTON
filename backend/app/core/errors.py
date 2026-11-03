"""HTTP error taxonomy and handlers.

Keeping every failure in one place guarantees consistent JSON bodies and
correct status codes for the storefront widget and the dashboard.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Base class for errors that map cleanly onto an HTTP response."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details or {}

    def to_payload(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {"error": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body


class ValidationError(ApiError):
    status_code = 422
    code = "validation_error"


class ImageRejected(ApiError):
    """Raised for SSRF, unsupported format, oversize or undownloadable images."""

    status_code = 400
    code = "invalid_image"


class QuotaExceeded(ApiError):
    status_code = 429
    code = "quota_exceeded"


class UpstreamUnavailable(ApiError):
    status_code = 503
    code = "upstream_unavailable"


class GpuError(ApiError):
    status_code = 503
    code = "gpu_error"


class Unauthorized(ApiError):
    status_code = 401
    code = "unauthorized"


class NotFound(ApiError):
    status_code = 404
    code = "not_found"


class Conflict(ApiError):
    status_code = 409
    code = "conflict"


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Something went wrong while processing this request.",
            "request_id": request_id,
        },
    )
