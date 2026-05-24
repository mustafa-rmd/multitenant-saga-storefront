"""
Platform-admin trigger for the payment-reconciliation sweep.

POST /api/v1/admin/platform/ops/reconcile-payments

The reconciliation pass also runs on a Celery beat schedule every five
minutes (see `config/celery.py`). This endpoint exists for two reasons:

1. **Operational lever.** When a gateway has been down and we know there's
   a backlog of stuck PENDING payments, an operator can force a sweep
   immediately instead of waiting for the next beat tick.

2. **Testable surface.** Beat tasks aren't HTTP-reachable; an explicit
   trigger lets the Bun suite assert the task is wired up correctly and
   returns the documented summary shape.

Returns the summary dict directly inside the envelope, e.g.:

    {"scanned": 7, "converged": 1, "cancelled": 3, "stillPending": 3}

Synchronous on purpose -- the operator wants to see the result.
"""

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.response import Response

from apps.core.responses import envelope
from apps.iam.views._base import PlatformAdminAPIView
from apps.payments.tasks import RECONCILE_STALE_MINUTES, reconcile_pending_payments


class PlatformReconcilePaymentsView(PlatformAdminAPIView):
    """Force an immediate payment reconciliation sweep."""

    @extend_schema(
        summary="Force a payment reconciliation sweep (platform-admin)",
        parameters=[
            OpenApiParameter(
                "stale_after_minutes",
                OpenApiTypes.INT,
                description=(
                    "Override the staleness threshold (default 10). "
                    "Useful for one-off cleanups after a known incident."
                ),
                required=False,
            ),
        ],
        request=None,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "properties": {
                            "scanned": {"type": "integer"},
                            "converged": {"type": "integer"},
                            "cancelled": {"type": "integer"},
                            "stillPending": {"type": "integer"},
                        },
                    },
                },
            }
        },
    )
    def post(self, request):
        raw = request.query_params.get("stale_after_minutes")
        try:
            stale_after_minutes = int(raw) if raw is not None else RECONCILE_STALE_MINUTES
        except ValueError:
            stale_after_minutes = RECONCILE_STALE_MINUTES

        # Run synchronously so the operator sees the outcome in the
        # response. Behind the scenes this is the same code path the
        # beat-scheduled task executes.
        summary = reconcile_pending_payments(stale_after_minutes=stale_after_minutes)
        return Response(envelope(summary, request=request), status=status.HTTP_200_OK)
