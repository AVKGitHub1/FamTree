"""Domain errors. The API layer maps each to an HTTP status."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status = 400
    code = "invalid_request"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFound(DomainError):
    status = 404
    code = "not_found"


class Forbidden(DomainError):
    status = 403
    code = "forbidden"


class InvalidInput(DomainError):
    status = 422
    code = "invalid_input"


class Conflict(DomainError):
    """The request conflicts with existing data (e.g. a duplicate relationship)."""

    status = 409
    code = "conflict"


class StaleRevision(DomainError):
    """Someone else saved the record first; the client must reload and reconcile."""

    status = 409
    code = "stale_revision"


class GraphRuleViolation(DomainError):
    """The change would break a family-graph invariant (cycle, missing public link)."""

    status = 422
    code = "graph_rule"
