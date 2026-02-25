"""Context propagation helpers — session_id and request_id via contextvars."""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

_session_id_var: ContextVar[str] = ContextVar("session_id", default="")
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_session_id() -> str:
    """Return the current session_id from context, or empty string."""
    return _session_id_var.get()


def set_session_id(value: str) -> None:
    """Set the session_id in the current context."""
    _session_id_var.set(value)


def get_request_id() -> str:
    """Return the current request_id from context, or empty string."""
    return _request_id_var.get()


def set_request_id(value: str) -> None:
    """Set the request_id in the current context."""
    _request_id_var.set(value)


def generate_request_id() -> str:
    """Generate a short unique request ID."""
    return uuid.uuid4().hex[:8]


class ContextFilter(logging.Filter):
    """Inject session_id and request_id into log records from contextvars."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = get_session_id()
        record.request_id = get_request_id()
        return True
