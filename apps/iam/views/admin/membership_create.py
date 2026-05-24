from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response

from apps.core.exceptions import ResourceNotFound
from apps.core.responses import envelope
from apps.iam.models import TenantMembership
from apps.iam.serializers import MembershipCreateSerializer, MembershipSerializer
from apps.iam.views._base import ADMIN_DB_ALIAS, PlatformAdminAPIView
from apps.tenants.models import Tenant

User = get_user_model()


@extend_schema_view(
    post=extend_schema(
        summary="Assign a user as admin on a tenant",
        request=MembershipCreateSerializer,
        responses={201: MembershipSerializer},
    ),
)
class PlatformMembershipCreateView(PlatformAdminAPIView):
    """Bind a Django User to a tenant with a role.

    Reads the target tenant from the URL (`/platform/tenants/{tenant_id}/memberships`).
    With `create_user_if_missing=true`, creates the User in the same transaction
    using `initial_password` (which the new admin should rotate on first login).
    Idempotent: assigning the same (user, tenant) twice updates the role
    rather than 409-ing.
    """

    def post(self, request, tenant_id):
        s = MembershipCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            tenant = Tenant.all_objects.using(ADMIN_DB_ALIAS).get(id=tenant_id)
        except Tenant.DoesNotExist as exc:
            raise ResourceNotFound("Tenant not found") from exc

        with transaction.atomic(using=ADMIN_DB_ALIAS):
            try:
                user = User.objects.using(ADMIN_DB_ALIAS).get(email__iexact=v["email"])
            except User.DoesNotExist as exc:
                if not v["create_user_if_missing"]:
                    raise ResourceNotFound(
                        "User not found. Set createUserIfMissing=true to provision them."
                    ) from exc
                user = User(
                    username=v["email"],
                    email=v["email"],
                    first_name=v["first_name"],
                    last_name=v["last_name"],
                    is_active=True,
                )
                user.set_password(v["initial_password"])
                user.save(using=ADMIN_DB_ALIAS)

            membership, _ = TenantMembership.objects.using(ADMIN_DB_ALIAS).update_or_create(
                user=user,
                tenant=tenant,
                defaults={"role": v["role"]},
            )

        return Response(
            envelope(MembershipSerializer(membership).data, request=request),
            status=status.HTTP_201_CREATED,
        )
