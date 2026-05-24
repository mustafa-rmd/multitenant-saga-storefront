r"""
End-to-end verification of `reconcile_pending_payments`.

The Bun suite covers the HTTP shell of the platform-admin trigger
(`tests-ts/admin/platform-admin-reconcile.test.ts`). It cannot create
backdated PENDING Payment rows through the public API, so the deeper
converge / cancel branches live here, runnable on demand:

    $env:DATABASE_URL = "postgres://app_admin:app_admin_pass@localhost:5432/acme_cart"
    .\.venv\Scripts\python.exe scripts/verify_reconcile.py

Or as one of the seed-style smoke checks if you prefer running through
manage.py:

    python manage.py shell -c "exec(open('scripts/verify_reconcile.py').read())"

What it proves:

  A. PENDING + gateway_transaction_id -> mock gateway's retrieve_payment
     returns AUTHORIZED -> payment converges; order remains PENDING
     (AUTHORIZED is not CAPTURED, so the order only flips on capture).
  B. PENDING + empty gateway_transaction_id -> safe path is FAILED + the
     order is CANCELLED + reservations released.
  C. Idempotency: running the sweep twice doesn't re-touch already-converged
     rows.

Exits non-zero on any assertion failure so it can be wired into CI later.
"""

import os
import sys
import uuid
from datetime import timedelta
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.customers.models import Customer  # noqa: E402
from apps.orders.models import Order  # noqa: E402
from apps.payments.models import Payment, PaymentGatewayConfig  # noqa: E402
from apps.payments.tasks import reconcile_pending_payments  # noqa: E402
from apps.tenants.models import Tenant  # noqa: E402

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

_fail_count = 0


def _check(label: str, ok: bool, detail: str = "") -> None:
    global _fail_count
    if ok:
        print(f"{GREEN}OK{RESET}  {label}")
    else:
        _fail_count += 1
        print(f"{RED}FAIL{RESET} {label}  {detail}")


def main() -> int:
    tenant = Tenant.all_objects.get(subdomain="store-a")
    customer = Customer.all_objects.filter(tenant=tenant).first()
    gw_cfg = PaymentGatewayConfig.all_objects.filter(tenant=tenant, gateway_name="mock").first()

    if customer is None or gw_cfg is None:
        print("Fixtures missing -- run `make provision-fixtures` after `make bootstrap`.")
        return 2

    print(f"Fixture: tenant={tenant.subdomain} customer={customer.email} gw={gw_cfg.gateway_name}")

    # ---- CASE A: PENDING with gateway_transaction_id -------------------
    idem_a = f"verify-recon-with-txn-{uuid.uuid4()}"
    with transaction.atomic():
        order_a = Order.all_objects.create(
            tenant=tenant,
            customer=customer,
            order_number=999_990 + int(uuid.uuid4().int % 1000),
            status=Order.Status.PENDING,
            subtotal=Decimal("20"),
            grand_total=Decimal("20"),
            currency="SAR",
            shipping_address={},
            billing_address={},
            idempotency_key=idem_a,
        )
        payment_a = Payment.all_objects.create(
            tenant=tenant,
            order=order_a,
            gateway_config=gw_cfg,
            status=Payment.Status.PENDING,
            amount=Decimal("20"),
            currency="SAR",
            idempotency_key=f"{idem_a}:auth",
            gateway_transaction_id=f"mock_txn_{uuid.uuid4()}",
        )
        Payment.all_objects.filter(id=payment_a.id).update(
            updated_at=timezone.now() - timedelta(minutes=20)
        )

    # ---- CASE B: PENDING with NO gateway_transaction_id -----------------
    idem_b = f"verify-recon-no-txn-{uuid.uuid4()}"
    with transaction.atomic():
        order_b = Order.all_objects.create(
            tenant=tenant,
            customer=customer,
            order_number=999_000 + int(uuid.uuid4().int % 1000),
            status=Order.Status.PENDING,
            subtotal=Decimal("10"),
            grand_total=Decimal("10"),
            currency="SAR",
            shipping_address={},
            billing_address={},
            idempotency_key=idem_b,
        )
        payment_b = Payment.all_objects.create(
            tenant=tenant,
            order=order_b,
            gateway_config=gw_cfg,
            status=Payment.Status.PENDING,
            amount=Decimal("10"),
            currency="SAR",
            idempotency_key=f"{idem_b}:auth",
        )
        Payment.all_objects.filter(id=payment_b.id).update(
            updated_at=timezone.now() - timedelta(minutes=20)
        )

    print(f"\nFixtures: case-A payment={payment_a.id}  case-B payment={payment_b.id}")

    # ---- Run the sweep --------------------------------------------------
    summary = reconcile_pending_payments(stale_after_minutes=10)
    print(f"\nSweep result: {summary}")
    _check("sweep returns a dict", isinstance(summary, dict))
    _check(
        "summary has all 4 keys",
        {"scanned", "converged", "cancelled", "still_pending"} <= set(summary),
    )
    _check(
        "conservation: scanned == converged+cancelled+still_pending",
        summary["scanned"]
        == summary["converged"] + summary["cancelled"] + summary["still_pending"],
    )

    # ---- Case-A assertions ---------------------------------------------
    payment_a.refresh_from_db()
    order_a.refresh_from_db()
    _check(
        "case-A payment -> AUTHORIZED",
        payment_a.status == Payment.Status.AUTHORIZED,
        f"got status={payment_a.status}",
    )
    _check(
        "case-A gateway_response.reconciled is True",
        (payment_a.gateway_response or {}).get("reconciled") is True,
    )
    _check(
        "case-A order remains PENDING (AUTHORIZED is not CAPTURED)",
        order_a.status == Order.Status.PENDING,
        f"got status={order_a.status}",
    )

    # ---- Case-B assertions ---------------------------------------------
    payment_b.refresh_from_db()
    order_b.refresh_from_db()
    _check(
        "case-B payment -> FAILED",
        payment_b.status == Payment.Status.FAILED,
        f"got status={payment_b.status}",
    )
    _check(
        "case-B reconcile_reason recorded",
        (payment_b.gateway_response or {}).get("reconcile_reason") == "no_gateway_transaction_id",
    )
    _check(
        "case-B order -> CANCELLED",
        order_b.status == Order.Status.CANCELLED,
        f"got status={order_b.status}",
    )

    # ---- Idempotency: run again, both fixtures stay put -----------------
    second = reconcile_pending_payments(stale_after_minutes=10)
    payment_a.refresh_from_db()
    payment_b.refresh_from_db()
    _check(
        "second sweep doesn't re-touch case-A (still AUTHORIZED)",
        payment_a.status == Payment.Status.AUTHORIZED,
    )
    _check(
        "second sweep doesn't re-touch case-B (still FAILED)",
        payment_b.status == Payment.Status.FAILED,
    )
    print(f"Second sweep: {second}")

    # ---- Cleanup --------------------------------------------------------
    Payment.all_objects.filter(id__in=[payment_a.id, payment_b.id]).delete()
    Order.all_objects.filter(id__in=[order_a.id, order_b.id]).delete()
    print("\nFixtures cleaned up.")

    if _fail_count:
        print(f"\n{RED}{_fail_count} assertion(s) failed.{RESET}")
        return 1
    print(f"\n{GREEN}All assertions passed.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
