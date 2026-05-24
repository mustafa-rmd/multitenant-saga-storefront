from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response

from apps.core.exceptions import CustomerNotFound
from apps.core.responses import envelope
from apps.customers.models import Customer
from apps.customers.serializers_admin import (
    AdminCustomerSerializer,
    AdminCustomerUpdateSerializer,
)
from apps.iam.views._base import TenantAdminAPIView


@extend_schema_view(
    get=extend_schema(
        summary="Get a customer (tenant-admin)", responses={200: AdminCustomerSerializer}
    ),
    patch=extend_schema(
        summary="Update a customer (also used to block/unblock via is_active)",
        request=AdminCustomerUpdateSerializer,
        responses={200: AdminCustomerSerializer},
    ),
    delete=extend_schema(
        summary="Soft-delete a customer (sets is_active=false; storefront auth then 401s)",
        responses={204: None},
    ),
)
class AdminCustomerDetailView(TenantAdminAPIView):
    """GET/PATCH/DELETE one customer.

    `DELETE` is soft (flips `is_active=False`) because Customer is
    referenced by Order with on_delete=PROTECT -- a hard delete would
    500 the moment the customer has any order history. Soft-delete
    doubles as the block/unblock primitive: the
    `CustomerAuthMiddleware` refuses `X-Customer-Id` lookups when
    `is_active=False`, returning `401 customer_not_found` (no
    enumeration).
    """

    serializer_class = AdminCustomerSerializer
    lookup_url_kwarg = "customer_id"

    def _get(self, customer_id):
        try:
            return Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist as exc:
            raise CustomerNotFound("Customer not found") from exc

    def get(self, request, customer_id):
        customer = self._get(customer_id)
        return Response(envelope(AdminCustomerSerializer(customer).data, request=request))

    def patch(self, request, customer_id):
        customer = self._get(customer_id)
        s = AdminCustomerUpdateSerializer(customer, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(envelope(AdminCustomerSerializer(customer).data, request=request))

    def delete(self, request, customer_id):
        customer = self._get(customer_id)
        if customer.is_active:
            customer.is_active = False
            customer.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
