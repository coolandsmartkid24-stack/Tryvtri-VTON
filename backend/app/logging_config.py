"""Structured logging setup.

Every log line carries a ``request_id`` so a storefront request can be traced
through validation → quota → GPU wake-up → inference → persistence.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", *, force: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: Optional[str] = None, **initial):
    """Return a structlog logger."""
    if not _CONFIGURED:
        configure_logging()
    logger = structlog.get_logger(name)
    if initial:
        return logger.bind(**initial)
    return logger
