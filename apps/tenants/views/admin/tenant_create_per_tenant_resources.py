"""Side-effect helper that provisions per-tenant Postgres sequences.

Every tenant needs its own `order_number_seq_*` and `invoice_number_seq_*`
because checkout pulls order numbers from a tenant-scoped sequence. The
platform-admin tenant-create endpoint calls this in the same transaction
as the Tenant insert, so a freshly-created tenant is always ready for
checkout traffic.

Runs on the `admin` DB alias because (a) creating sequences requires DDL
and (b) we already opened that connection for the tenant CRUD itself.
"""

from django.db import connections

from apps.iam.views._base import ADMIN_DB_ALIAS


def create_per_tenant_sequences(tenant_id) -> None:
    safe_id = str(tenant_id).replace("-", "_")
    with connections[ADMIN_DB_ALIAS].cursor() as cur:
        cur.execute(f"CREATE SEQUENCE IF NOT EXISTS order_number_seq_{safe_id} START 1000;")
        cur.execute(f"CREATE SEQUENCE IF NOT EXISTS invoice_number_seq_{safe_id} START 1000;")
        cur.execute(
            f"GRANT USAGE, SELECT, UPDATE ON SEQUENCE order_number_seq_{safe_id} TO app_user;"
        )
        cur.execute(
            f"GRANT USAGE, SELECT, UPDATE ON SEQUENCE invoice_number_seq_{safe_id} TO app_user;"
        )
