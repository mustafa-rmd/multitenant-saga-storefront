from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response

from apps.core.exceptions import ResourceNotFound
from apps.iam.models import TenantMembership
from apps.iam.views._base import ADMIN_DB_ALIAS, PlatformAdminAPIView


@extend_schema_view(
    delete=extend_schema(summary="Revoke a membership", responses={204: None}),
)
class PlatformMembershipDeleteView(PlatformAdminAPIView):
    """Hard-delete a membership row. The user's token (if any) is left intact
    -- their next admin request fails at IsTenantAdmin's live membership check.
    """

    def delete(self, request, membership_id):
        deleted, _ = (
            TenantMembership.objects.using(ADMIN_DB_ALIAS).filter(id=membership_id).delete()
        )
        if deleted == 0:
            raise ResourceNotFound("Membership not found")
        return Response(status=status.HTTP_204_NO_CONTENT)
