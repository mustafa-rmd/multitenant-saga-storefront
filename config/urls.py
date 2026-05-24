"""Root URLconf for the Acme cart system."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import DashboardView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Operator dashboard (HTML, client-side; consumes /api/v1/admin/*)
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    # Health (exempt from auth in CustomerAuthMiddleware)
    path("api/v1/health", include("apps.core.urls")),
    # OpenAPI
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # Business APIs (storefront / customer-facing)
    path("api/v1/", include("apps.catalog.urls")),
    path("api/v1/", include("apps.customers.urls")),
    path("api/v1/", include("apps.coupons.urls")),
    path("api/v1/", include("apps.payments.urls")),
    path("api/v1/", include("apps.carts.urls")),
    path("api/v1/", include("apps.orders.urls")),
    # Admin REST surface (tenant-admin + platform-admin).
    # See apps/iam/urls_admin.py for the audience split.
    path("api/v1/admin/", include("apps.iam.urls_admin")),
]

if settings.DEBUG:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
