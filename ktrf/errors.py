"""Standard API error schema (spec §27.6, REQ-API-004).

Budget/timeout/truncation are NOT errors — they surface as HTTP 200 with
``degraded: true`` (§27.7, INV-013). Errors are reserved for requests that
cannot be processed at all.
"""

from __future__ import annotations

ERROR_TABLE = {
    "INVALID_REQUEST": (400, False),
    "INVALID_UTF8": (400, False),
    "UNAUTHENTICATED": (401, False),
    "FORBIDDEN_GLOSSARY": (403, False),
    "GLOSSARY_NOT_FOUND": (404, False),
    "GLOSSARY_VERSION_MISMATCH": (409, False),
    "INPUT_TOO_LARGE": (413, False),
    "RATE_LIMITED": (429, True),
    "INTERNAL": (500, True),
    "SNAPSHOT_UNAVAILABLE": (503, True),
}


class KtrfApiError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        if code not in ERROR_TABLE:
            code = "INTERNAL"
        self.code = code
        self.http_status, self.retryable = ERROR_TABLE[code]
        self.message = message
        self.details = details or {}
        super().__init__(f"{code}: {message}")

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "details": self.details,
            }
        }
