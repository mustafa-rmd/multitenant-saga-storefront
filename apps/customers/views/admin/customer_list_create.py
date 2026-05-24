from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.response import Response

from apps.core.responses import envelope
from apps.customers.models import Customer, CustomerType
from apps.customers.serializers_admin import (
    AdminCustomerCreateSerializer,
    AdminCustomerSerializer,
)
from apps.iam.views._base import TenantAdminAPIView

_TRUE_VALUES = frozenset({"true", "1", "yes"})
_FALSE_VALUES = frozenset({"false", "0", "no"})
_ALLOWED_CUSTOMER_TYPES = frozenset({CustomerType.B2C, CustomerType.B2B})


def _parse_bool(value: str, field: str) -> bool:
    lowered = value.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise serializers.ValidationError(
        {field: f"Must be true/false (or 1/0, yes/no), got {value!r}."}
    )


@extend_schema_view(
    get=extend_schema(
        summary="List customers (tenant-admin)",
        parameters=[
            OpenApiParameter(
                "email", OpenApiTypes.STR, description="Case-insensitive substring match on email."
            ),
            OpenApiParameter(
                "customer_type", OpenApiTypes.STR, description="Filter to `B2C` or `B2B`."
            ),
            OpenApiParameter(
                "is_active", OpenApiTypes.BOOL, description="Filter to active or blocked customers."
            ),
        ],
        responses={200: AdminCustomerSerializer(many=True)},
    ),
    post=extend_schema(
        summary="Create a customer (B2B pre-provisioning; identity still owned by the upstream IdP)",
        request=AdminCustomerCreateSerializer,
        responses={201: AdminCustomerSerializer},
    ),
)
class AdminCustomerListCreateView(TenantAdminAPIView):
    """List or create Customer rows for the resolved tenant.

    Creation here writes the application's record only -- the upstream
    identity proxy must still know about the email before the customer
    can authenticate via `X-Customer-Id`. Useful for B2B onboarding
    flows where the merchant pre-provisions the row.
    """

    serializer_class = AdminCustomerSerializer

    def get_queryset(self):
        qs = Customer.objects.all()
        params = self.request.query_params
        if email := params.get("email"):
            qs = qs.filter(email__icontains=email)
        if ctype := params.get("customer_type"):
            ctype_upper = ctype.upper()
            if ctype_upper not in _ALLOWED_CUSTOMER_TYPES:
                raise serializers.ValidationError(
                    {
                        "customer_type": (
                            f"Must be one of {sorted(_ALLOWED_CUSTOMER_TYPES)}, got {ctype!r}."
                        )
                    }
                )
            qs = qs.filter(customer_type=ctype_upper)
        if (is_active := params.get("is_active")) is not None and is_active != "":
            qs = qs.filter(is_active=_parse_bool(is_active, "is_active"))
        return qs.order_by("email")

    def get(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(AdminCustomerSerializer(page, many=True).data)
        return Response(envelope(AdminCustomerSerializer(qs, many=True).data, request=request))

    def post(self, request):
        s = AdminCustomerCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        customer = Customer.objects.create(**s.validated_data)
        return Response(
            envelope(AdminCustomerSerializer(customer).data, request=request),
            status=status.HTTP_201_CREATED,
        )
