"""Operator dashboard — a single-page HTML view rendered from a template.

The page is fully client-side: it logs in via POST /api/v1/admin/auth/login,
caches the token in localStorage, then drives the tenant-admin REST surface
(GET /admin/orders, /admin/orders/{id}/payments, POST /admin/orders/{id}/mark-paid)
via fetch. No new backend endpoints needed — the dashboard is just a
consumer of what the admin API already serves.

Same-origin with the API, so no CORS plumbing required. The path is in
GLOBAL_EXEMPT_PATHS so it loads without tenant resolution or customer
auth; the JS then makes calls under the current host so tenant-admin
endpoints see the right subdomain.
"""

from django.views.generic import TemplateView


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"
