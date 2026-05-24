# tests-ts

The project's full test suite. Black-box: drives the system through HTTP from
the outside using Bun's built-in test runner and `fetch`.

## Running

```powershell
# from the repo root, with the Django app running on :8000 and fixtures provisioned
bun test --cwd tests-ts
```

or

```powershell
cd tests-ts
bun test
```

`make test` is the canonical entry point.

## Prerequisites

1. **Infra up** — `docker compose -f docker-compose.infra.yml up -d`
2. **Migrations + platform admin** — `make bootstrap` (creates one Django superuser; nothing else)
3. **Django running** — `python manage.py runserver 0.0.0.0:8000`
4. **Fixtures provisioned via the admin API** — `make provision-fixtures`

The provisioner (`provision_fixtures.ts` in this directory) walks the admin REST API to create the same set the suite expects: tenants A/B, customers Alice + Charlie + Diana (B2B) on store-a and Bob on store-b, products including `SA-WIDGET-01` (stock 50), `SA-GIZMO-01` (stock 5), `SA-USD-01` (USD-denominated, for currency-mismatch tests), `SA-SCARCE-01` (stock 1, for the concurrency race), and the ten coupons listed in `coupons/storefront.test.ts`. Customer UUIDs are written to `tests-ts/.fixtures.json` (gitignored) and consumed by `tests-ts/fixtures.ts`.

## File map

| File | Mirrors |
|---|---|
| `tenant-isolation/*.test.ts`  | Cross-tenant catalog separation, customer scoping, indirect-reference isolation, unknown-subdomain routing |
| `carts/operations.test.ts`    | Lazy creation, line merge, currency lock-in, stock guard, version bump |
| `carts/idempotency.test.ts`   | 3-layer idempotency, replay returns same order, version conflict |
| `carts/concurrency.test.ts`   | Two customers race for stock=1 over `Promise.all` |
| `coupons/storefront.test.ts`  | Every constraint dimension + discount math |
| `coupons/admin.test.ts`       | Admin CRUD + validation |
| `orders/purchase-order.test.ts` | B2B PO checkout + admin mark-paid |
| `journey.test.ts`             | End-to-end smoke walk of the full storefront flow (tenant → catalog → cart → checkout → invoice) |
| `invoices.test.ts`            | Invoice PDF generation + storage |
| `admin/*.test.ts`             | Auth + throttling + cross-rail boundary |
| `platform/reconcile.test.ts`  | Reconcile trigger response shape (HTTP-reachable surface only) |
| `helpers.ts`                  | `call()` wrapper, types, `resetCart`, `readyCart`, `attemptCheckout` |

## Configuration

All overridable via env vars (defaults match the provisioner output):

| Var                  | Default                                  |
|----------------------|------------------------------------------|
| `ECOM_BASE_URL`      | `http://localhost:8000`                  |
| `ECOM_TENANT_A_HOST` | `store-a.acme.test`                      |
| `ECOM_TENANT_B_HOST` | `store-b.acme.test`                      |
| `ECOM_ALICE`         | (loaded from `tests-ts/.fixtures.json`)  |
| `ECOM_CHARLIE`       | (loaded from `tests-ts/.fixtures.json`)  |
| `ECOM_DIANA`         | (loaded from `tests-ts/.fixtures.json`)  |
| `ECOM_BOB`           | (loaded from `tests-ts/.fixtures.json`)  |

The suite uses an explicit `Host` header for tenant routing — you do **not** need to edit `C:\Windows\System32\drivers\etc\hosts`.

## State management

These tests share one DB across test files, with `beforeEach` / explicit `resetCart()` calls between mutations. Two products' state can drift across runs:

- **`SA-SCARCE-01`** is consumed by `concurrency.test.ts`. Once depleted the concurrency test SKIPs with a clear message; reset its stock with `PATCH /api/v1/admin/products/<id>` setting `stockQuantity: 1` (the provisioner won't lower an existing stock value).
- **`SA-WIDGET-01`** is consumed one unit at a time by every successful checkout. The provisioner gives it 50 units; suite is good for ~40 runs before another reset.

## Out-of-scope (not portable to HTTP)

Some invariants live entirely inside the Python process and can't be re-asserted from outside:

- Manager-level fail-closed when no tenant context is set
- `Model.all_objects` (UnscopedManager) escape hatch
- The `Tenant` root model not being itself tenant-scoped
- Postgres RLS blocking cross-tenant access at the raw-SQL layer
- Deep converge/cancel branches of `reconcile_pending_payments` (requires backdating `Payment.updated_at` and fabricating a `gateway_transaction_id` — neither reachable through the public API)

Verify these from `manage.py shell` when touching `apps/core/models.py` or the RLS migration. For the reconcile path specifically there's a checked-in script:

```powershell
$env:DATABASE_URL = "postgres://app_admin:app_admin_pass@localhost:5432/acme_cart"
.\.venv\Scripts\python.exe scripts/verify_reconcile.py
```

It creates two stuck Payment fixtures (one with `gateway_transaction_id`, one without), runs the sweep, asserts the converge / cancel outcomes, and cleans up — exits non-zero on any assertion failure. The HTTP shell (auth rail, response shape, conservation) is covered by `tests-ts/platform/reconcile.test.ts`.
