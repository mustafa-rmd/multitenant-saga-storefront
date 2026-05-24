from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response

from apps.core.responses import envelope, error_envelope
from apps.customers.models import Customer
from apps.customers.serializers_platform import PlatformCustomerSerializer
from apps.iam.views._base import ADMIN_DB_ALIAS, PlatformAdminAPIView


@extend_schema_view(
    get=extend_schema(
        summary="Cross-tenant customer search (platform-admin)",
        parameters=[
            OpenApiParameter(
                "email", OpenApiTypes.STR, description="Case-insensitive substring match on email."
            ),
            OpenApiParameter(
                "tenant_subdomain",
                OpenApiTypes.STR,
                description="Filter to one tenant's customers (e.g. `store-a`).",
            ),
        ],
        responses={200: PlatformCustomerSerializer(many=True)},
    ),
)
class PlatformCustomerListView(PlatformAdminAPIView):
    """Read-only cross-tenant customer search for support escalations.

    Runs on the `admin` DB connection (BYPASSRLS). Mandatory `email`
    filter so the endpoint never accidentally dumps the entire
    customer table. Returns at most one page (paginated) with
    `tenant_subdomain` per row so the support agent can hop into the
    right tenant for follow-up.
    """

    serializer_class = PlatformCustomerSerializer

    # EmailField max is 254 chars (RFC 5321). Anything longer is either a
    # client bug or someone trying to lean on the LIKE query for denial.
    EMAIL_MAX_LENGTH = 254

    def get(self, request):
        email = (request.query_params.get("email") or "").strip()
        if not email:
            return Response(
                error_envelope(
                    {
                        "code": "email_query_required",
                        "detail": (
                            "Provide ?email= (case-insensitive substring); "
                            "searching by tenant alone is not supported."
                        ),
                    },
                    request=request,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(email) > self.EMAIL_MAX_LENGTH:
            return Response(
                error_envelope(
                    {
                        "code": "email_query_too_long",
                        "detail": (f"Email query exceeds the {self.EMAIL_MAX_LENGTH}-char cap."),
                    },
                    request=request,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = (
            Customer.all_objects.using(ADMIN_DB_ALIAS)
            .select_related("tenant")
            .filter(email__icontains=email)
        )
        if tenant_subdomain := request.query_params.get("tenant_subdomain"):
            qs = qs.filter(tenant__subdomain=tenant_subdomain)
        qs = qs.order_by("tenant__subdomain", "email")

        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(PlatformCustomerSerializer(page, many=True).data)
        return Response(envelope(PlatformCustomerSerializer(qs, many=True).data, request=request))
