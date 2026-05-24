"""Celery app configuration.

Two things live here besides the usual Django glue:

1. **Beat schedule.** Three periodic tasks: reservation TTL sweep,
   stale-cart abandoner, and the payment reconciliation pass.

2. **Dead-letter queue.** Every task queue is declared with a
   `x-dead-letter-exchange` so messages that exhaust their `max_retries`
   (or are rejected by `acks_late` + worker crash combos) land in a DLQ
   instead of looping forever and saturating the worker pool. The DLQ
   has no consumer by design -- an operator looks at it on demand.
"""

import os

from celery import Celery
from celery.schedules import timedelta
from celery.signals import (
    before_task_publish,
    task_postrun,
    task_prerun,
)
from kombu import Exchange, Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# ---------------------------------------------------------------------------
# Request-id propagation across the queue boundary.
# ---------------------------------------------------------------------------
# Without this, an HTTP request that enqueues a task gets one request_id in
# its logs and the worker's log lines have none -- you can't correlate the
# two. We stamp the current contextvar onto the outbound message headers at
# publish time, and re-hydrate the contextvar on the worker side around
# task execution. No `.delay()` callsite has to change.
#
# Tenant id rides through a different path: TenantAwareTask requires it as
# the first positional arg and sets the tenant contextvar in __call__. That
# stays as-is.

_REQUEST_ID_HEADER = "x-request-id"


@before_task_publish.connect
def _attach_request_id_header(sender=None, headers=None, **kwargs):
    """Copy the calling request's id into the task message headers."""
    from apps.core.request_context import get_current_request_id

    if headers is None:
        return
    rid = get_current_request_id()
    if rid and _REQUEST_ID_HEADER not in headers:
        headers[_REQUEST_ID_HEADER] = rid


# Workers store the request-id contextvar token here so task_postrun can
# reset it. Keyed by task_id so concurrent tasks (gevent / eventlet pools)
# don't clobber each other's tokens.
_request_id_tokens: dict[str, object] = {}


@task_prerun.connect
def _enter_request_context(task_id=None, task=None, **kwargs):
    from apps.core.request_context import set_current_request_id

    rid = None
    request = getattr(task, "request", None)
    if request is not None:
        # Celery puts custom message headers under `request.headers`.
        msg_headers = getattr(request, "headers", None) or {}
        rid = msg_headers.get(_REQUEST_ID_HEADER)
    if rid:
        _request_id_tokens[task_id] = set_current_request_id(rid)


@task_postrun.connect
def _exit_request_context(task_id=None, **kwargs):
    from apps.core.request_context import reset_current_request_id

    token = _request_id_tokens.pop(task_id, None)
    if token is not None:
        reset_current_request_id(token)


# ---------------------------------------------------------------------------
# Queue topology: one work queue + one dead-letter queue.
# ---------------------------------------------------------------------------
# A task that exhausts max_retries (or is rejected after acks_late +
# worker-lost) gets nacked back to RabbitMQ. Without a DLX configured,
# `reject_on_worker_lost=True` requeues the message to the SAME queue,
# which means a poison message loops indefinitely. The DLX redirects it
# to `acme.dlq`, where it sits until someone investigates.
#
# Routing keys mirror queue names so we can add more named queues later
# (e.g. a `payments.high` priority lane) without touching the DLX wiring.

_default_exchange = Exchange("acme", type="direct")
_dlx_exchange = Exchange("acme.dlx", type="direct")

app.conf.task_default_queue = "acme.default"
app.conf.task_default_exchange = "acme"
app.conf.task_default_routing_key = "acme.default"

app.conf.task_queues = (
    Queue(
        "acme.default",
        exchange=_default_exchange,
        routing_key="acme.default",
        queue_arguments={
            "x-dead-letter-exchange": "acme.dlx",
            "x-dead-letter-routing-key": "acme.dlq",
        },
    ),
    Queue(
        "acme.dlq",
        exchange=_dlx_exchange,
        routing_key="acme.dlq",
        # No DLX on the DLQ itself -- terminal sink.
    ),
)

# ---------------------------------------------------------------------------
# Periodic tasks.
# ---------------------------------------------------------------------------
app.conf.beat_schedule = {
    "release-expired-reservations": {
        "task": "apps.orders.tasks.release_expired_reservations",
        "schedule": timedelta(seconds=30),
    },
    "abandon-stale-carts": {
        "task": "apps.carts.tasks.abandon_stale_carts",
        "schedule": timedelta(hours=1),
    },
    "reconcile-pending-payments": {
        # Catches PENDING payments orphaned by worker crashes /
        # gateway timeouts -- the "outage = money lost" mitigation.
        # See apps/payments/tasks.py:reconcile_pending_payments.
        "task": "apps.payments.tasks.reconcile_pending_payments",
        "schedule": timedelta(minutes=5),
    },
}


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
