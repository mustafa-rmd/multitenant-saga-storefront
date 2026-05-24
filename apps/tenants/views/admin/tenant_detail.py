from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.response import Response

from apps.core.exceptions import ResourceNotFound
from apps.core.responses import envelope
from apps.iam.models import TenantMembership
from apps.iam.views._base import ADMIN_DB_ALIAS, PlatformAdminAPIView
from apps.tenants.models import Tenant
from apps.tenants.serializers import TenantSerializer, TenantUpdateSerializer


@extend_schema_view(
    get=extend_schema(summary="Get a tenant", responses={200: TenantSerializer}),
    patch=extend_schema(
        summary="Update a tenant", request=TenantUpdateSerializer, responses={200: TenantSerializer}
    ),
)
class PlatformTenantDetailView(PlatformAdminAPIView):
    serializer_class = TenantSerializer
    lookup_url_kwarg = "tenant_id"

    def _get_object(self, tenant_id):
        try:
            return (
                Tenant.all_objects.using(ADMIN_DB_ALIAS)
                .prefetch_related(
                    Prefetch(
                        "memberships",
                        queryset=TenantMembership.objects.using(ADMIN_DB_ALIAS).select_related(
                            "user"
                        ),
                    )
                )
                .get(id=tenant_id)
            )
        except Tenant.DoesNotExist as exc:
            raise ResourceNotFound("Tenant not found") from exc

    def get(self, request, tenant_id):
        tenant = self._get_object(tenant_id)
        return Response(envelope(TenantSerializer(tenant).data, request=request))

    def patch(self, request, tenant_id):
        tenant = self._get_object(tenant_id)
        s = TenantUpdateSerializer(tenant, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        for field, value in s.validated_data.items():
            setattr(tenant, field, value)
        tenant.save(using=ADMIN_DB_ALIAS)
        return Response(envelope(TenantSerializer(tenant).data, request=request))
