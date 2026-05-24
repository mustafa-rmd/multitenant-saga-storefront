from django.db import connection, transaction

from apps.core.tenant_context import get_current_tenant_id


class TenantDBSessionMiddleware:
    """
    Sets `app.current_tenant` on the Postgres connection so RLS policies fire.

    SET LOCAL is scoped to the current transaction, so we explicitly wrap
    `get_response` in `transaction.atomic()`. Without this wrapper, middleware
    code runs in autocommit mode (each cursor.execute is its own implicit
    transaction), and the SET LOCAL would not persist to downstream queries.
    ATOMIC_REQUESTS only wraps the view call itself, not the middleware chain.

    Wrapping here means the whole request (downstream middleware + view) shares
    one transaction with the GUC set, so RLS sees the right tenant everywhere.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant_id = get_current_tenant_id()
        # No-tenant short-circuit. Paths exempt from TenantResolverMiddleware
        # (health, /admin/platform/, /admin/auth/, webhooks) never get a
        # contextvar set, so we skip the SET LOCAL and avoid wrapping the
        # request in an unnecessary transaction. RLS won't return rows for
        # those paths anyway -- they either bypass app_user (admin endpoints)
        # or don't read tenant-scoped tables (health).
        if tenant_id is None:
            return self.get_response(request)

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL app.current_tenant = %s", [str(tenant_id)])
            return self.get_response(request)
