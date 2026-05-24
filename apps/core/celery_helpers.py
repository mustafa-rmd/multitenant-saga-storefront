"""
Celery base task plumbing: tenant context + dead-letter publishing.

`TenantAwareTask` requires `tenant_id` as the first positional arg and
sets both the contextvar and the Postgres session variable before
running. Use it for any task that touches tenant-scoped tables.

`DurableTask` is the cross-tenant variant (sweepers, reconcilers). It
adds the same dead-letter behavior as `TenantAwareTask` without the
tenant-context machinery.

Both bases override `on_failure` so a task that exhausts `max_retries`
publishes a "death certificate" to the DLQ exchange before the message
is ack'd. Without this, retry-exhausted failures get logged and
forgotten -- the DLX wiring on the queue only catches worker-lost
nacks, not exhausted-retry acks. Republishing here gives operators a
single place (the `acme.dlq` queue) to inspect every task that gave
up.

Note: Celery workers connect to Postgres as `app_admin` (BYPASSRLS),
so the `SET LOCAL` isn't strictly necessary for the DB layer. We set
it anyway for defense in depth -- if a task is ever run as `app_user`
for any reason, RLS still fires.
"""

import json
import logging

from celery import Task
from celery.exceptions import Ignore, Retry
from django.db import connection
from django.utils import timezone

from apps.core.tenant_context import reset_current_tenant_id, set_current_tenant_id

log = logging.getLogger(__name__)


_DLQ_EXCHANGE = "acme.dlx"
_DLQ_ROUTING_KEY = "acme.dlq"


def _publish_death_certificate(task: Task, task_id, args, kwargs, exc) -> None:
    """Post a JSON record describing the terminal failure to the DLQ.

    This runs from `on_failure`, which Celery invokes after autoretry has
    exhausted `max_retries`. The original task message has already been
    ack'd at this point, so we have to publish a NEW message to the DLX
    exchange ourselves. The DLQ has no consumer -- an operator inspects
    it on demand (RabbitMQ console at http://localhost:15672).
    """
    body = {
        "task": task.name,
        "task_id": str(task_id),
        "args": list(args or ()),
        "kwargs": kwargs or {},
        "exception_class": type(exc).__name__,
        "exception_message": str(exc),
        "failed_at": timezone.now().isoformat(),
    }
    try:
        with task.app.producer_pool.acquire(block=True) as producer:
            producer.publish(
                json.dumps(body),
                exchange=_DLQ_EXCHANGE,
                routing_key=_DLQ_ROUTING_KEY,
                serializer="json",
                content_type="application/json",
                content_encoding="utf-8",
                # Persistent: survive a broker restart so the DLQ is the
                # source of truth even after infra hiccups.
                delivery_mode=2,
            )
    except Exception:
        # Last-ditch -- if publishing to the DLQ itself fails, log
        # loudly so the failure is at least in stdout.
        log.exception("DLQ publish failed for task=%s task_id=%s exc=%r", task.name, task_id, exc)


class _DeadLetterMixin:
    """Adds DLQ publishing to a Celery Task's terminal-failure path.

    Skips Retry (intermediate) and Ignore (intentional drop) exceptions
    so only real terminal failures get a death certificate.
    """

    def on_failure(self, exc, task_id, args, kwargs, einfo):  # noqa: D401 - Celery hook
        if not isinstance(exc, (Retry, Ignore)):
            log.error("Task %s gave up after retries: %r (task_id=%s)", self.name, exc, task_id)
            _publish_death_certificate(self, task_id, args, kwargs, exc)
        return super().on_failure(exc, task_id, args, kwargs, einfo)


class DurableTask(_DeadLetterMixin, Task):
    """Cross-tenant base. DLQ on terminal failure; no tenant context."""

    abstract = True


class TenantAwareTask(_DeadLetterMixin, Task):
    """Base task that enters tenant context for the duration of the task.

    Also routes terminal failures to the DLQ via `_DeadLetterMixin`.
    """

    abstract = True

    def __call__(self, *args, **kwargs):
        # With bind=True, Celery's `BoundTask.run` already strips `self`
        # before invoking the user function, so `args` here is always
        # the caller's positional arguments. tenant_id is the first.
        if not args:
            raise TypeError(f"{self.name} must be called with tenant_id as first argument")

        tenant_id = args[0]
        log.debug("Entering tenant context %s for task %s", tenant_id, self.name)

        token = set_current_tenant_id(tenant_id)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])
            try:
                return self.run(*args, **kwargs)
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("RESET app.current_tenant")
        finally:
            reset_current_tenant_id(token)
