"""
Enable Postgres Row-Level Security on every tenant-scoped table.

Runs LAST, after all other app migrations have created the tables.
The list of tables is maintained manually -- when adding a new
tenant-scoped model, add its table here.

Why this lives in `core` and not `tenants`: it depends on all other
apps' tables existing, so it must be ordered last via the `dependencies`
list below.

What this does:
1. Enables RLS on each table
2. FORCEs RLS so even the table owner can't bypass it
3. Creates a policy `tenant_isolation` that filters by app.current_tenant
4. The policy applies only to role `app_user`; `app_admin` has BYPASSRLS

If `app.current_tenant` is not set (NULL), the predicate `tenant_id =
NULL::uuid` is FALSE for every row, so the table appears empty. Fail closed.
"""
from django.db import migrations


# Every TenantScopedModel's db_table goes here.
# Order doesn't matter for the SQL, but we group by app for readability.
TENANT_TABLES = [
    # carts
    "carts_cart",
    "carts_cartitem",
    "carts_appliedcoupon",
    # catalog
    "catalog_product",
    # customers
    "customers_customer",
    "customers_address",
    # coupons
    "coupons_coupon",
    # orders
    "orders_order",
    "orders_orderitem",
    "orders_inventoryreservation",
    "orders_invoice",
    # payments
    "payments_paymentgatewayconfig",
    "payments_paymentmethod",
    "payments_payment",
]


def enable_rls(apps, schema_editor):
    cursor = schema_editor.connection.cursor()
    for table in TENANT_TABLES:
        cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        cursor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        cursor.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            FOR ALL
            TO app_user
            USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
        """)


def disable_rls(apps, schema_editor):
    cursor = schema_editor.connection.cursor()
    for table in TENANT_TABLES:
        cursor.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    """Runs last, after all tenant-scoped tables are created."""

    # This migration must run AFTER all the tenant-scoped tables exist.
    # When adding a new tenant-scoped app, add its initial migration here.
    dependencies = [
        ("tenants", "0001_initial"),
        ("catalog", "0001_initial"),
        ("customers", "0001_initial"),
        ("coupons", "0001_initial"),
        ("payments", "0001_initial"),
        ("carts", "0001_initial"),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, reverse_code=disable_rls),
    ]
