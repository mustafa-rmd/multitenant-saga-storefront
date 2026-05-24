"""
Minimum DB state for the application logic to function.

Creates exactly one Django superuser (platform admin). Nothing else.
Every subsequent piece of state — tenants, payment-gateway configs, tenant
admins, customers, products, coupons — is reachable through the admin
REST API once the platform admin is in place. Use the Postman collection
or curl to drive the rest.

Idempotent: re-running this updates the existing user's password if you
changed PLATFORM_ADMIN_PASSWORD, but doesn't create duplicates.

  Defaults (override via env):
    PLATFORM_ADMIN_EMAIL      = platform@acme.test
    PLATFORM_ADMIN_PASSWORD   = platform-pass
    PLATFORM_ADMIN_FIRST_NAME = Platform
    PLATFORM_ADMIN_LAST_NAME  = Admin

Run via:
    .\\.venv\\Scripts\\python.exe manage.py shell -c "exec(open('scripts/bootstrap.py').read())"

  …with $env:DATABASE_URL set to a role that has CREATE on auth_user
  (postgres or app_admin). app_user lacks it.

What this does NOT seed:
  * No tenants — POST /api/v1/admin/platform/tenants to create one.
    The endpoint provisions the per-tenant Postgres sequences
    (order_number_seq_<uuid>, invoice_number_seq_<uuid>) inside the
    same transaction, so you don't need to issue any raw SQL yourself.
  * No tenant admins — POST /api/v1/admin/platform/tenants/{id}/memberships
    with createUserIfMissing=true.
  * No payment-gateway configs — POST /api/v1/admin/payment-gateways.
  * No customers — POST /api/v1/admin/customers.
  * No products — POST /api/v1/admin/products.

This is the only DB-state-init script in this repo. The Bun test suite
under tests-ts/ currently hardcodes fixture UUIDs and will not pass
without provisioning those records via the admin API as a setup step.
"""

import os

from django.contrib.auth import get_user_model

User = get_user_model()


PLATFORM_ADMIN_EMAIL = os.environ.get("PLATFORM_ADMIN_EMAIL", "platform@acme.test")
PLATFORM_ADMIN_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "platform-pass")
PLATFORM_ADMIN_FIRST_NAME = os.environ.get("PLATFORM_ADMIN_FIRST_NAME", "Platform")
PLATFORM_ADMIN_LAST_NAME = os.environ.get("PLATFORM_ADMIN_LAST_NAME", "Admin")

user, created = User.objects.update_or_create(
    username=PLATFORM_ADMIN_EMAIL,
    defaults={
        "email": PLATFORM_ADMIN_EMAIL,
        "first_name": PLATFORM_ADMIN_FIRST_NAME,
        "last_name": PLATFORM_ADMIN_LAST_NAME,
        "is_active": True,
        "is_staff": True,
        "is_superuser": True,
    },
)
# Only re-hash the password when the existing one no longer matches —
# avoids needless writes on every re-run.
if created or not user.check_password(PLATFORM_ADMIN_PASSWORD):
    user.set_password(PLATFORM_ADMIN_PASSWORD)
    user.save(update_fields=["password"])

verb = "Created" if created else "Refreshed"
print(f"{verb} platform admin: {PLATFORM_ADMIN_EMAIL}")
print()
print("Next steps (all via the admin REST API):")
print("  1. POST /api/v1/admin/auth/login            -> get token")
print("  2. POST /api/v1/admin/platform/tenants      -> create your first tenant")
print("     (provisions order/invoice sequences in the same transaction)")
print("  3. POST /api/v1/admin/platform/tenants/{id}/memberships")
print("                                              -> assign a tenant admin")
print("  4. Log in as the tenant admin, then POST to:")
print("     /api/v1/admin/payment-gateways          -> gateway config")
print("     /api/v1/admin/products                  -> products")
print("     /api/v1/admin/customers                 -> customers")
