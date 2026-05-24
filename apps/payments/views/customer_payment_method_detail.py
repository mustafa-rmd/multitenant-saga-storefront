from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.core.exceptions import Forbidden
from apps.payments.models import PaymentMethod
from apps.payments.serializers import PaymentMethodSerializer


@extend_schema_view(
    get=extend_schema(summary="Get a saved payment method"),
    delete=extend_schema(summary="Delete a saved payment method"),
)
class CustomerPaymentMethodDetailView(generics.RetrieveDestroyAPIView):
    """Retrieve or delete a single saved payment method.

    `{customer_id}` must match `X-Customer-Id` (`403 forbidden`
    otherwise). `{method_id}` is the payment method's UUID.

    Update operations are deliberately not exposed — once tokenized, a
    saved method is immutable from the API's perspective. To change the
    default, use `PUT /customers/{customer_id}/payment-methods/{method_id}/default`.
    To replace card details, create a new method and delete the old one.

    `DELETE` is a hard delete. If the method is still referenced by an
    in-flight cart slot, Postgres will refuse via foreign key (the cart
    slot uses `on_delete=PROTECT`); clear the slot first. Historical
    orders snapshot their payment metadata so deletion never affects
    past orders.
    """

    serializer_class = PaymentMethodSerializer
    lookup_url_kwarg = "method_id"

    def get_queryset(self):
        customer_id = self.kwargs["customer_id"]
        if str(self.request.user.id) != str(customer_id):
            raise Forbidden("You can only access your own payment methods")
        return PaymentMethod.objects.filter(customer_id=customer_id)
