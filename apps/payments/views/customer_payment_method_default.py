from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import Forbidden, ResourceNotFound
from apps.core.responses import envelope
from apps.payments.models import PaymentMethod
from apps.payments.serializers import PaymentMethodSerializer


class CustomerPaymentMethodDefaultView(APIView):
    """Set a saved payment method as the customer's default."""

    @extend_schema(summary="Set this payment method as default")
    def put(self, request, customer_id, method_id):
        """Mark `method_id` as the default payment method for the customer.

        Atomically clears the existing default and sets the target row's
        `isDefault=true` in one transaction (no window where the customer
        has two defaults or none). Idempotent: if `method_id` is already
        the default, this returns the same row unchanged.

        `{customer_id}` must match `X-Customer-Id` (`403 forbidden`).
        Returns the updated method envelope. Errors:
        - `403 forbidden` — customer mismatch.
        - `404 resource_not_found` — method doesn't exist or belongs to
          another customer.
        """
        if str(request.user.id) != str(customer_id):
            raise Forbidden("You can only access your own payment methods")

        with transaction.atomic():
            try:
                target = PaymentMethod.objects.select_for_update().get(
                    id=method_id,
                    customer_id=customer_id,
                )
            except PaymentMethod.DoesNotExist as e:
                raise ResourceNotFound("Payment method not found") from e

            PaymentMethod.objects.filter(
                customer_id=customer_id,
                is_default=True,
            ).exclude(id=target.id).update(is_default=False)

            if not target.is_default:
                target.is_default = True
                target.save(update_fields=["is_default", "updated_at"])

        return Response(envelope(PaymentMethodSerializer(target).data, request=request))
