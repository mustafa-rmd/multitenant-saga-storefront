from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.response import Response

from apps.core.exceptions import Forbidden
from apps.core.responses import envelope
from apps.customers.models import Customer
from apps.payments.gateways import registry
from apps.payments.models import PaymentMethod, PaymentMethodType
from apps.payments.serializers import (
    CreatePaymentMethodSerializer,
    PaymentMethodSerializer,
)
from apps.payments.services import build_credentials, resolve_gateway_config


@extend_schema_view(
    get=extend_schema(summary="List the customer's saved payment methods"),
    post=extend_schema(summary="Save a payment method"),
)
class CustomerPaymentMethodListCreateView(generics.ListCreateAPIView):
    """List or create saved payment methods for the authenticated customer.

    The `{customer_id}` must match `X-Customer-Id` (`403 forbidden`
    otherwise). Payment methods are customer-scoped and live in the
    tenant resolved from the request subdomain.

    `GET` returns the customer's saved methods (no pagination — customers
    rarely have more than a handful). The serializer returns only the
    displayable `brand` + `lastFour` and never the raw `token`.

    `POST` supports two tokenization flows:

    1. **Client-side tokenization** (Stripe.js / Elements). Client
       already exchanged the card for a token; pass it as `token` plus
       displayable `brand` / `lastFour`. The raw PAN never touches our
       servers — PCI-favourable.
    2. **Server-side tokenization** (mock / dev). Omit `token` and the
       gateway's `tokenize()` is called with a synthetic payload. Only
       safe for the `mock` gateway in tests/dev.

    Setting `isDefault: true` clears the existing default for this
    customer in the same transaction.
    """

    serializer_class = PaymentMethodSerializer

    def get_queryset(self):
        customer_id = self.kwargs["customer_id"]
        if str(self.request.user.id) != str(customer_id):
            raise Forbidden("You can only access your own payment methods")
        return PaymentMethod.objects.filter(customer_id=customer_id).order_by(
            "-is_default", "-created_at"
        )

    def create(self, request, *args, **kwargs):
        customer_id = self.kwargs["customer_id"]
        if str(request.user.id) != str(customer_id):
            raise Forbidden("You can only access your own payment methods")

        s = CreatePaymentMethodSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        method_type = v.get("method_type", PaymentMethodType.CARD)

        if method_type == PaymentMethodType.PURCHASE_ORDER:
            # PO accounts are a B2B-only artifact. Refuse for B2C customers
            # so a typo or curious frontend can't bypass the gateway path.
            customer = Customer.objects.get(id=customer_id)
            if not customer.is_b2b:
                raise Forbidden("Purchase-order payment methods are restricted to B2B customers")

            with transaction.atomic():
                if v.get("is_default", False):
                    PaymentMethod.objects.filter(
                        customer_id=customer_id,
                        is_default=True,
                    ).update(is_default=False)
                pm = PaymentMethod.objects.create(
                    customer_id=customer_id,
                    method_type=PaymentMethodType.PURCHASE_ORDER,
                    gateway_config=None,
                    token="",
                    brand="",
                    last_four="",
                    payment_terms=v.get("payment_terms") or "net_30",
                    po_account_label=v.get("po_account_label") or "",
                    is_default=v.get("is_default", False),
                )

            return Response(
                envelope(PaymentMethodSerializer(pm).data, request=request),
                status=status.HTTP_201_CREATED,
            )

        # --- Card path (unchanged) ---
        gateway_config = resolve_gateway_config(gateway_name=v["gateway_name"])

        # If client provided a token directly (e.g. Stripe.js flow), use it.
        # Otherwise call tokenize() on the gateway (mock flow).
        token = v.get("token") or ""
        brand = v.get("brand") or ""
        last_four = v.get("last_four") or ""

        if not token:
            gateway = registry.get(gateway_config.gateway_name)
            credentials = build_credentials(gateway_config)
            tokenized = gateway.tokenize(
                credentials=credentials,
                payload={"brand": brand or "visa", "last_four": last_four or "4242"},
            )
            token = tokenized.gateway_token
            brand = tokenized.brand
            last_four = tokenized.last_four

        with transaction.atomic():
            if v.get("is_default", False):
                PaymentMethod.objects.filter(
                    customer_id=customer_id,
                    is_default=True,
                ).update(is_default=False)
            pm = PaymentMethod.objects.create(
                customer_id=customer_id,
                method_type=PaymentMethodType.CARD,
                gateway_config=gateway_config,
                token=token,
                brand=brand,
                last_four=last_four,
                is_default=v.get("is_default", False),
            )

        return Response(
            envelope(PaymentMethodSerializer(pm).data, request=request),
            status=status.HTTP_201_CREATED,
        )
