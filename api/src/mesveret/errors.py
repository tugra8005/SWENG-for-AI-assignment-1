"""Alan hataları. Mesajlar kullanıcıya gösterilir (Türkçe)."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status = 422

    def __init__(self, message: str, *, violations: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.violations = violations or []


class NotFound(DomainError):
    status = 404


class Forbidden(DomainError):
    status = 403


class Unauthorized(DomainError):
    status = 401


class Conflict(DomainError):
    status = 409
