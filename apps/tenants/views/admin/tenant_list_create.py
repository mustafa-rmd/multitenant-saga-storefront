from django.db import transaction
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response

from apps.core.responses import envelope
from apps.iam.models import TenantMembership
from apps.iam.views._base import ADMIN_DB_ALIAS, PlatformAdminAPIView
from apps.tenants.models import Tenant
from apps.tenants.serializers import TenantCreateSerializer, TenantSerializer
from apps.tenants.views.admin.tenant_create_per_tenant_resources import (
    create_per_tenant_sequences,
)


def _membership_prefetch():
    """Eager-load memberships + their users, on the admin DB alias."""
    return Prefetch(
        "memberships",
        queryset=TenantMembership.objects.using(ADMIN_DB_ALIAS).select_related("user"),
    )


@extend_schema_view(
    get=extend_schema(
        summary="List all tenants (platform-admin)", responses={200: TenantSerializer(many=True)}
    ),
    post=extend_schema(
        summary="Create a tenant", request=TenantCreateSerializer, responses={201: TenantSerializer}
    ),
)
class PlatformTenantListCreateView(PlatformAdminAPIView):
    serializer_class = TenantSerializer

    def get_queryset(self):
        return (
            Tenant.all_objects.using(ADMIN_DB_ALIAS)
            .prefetch_related(_membership_prefetch())
            .order_by("subdomain")
        )

    def get(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(TenantSerializer(page, many=True).data)
        return Response(envelope(TenantSerializer(qs, many=True).data, request=request))

    def post(self, request):
        s = TenantCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with transaction.atomic(using=ADMIN_DB_ALIAS):
            tenant = Tenant.all_objects.using(ADMIN_DB_ALIAS).create(**s.validated_data)
            create_per_tenant_sequences(tenant.id)
        return Response(
            envelope(TenantSerializer(tenant).data, request=request),
            status=status.HTTP_201_CREATED,
        )
