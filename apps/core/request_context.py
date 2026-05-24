"""
Per-request correlation id. Stored in a ContextVar so it survives across
sync/async boundaries (Django sync views, async views, Celery's prefork
worker which copies context per task).

The middleware sets this at the start of each HTTP request from the
inbound `X-Request-ID` header (or a fresh UUID4 if absent). The logging
filter and the response envelope both read it so a single id flows from
the client header through every log line, the response body's
`meta.request_id`, and the response header back to the caller.

Celery signals in `config/celery.py` carry the same id across the
queue boundary so async work logs under the same correlation id as the
request that enqueued it.
"""

from contextvars import ContextVar

_current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


def get_current_request_id() -> str | None:
    return _current_request_id.get()


def set_current_request_id(request_id: str | None):
    return _current_request_id.set(request_id)


def reset_current_request_id(token) -> None:
    _current_request_id.reset(token)
