"""Cart-related async tasks."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.carts.models import Cart
from apps.core.celery_helpers import DurableTask

log = logging.getLogger(__name__)


@shared_task(
    base=DurableTask,
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def abandon_stale_carts(self, stale_after_days: int = 30):
    """Mark long-inactive active carts as abandoned. Runs hourly."""
    cutoff = timezone.now() - timedelta(days=stale_after_days)
    updated = Cart.all_objects.filter(
        status=Cart.Status.ACTIVE,
        updated_at__lt=cutoff,
    ).update(status=Cart.Status.ABANDONED)
    if updated:
        log.info("Abandoned %s stale carts (idle > %s days)", updated, stale_after_days)
    return updated
