# Ensure the Celery app instance is loaded whenever Django starts.
#
# Without this import, Django code calling `.delay()` on a `@shared_task`
# resolves against Celery's default global app (with hard-coded defaults:
# queue=`celery`, exchange=`celery`). The worker, started via `celery -A
# config`, *does* load `config.celery` and consumes from `acme.default`.
# The mismatch lets messages pile up in the `celery` queue forever with
# no consumer -- silent, but fatal for any post-payment background work.
from .celery import app as celery_app

__all__ = ("celery_app",)
