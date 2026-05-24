"""
Admin REST surface, aggregated.

Two audiences share this URL tree:

  * Tenant-admin lives under each tenant's subdomain at /api/v1/admin/...
    and uses the default DB connection (RLS-enforced). Resource viewsets
    are co-located with their app (apps/<resource>/urls_admin.py) and
    included below.

  * Platform-admin lives under the reserved `admin` subdomain at
    /api/v1/admin/platform/... and uses the BYPASSRLS admin DB alias.
    Tenant CRUD and membership ops live in apps/tenants and apps/iam.

The path prefix `/api/v1/admin/` is exempt from CustomerAuthMiddleware
(AUTH_EXEMPT_PATHS) and `/api/v1/admin/platform/` is also exempt from
tenant resolution (GLOBAL_EXEMPT_PATHS). See apps/core/middleware/_exempt_paths.py.
"""

from django.urls import include, path

from apps.iam.views import AdminLoginView, AdminLogoutView, AdminMeView
from apps.iam.views.admin import (
    PlatformMembershipCreateView,
    PlatformMembershipDeleteView,
)
from apps.payments.views.admin import PlatformReconcilePaymentsView
from apps.tenants.views.admin import (
    PlatformTenantDetailView,
    PlatformTenantListCreateView,
)

urlpatterns = [
    # --- Auth (shared by both audiences) ---
    path("auth/login", AdminLoginView.as_view(), name="admin-login"),
    path("auth/logout", AdminLogoutView.as_view(), name="admin-logout"),
    path("auth/me", AdminMeView.as_view(), name="admin-me"),
    # --- Platform-admin (cross-tenant; admin DB alias) ---
    path(
        "platform/tenants",
        PlatformTenantListCreateView.as_view(),
        name="platform-tenant-list-create",
    ),
    path(
        "platform/tenants/<uuid:tenant_id>",
        PlatformTenantDetailView.as_view(),
        name="platform-tenant-detail",
    ),
    path(
        "platform/tenants/<uuid:tenant_id>/memberships",
        PlatformMembershipCreateView.as_view(),
        name="platform-membership-create",
    ),
    path(
        "platform/memberships/<uuid:membership_id>",
        PlatformMembershipDeleteView.as_view(),
        name="platform-membership-delete",
    ),
    path(
        "platform/ops/reconcile-payments",
        PlatformReconcilePaymentsView.as_view(),
        name="platform-reconcile-payments",
    ),
    # --- Tenant-admin (per-tenant; default DB; subdomain-scoped) ---
    path("", include("apps.catalog.urls_admin")),
    path("", include("apps.coupons.urls_admin")),
    path("", include("apps.payments.urls_admin")),
    path("", include("apps.orders.urls_admin")),
    # apps.customers exposes BOTH per-tenant /customers and the
    # platform-admin /platform/customers search in a single urlconf.
    path("", include("apps.customers.urls_admin")),
]
