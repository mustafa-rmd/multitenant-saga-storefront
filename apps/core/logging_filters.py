"""
Logging plumbing for observability.

`RequestContextFilter` is attached to every console handler so each log
record gets `request_id` and `tenant_id` injected from the contextvars
set by middleware (HTTP) or Celery signals (async). The text formatter
references them in its format string; the JSON formatter emits them as
top-level keys so downstream tools (Loki, Datadog, jq) can filter on
them directly.

`JsonFormatter` is a minimal one-line-per-record formatter. Standard
library only -- no python-json-logger dependency for what amounts to
~15 lines.
"""

import json
import logging
from datetime import UTC, datetime

from apps.core.request_context import get_current_request_id
from apps.core.tenant_context import get_current_tenant_id


class RequestContextFilter(logging.Filter):
    """Inject request_id + tenant_id from contextvars into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_current_request_id() or "-"
        tenant_id = get_current_tenant_id()
        record.tenant_id = str(tenant_id) if tenant_id else "-"
        return True


# Stdlib LogRecord attributes we don't want to duplicate as "extras".
# Derived at import time from a synthetic empty record so new Python
# versions (3.12 added `taskName`, future versions may add more) flow
# through without an update here. Plus our two injected fields, which are
# promoted to top-level keys by the formatter.
_STDLIB_LOGRECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__.keys()) | frozenset(
    {"request_id", "tenant_id"}
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Designed for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "tenant_id": getattr(record, "tenant_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        # Any extras passed via logger.info(..., extra={...}) -- preserve them.
        for key, value in record.__dict__.items():
            if key in _STDLIB_LOGRECORD_ATTRS or key in payload:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        return json.dumps(payload, ensure_ascii=False)
