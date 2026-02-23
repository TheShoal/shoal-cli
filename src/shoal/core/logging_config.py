"""Centralized logging configuration for Shoal."""

from __future__ import annotations

import json
import logging
import time

from shoal.core.context import ContextFilter


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Add context fields if present (injected by ContextFilter)
        session_id = getattr(record, "session_id", "")
        request_id = getattr(record, "request_id", "")
        if session_id:
            data["session_id"] = session_id
        if request_id:
            data["request_id"] = request_id

        if record.exc_info and record.exc_info[1] is not None:
            data["error"] = str(record.exc_info[1])

        return json.dumps(data, default=str)


def configure_logging(
    *,
    level: str = "WARNING",
    json_logs: bool = False,
    log_file: str | None = None,
) -> None:
    """Set up the ``shoal`` logger with the given configuration.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
        json_logs: If True, use JsonFormatter instead of text format.
        log_file: If provided, log to this file instead of stderr.
    """
    shoal_logger = logging.getLogger("shoal")
    shoal_logger.setLevel(getattr(logging, level.upper(), logging.WARNING))

    # Remove existing handlers to avoid duplication on reconfigure
    shoal_logger.handlers.clear()

    if log_file:
        handler: logging.Handler = logging.FileHandler(log_file)
    else:
        handler = logging.StreamHandler()

    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(levelname)s %(name)s [sid=%(session_id)s rid=%(request_id)s]: %(message)s"
            )
        )

    handler.addFilter(ContextFilter())
    shoal_logger.addHandler(handler)
