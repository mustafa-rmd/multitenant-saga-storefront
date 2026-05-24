from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response

from apps.catalog.models import Product
from apps.catalog.serializers_admin import (
    AdminProductCreateSerializer,
    AdminProductSerializer,
)
from apps.core.responses import envelope
from apps.iam.views._base import TenantAdminAPIView


@extend_schema_view(
    get=extend_schema(
        summary="List products (admin: includes inactive)",
        responses={200: AdminProductSerializer(many=True)},
    ),
    post=extend_schema(
        summary="Create a product",
        request=AdminProductCreateSerializer,
        responses={201: AdminProductSerializer},
    ),
)
class AdminProductListCreateView(TenantAdminAPIView):
    """Admin list/create for the resolved tenant.

    Tenant scope is enforced by `TenantManager` (auto-filter by
    `app.current_tenant`) plus Postgres RLS on `app_user`. Unlike the
    storefront list, this returns inactive products too so admins can
    re-activate them.
    """

    serializer_class = AdminProductSerializer

    def get_queryset(self):
        return Product.objects.all().order_by("sku")

    def get(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(AdminProductSerializer(page, many=True).data)
        return Response(envelope(AdminProductSerializer(qs, many=True).data, request=request))

    def post(self, request):
        s = AdminProductCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        # tenant_id is auto-populated by TenantScopedModel.save() from the contextvar.
        product = Product.objects.create(**s.validated_data)
        return Response(
            envelope(AdminProductSerializer(product).data, request=request),
            status=status.HTTP_201_CREATED,
        )
