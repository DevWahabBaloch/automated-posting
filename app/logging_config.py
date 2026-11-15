"""Logging setup with per-request correlation IDs."""

from __future__ import annotations

import logging
import logging.config
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": _RequestIdFilter}},
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                }
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                # httpx logs full request URLs at INFO. Telegram bot tokens and
                # Discord webhook tokens live in the URL, so keep it quiet.
                "httpx": {"level": "WARNING"},
                "httpcore": {"level": "WARNING"},
                "uvicorn.access": {"level": "WARNING"},
            },
        }
    )
