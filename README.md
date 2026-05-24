# Multitenant Saga Storefront

Multi-tenant cart system POC. Tenant isolation at two layers, pluggable payments, a checkout saga with compensating actions, idempotency at every money-touching step, and an HTTP-level test suite.

---

## Quickstart

```powershell
# Bring up infra (postgres, redis, rabbitmq, stripe-mock, minio) in Docker.
make up

# Apply migrations + create one platform-admin Django superuser. Everything
# else — tenants, gateway configs, customers, products — is provisioned
# via the admin REST API once you can log in.
$env:DATABASE_URL = 'postgres://postgres:postgres@localhost:5432/acme_cart'
make migrate
make bootstrap   # platform@acme.test / platform-pass by default

# Start the app processes in three terminals (or use `make run-all`).
make runserver   # terminal 1
make worker      # terminal 2
make beat        # terminal 3
```

Now you have:

- **API:**         http://localhost:8000/api/v1/docs/  (Swagger UI)
- **RabbitMQ:**    http://localhost:15672  (acme / acme)
- **Stripe-mock:** http://localhost:12111
- **MinIO console:** http://localhost:9001  (minioadmin / minioadmin — invoice PDFs land in the `invoices` bucket)
- **Tenants** are accessed by subdomain: `store-a.acme.test` and `store-b.acme.test`. Add to your `/etc/hosts`:

  ```
  127.0.0.1  store-a.acme.test  store-b.acme.test
  ```

Hit the API as Alice (tenant A):

```bash
curl -H "X-Customer-Id: 00000000-0000-0000-0000-0000000000aa" \
     -H "Host: store-a.acme.test" \
     http://localhost:8000/api/v1/products
```

---

## Architecture

### Modular monolith

One Django project, several apps, each owning a slice of the domain:

```
config/                 settings, URLs, Celery wiring
apps/
  core/                 tenant context, middleware, base models, RLS migration, error handling
  tenants/              Tenant model and admin (the multi-tenancy root)
  catalog/              Product (sku, price, stock)
  customers/            Customer + Address (B2C and B2B)
  coupons/              Coupon with constraint validation
  payments/             PaymentMethod, gateway interface + adapters, PaymentService
  carts/                Cart, CartItem, AppliedCoupon, CartService
  orders/               Order, InventoryReservation, Invoice, CheckoutService (the saga)
tests-ts/               Bun/TypeScript suite (HTTP black-box): tenant isolation, concurrency, idempotency, coupons, journey smoke
```

App boundaries are clean enough to extract any single one into its own service later.

### Tenant isolation: belt + suspenders

Two independent layers, either of which would mostly work alone. Together, a bug in one cannot leak data.

**Layer 1 — Application (Django manager).** Every tenant-scoped model inherits `TenantScopedModel`, which exposes two managers:

- `objects` — auto-filtered by the current tenant from a `ContextVar`. With no tenant set, **returns empty** (fail closed).
- `all_objects` — escape hatch for system code (Celery, admin commands, webhook tenant resolution). Every use is greppable.

The tenant is set by `TenantResolverMiddleware` based on the request's subdomain.

**Layer 2 — Database (Postgres RLS).** Every tenant-scoped table has a row-level security policy:

```sql
CREATE POLICY tenant_isolation ON catalog_product
FOR ALL TO app_user
USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
```

`TenantDBSessionMiddleware` runs `SET LOCAL app.current_tenant = '...'` at the start of every request transaction. The application connects as `app_user` (RLS enforced); Celery and the Django admin connect as `app_admin` (`BYPASSRLS`) because they routinely operate across tenants.

The policies use `FORCE ROW LEVEL SECURITY`, which means even the table owner can't bypass them. If `app.current_tenant` is unset, the predicate compares against NULL and returns no rows — fail closed at this layer too.

**Cross-checks.** `CustomerAuthMiddleware` looks up the `Customer` via the RLS-scoped manager *after* `TenantDBSessionMiddleware` has set `app.current_tenant`. A customer ID from a different tenant returns 404, not the wrong row — the tenant guard is the database itself, not an application-level claim check.

### Authentication

Auth is a thin seam: the application reads `X-Customer-Id` from each request and resolves it to a `Customer` row. The header is trusted because the production path to it is trusted — an upstream identity-aware proxy (Cloudflare Access, an API gateway with JWT validation, an OIDC sidecar) authenticates the user, derives the customer ID, and strips forged client-supplied versions. Swap in any real identity layer and only `CustomerAuthMiddleware` changes.

In local dev / tests, set the header directly. `TESTING_DISABLE_AUTH=True` lets fixtures inject `request.user` instead.

### Cart model

One cart per customer, persistent, lazy-created on first item add. Status transitions:

```
            add item
   ┌─────────────────────────►  active
   │                              │
   │                              │ POST /cart/checkout
   │                              ▼
   │     reservation expires   checking_out
   │                              │
   │   ◄──────────────────────────┤  payment ok       payment fails
   │       (beat task)            │                   (compensating action)
   │                              ▼                   reverts to active
   │                          converted
   │
   └◄── 30 days idle ───────  abandoned
```

A `version` column increments on every mutation. Clients may opt into optimistic locking via `If-Match: <version>`. Even without it, mutations are serialized by `SELECT FOR UPDATE` on the cart row, so concurrent writes can't interleave. We do strict version checks only at checkout, where the cost of phantom changes matters.

### Currency

Per-tenant default currency, per-product currency, and a cart "locks in" its currency on first add. Cross-currency carts are rejected with `currency_mismatch`. Multi-currency carts (e.g. partial fiat + partial credits) are out of scope.

### Pricing

Price is snapshotted at add-time. If the merchant changes a price between cart-add and checkout, the customer pays the snapshot price. Merchant-side price-changed revalidation can be enforced at the cart layer later if needed.

### Checkout saga

`CheckoutService.checkout()` is a seven-phase saga. Each phase commits in its own transaction so a worker crash leaves recoverable state, not a half-charged customer.

| Phase | Action                                                       | On failure                                      |
|-------|--------------------------------------------------------------|-------------------------------------------------|
| 1     | `SELECT FOR UPDATE` cart, validate version, → `checking_out` | Domain error to caller                          |
| 2     | Validate preconditions (items, addresses, payment, coupons)  | Revert cart to `active`                         |
| 3     | Reserve stock (deterministic lock order to avoid deadlocks)  | Revert cart to `active`                         |
| 4     | Create `Order` + `OrderItem`s, bump coupon `uses_count`      | Release reservations, revert cart               |
| 5     | Authorize payment via gateway                                | Cancel order, release reservations, revert cart |
| 6     | Cart → `converted`, link order to cart and reservations      | (phase 5 succeeded, no rollback needed here)    |
| 7     | Sync gateways: capture now; async: wait for webhook          | Capture failure: leave order in `pending` for reconciliation |

Wrapping the saga in one big transaction would hold the cart row lock across the payment-gateway network call — the classic recipe for "all customers blocked on one slow gateway" outages. The saga trades atomicity for liveness, with explicit compensating actions per phase.

**Deterministic lock order.** When a cart has multiple products, we `SELECT FOR UPDATE` them sorted by UUID. Two concurrent checkouts containing the same set of products will acquire those product locks in the same order, eliminating one deadlock class.

**Reservation TTL.** Reservations expire after 15 minutes. A Celery beat task (`release_expired_reservations`) runs every 30 seconds and releases expired ones with `SELECT FOR UPDATE SKIP LOCKED` to never block live checkouts.

### Idempotency: three layers

Every checkout requires an `Idempotency-Key` header. We defend at three places against the "client retries because the network blinked" case:

1. **App short-circuit.** Before doing anything, `CheckoutService` looks up an `Order` by `idempotency_key`. If one exists, we return it. No DB writes, no gateway calls.

2. **DB unique constraint.** `Order.idempotency_key` and `Payment.idempotency_key` are both `UNIQUE`. If two concurrent retries somehow bypass the lookup, the second insert fails. Defense in depth.

3. **Gateway-native.** The same key (with a `:auth` suffix) is passed to the gateway as its own idempotency key. So even if our DB row got created but the gateway call was lost, the retry hits the gateway's idempotency cache and gets the same result.

The `Payment` row is persisted in `PENDING` status **before** the gateway call. If the gateway succeeds but our process dies before we can update the row, on retry the unique constraint refuses the new row, and a reconciliation job can detect rows with `PENDING` + no `gateway_transaction_id` to investigate.

### Payments: pluggable gateways

`PaymentGateway` is an ABC. Each implementation is a single file in `apps/payments/gateways/`:

```python
class PaymentGateway(ABC):
    name: str
    @abstractmethod
    def authorize(self, *, credentials, amount, currency, payment_method_token,
                  idempotency_key, metadata=None) -> PaymentIntent: ...
    @abstractmethod
    def capture(...) -> PaymentIntent: ...
    @abstractmethod
    def refund(...) -> PaymentIntent: ...
    @abstractmethod
    def tokenize(...) -> TokenizedPaymentMethod: ...
    @abstractmethod
    def verify_webhook(...) -> bool: ...
    @abstractmethod
    def parse_webhook(...) -> WebhookEvent: ...
    def supports_currency(self, currency) -> bool: return True
```

Implementations are stateless. Per-tenant credentials are passed in a `GatewayCredentials` dataclass on every call. The cart and order code never see gateway-specific objects — only normalized `PaymentIntent` and `WebhookEvent`. Adding a new gateway is one file plus one `register()` call.

Two gateways ship:

- **`MockPaymentGateway`** — first-class implementation. Outcomes are controllable from the metadata dict (`{"mock_outcome": "decline" | "requires_action" | "success"}`). Used in tests and local dev.
- **`StripeGateway`** — skeletal but real. Points at `stripe-mock` via `STRIPE_API_BASE`. Demonstrates the adapter pattern with a real SDK. Production-grade Stripe integration would need additional work (full event taxonomy, customer flows, automatic payment methods).

#### Payment testing strategy

`stripe-mock` is stateless and validates request shapes against Stripe's OpenAPI spec — used for integration tests that prove request construction. `MockPaymentGateway` exercises success/failure logic — used for behavioural tests.

### Webhooks

`POST /api/v1/webhooks/payments/{gateway_name}` is exempt from auth and tenant-subdomain resolution (gateways don't know our tenant subdomains). The tenant is resolved by looking up the `Payment` row by `gateway_transaction_id` — this is the one place we deliberately query with `Payment.all_objects` (the unscoped manager). Signature verification happens before any state mutation. Actual processing is deferred to a `TenantAwareTask` Celery worker.

### Reconciliation and dead-letter queue

The "outage = money lost" failure mode: a worker crashes between calling the gateway and persisting the result. The `Payment` row sits in `PENDING`, the gateway may have charged, and nothing in the request-response cycle will notice.

`reconcile_pending_payments` (Celery beat, every 5 minutes) sweeps `Payment` rows in `PENDING` older than 10 minutes:

- **Has `gateway_transaction_id`** — call `gateway.retrieve_payment()` and apply the returned status. If still PENDING (3DS / async authorize), leave it for the next pass.
- **No `gateway_transaction_id`** — can't safely retry the charge (the `payment_method_token` lives on the cart, not the payment); mark the payment FAILED, cancel the order, release reservations. The `Order.idempotency_key` UNIQUE constraint guarantees a client retry doesn't create a second order.

The cross-tenant outer query routes through the `admin` DB alias (BYPASSRLS); per-row work sets both the Python `tenant_context` ContextVar and the Postgres `app.current_tenant` GUC, so tenant-scoped helpers from the webhook path are reused as-is. `SELECT FOR UPDATE SKIP LOCKED` on the inner per-row lock keeps the sweep from blocking live checkouts.

**Dead-letter queue.** RabbitMQ `acme.default` declares `x-dead-letter-exchange='acme.dlx'`; `acme.dlq` is the terminal sink (no consumer). A `_DeadLetterMixin` catches `on_failure` after `max_retries` exhausts and publishes a JSON record (task, args, exception, timestamp) to the DLQ. Every task has explicit `max_retries` + exponential backoff + jitter; financial-path tasks retry 5x, cross-tenant sweepers retry 3x.

### B2B

`Customer` has `customer_type` (B2C/B2B), `tax_id`, and `company_name` fields. At checkout, `is_b2b` and `tax_id` are snapshotted onto the `Order`. Coupons can be restricted to B2C-only or B2B-only via the `customer_type_restriction` field.

**Purchase-order payment method.** B2B customers can save a `purchase_order` payment method (`POST /customers/{id}/payment-methods` with `methodType: "purchase_order"`, `paymentTerms: "net_30"`). At checkout, the saga's phase 5 branches: instead of calling a gateway, it records a `Payment` row in `INVOICE_PENDING`, snapshots `payment_terms` + `payment_due_date` + `po_number` onto the `Order`, commits stock immediately (ship-first model), and fires the invoice task. The order stays in `PENDING` until a tenant admin posts `POST /admin/orders/{id}/mark-paid` once the wire/cheque clears — that flips the payment to `CAPTURED` and the order to `PAID`. The endpoint is idempotent and refuses non-PO orders by inference (an already-PAID card order is a no-op).

The PO path is a second branch on the same saga, not a parallel flow — phases 1-4 and 6 are shared with the card path, so coupon validation, stock reservation, idempotency, and tenant scoping all behave identically. Reconciliation (`reconcile_pending_payments`) filters on `status=PENDING` only, so `INVOICE_PENDING` rows are naturally excluded. `cancel_order` knows to reverse committed reservations for PO orders (restores `stock_quantity`) since the ship-first commit happens at checkout, not at capture.

What's still out of scope: B2B-specific workflows beyond PO (formal purchase-order submission with PDF attachments, credit-limit enforcement, quote-to-order conversion, net-30 dunning).

### Per-tenant order numbering

Order numbers are sequential per tenant (not globally), and are pulled from per-tenant Postgres sequences:

```sql
CREATE SEQUENCE IF NOT EXISTS order_number_seq_<tenant_uuid_underscored> START 1000;
SELECT nextval('...');
```

The first checkout for a tenant pays a one-time DDL cost to create its sequence. Subsequent checkouts are a single `nextval()`. This is cheaper than an in-table counter (no row lock) and gives strict monotonicity within a tenant.

---

## API surface

All endpoints under `/api/v1`. Mutations return the full cart state in the response.

| Method | Path                                                        | Purpose                                  |
|--------|-------------------------------------------------------------|------------------------------------------|
| GET    | `/health`                                                   | Liveness check (no auth, no tenant)      |
| GET    | `/docs/`                                                    | Swagger UI                               |
| GET    | `/products`                                                 | List active products                     |
| POST   | `/customers/{id}/addresses`                                 | Add an address                           |
| POST   | `/customers/{id}/payment-methods`                           | Tokenize and save a payment method       |
| GET    | `/cart`                                                     | Get cart with totals                     |
| POST   | `/cart/items`                                               | Add an item (lazy-creates the cart)      |
| DELETE | `/cart/items/{item_id}`                                     | Remove an item                           |
| POST   | `/cart/coupons`                                             | Apply a coupon                           |
| DELETE | `/cart/coupons/{code}`                                      | Remove a coupon                          |
| PUT    | `/cart/shipping-address`                                    | Set shipping address                     |
| PUT    | `/cart/billing-address`                                     | Set billing address                     |
| PUT    | `/cart/payment-method`                                      | Select payment method                    |
| POST   | `/cart/checkout`                                            | Convert to order. Needs `Idempotency-Key`. |
| GET    | `/orders/{id}`                                              | Order detail                             |
| GET    | `/orders/{id}/invoice`                                      | Invoice (if generated)                   |
| POST   | `/webhooks/payments/{gateway}`                              | Gateway webhook ingestion                |
| POST   | `/admin/orders/{id}/mark-paid`                              | Tenant-admin: flip a PO order to PAID    |

### Admin API (separate auth rail)

The admin REST surface lives under `/api/v1/admin/` and uses a separate auth rail from the storefront — Django `User` + DRF token auth, never `X-Customer-Id`. Two audiences share the tree:

- **Tenant-admin** (per-tenant store operator). Endpoints live under the tenant's subdomain (`store-a.acme.test/api/v1/admin/...`). Tenant resolution + Postgres RLS still apply; a tenant-admin token issued for store-a returns `403` if used against store-b.
- **Platform-admin** (Zid staff). Endpoints live under the reserved `admin.acme.test` subdomain and route ORM calls through the `app_admin` DB alias (BYPASSRLS) so they can operate across tenants.

A user becomes a tenant-admin via a `TenantMembership(user, tenant, role)` row (one Django User can admin many tenants). A user becomes a platform-admin via `is_superuser=True` — no membership rows; superusers are also accepted on tenant-admin endpoints for support escalations.

Issue a token with `POST /api/v1/admin/auth/login`, then send it as `Authorization: Token <key>` on subsequent calls. `POST /api/v1/admin/auth/logout` deletes the token row.

| Method | Path                                                    | Audience       |
|--------|---------------------------------------------------------|----------------|
| POST   | `/admin/auth/login`                                     | Both (open)    |
| POST   | `/admin/auth/logout`                                    | Both           |
| GET    | `/admin/auth/me`                                        | Both           |
| GET / POST            | `/admin/products`                          | Tenant-admin   |
| GET / PATCH / DELETE  | `/admin/products/{id}`                     | Tenant-admin   |
| POST / DELETE         | `/admin/products/{id}/image`               | Tenant-admin (multipart upload to MinIO/S3) |
| GET / POST            | `/admin/coupons`                           | Tenant-admin   |
| GET / PATCH / DELETE  | `/admin/coupons/{id}`                      | Tenant-admin   |
| GET / POST            | `/admin/payment-gateways`                  | Tenant-admin   |
| GET / PATCH / DELETE  | `/admin/payment-gateways/{id}`             | Tenant-admin   |
| GET / POST            | `/admin/customers`                         | Tenant-admin   |
| GET / PATCH / DELETE  | `/admin/customers/{id}`                    | Tenant-admin   |
| GET                   | `/admin/orders`                            | Tenant-admin   |
| GET                   | `/admin/orders/{id}`                       | Tenant-admin   |
| GET / POST            | `/admin/platform/tenants`                  | Platform-admin |
| GET / PATCH           | `/admin/platform/tenants/{id}`             | Platform-admin |
| POST                  | `/admin/platform/tenants/{id}/memberships` | Platform-admin |
| DELETE                | `/admin/platform/memberships/{id}`         | Platform-admin |
| GET                   | `/admin/platform/customers?email=`         | Platform-admin |
| POST                  | `/admin/platform/ops/reconcile-payments`   | Platform-admin (force a reconciliation sweep) |

**Seeded admin credentials** (rotate or remove before any non-local deployment):

| Role           | Email                | Password         |
|----------------|----------------------|------------------|
| Platform admin | `platform@acme.test` | `platform-pass`  |
| Store-a admin  | `owner-a@store-a.test` | `owner-a-pass` |
| Store-b admin  | `owner-b@store-b.test` | `owner-b-pass` |

Two implementation choices worth noting:

- **`PlatformAdminAPIView` routes through the `admin` DB alias explicitly** (`using="admin"` on every viewset). BYPASSRLS would happily return cross-tenant rows from a misplaced `.objects.all()`; the explicit-alias convention makes the escape obvious at every call site.
- **`IsPlatformAdmin` / `IsTenantAdmin` start with `isinstance(request.user, User)`** before checking flags or memberships. The storefront's `MiddlewareCustomerAuthentication` sets `request.user` to a `Customer` instance; without the type check, a Customer-typed user with a stray truthy attribute would slip past DRF's stock `IsAuthenticated`.

#### Customer admin + the soft-delete / block primitive

Tenant admins can CRUD their tenant's Customer rows (`/admin/customers`), including a `POST` for B2B pre-provisioning. The `customerType=B2B` path requires `taxId` + `companyName` so any order snapshotted off the customer is invoiceable. Identity itself is still owned by the upstream IdP — `POST /admin/customers` creates the application record only; the customer can't sign in via `X-Customer-Id` until the IdP knows the email.

`DELETE /admin/customers/{id}` and `PATCH { "isActive": false }` are the same primitive: both flip `Customer.is_active=False`. `CustomerAuthMiddleware` then refuses that `X-Customer-Id` with `401 customer_not_found` (no enumeration). Reactivate by `PATCH { "isActive": true }`. Hard delete is impossible — `Order.customer` is `on_delete=PROTECT`.

`GET /admin/platform/customers?email=<substring>` is the platform-admin escape hatch for support tickets that span tenants. The `email` param is mandatory (no accidental table dumps), and every row carries `tenantSubdomain` so the support agent can hop into the right store.

### Response envelope

Success:

```json
{ "data": { ... }, "meta": { "request_id": "...", "version": "v1" } }
```

Errors:

```json
{
  "errors": [
    {"code": "insufficient_stock", "detail": "Only 1 available, 3 requested",
     "meta": {"product_id": "...", "available": 1, "requested": 3}}
  ],
  "meta": { "request_id": "...", "version": "v1" }
}
```

### Error code reference

| HTTP | Code                          | Meaning                                                |
|------|-------------------------------|--------------------------------------------------------|
| 400  | `tenant_required`             | No tenant subdomain in request                         |
| 400  | `idempotency_key_required`    | Checkout without `Idempotency-Key` header              |
| 401  | `missing_customer_id`         | Request lacks `X-Customer-Id` header                   |
| 401  | `customer_not_found`          | `X-Customer-Id` doesn't resolve in the current tenant  |
| 403  | `forbidden`                   | Authenticated but not allowed                          |
| 404  | `tenant_not_found`            | Subdomain doesn't resolve to a tenant                  |
| 404  | `cart_not_found`              | Cart doesn't exist or belongs to another customer      |
| 404  | `product_not_found`           | Product gone or inactive                               |
| 404  | `coupon_not_found`            | Coupon code doesn't exist on this tenant               |
| 409  | `currency_mismatch`           | Adding a product in a different currency than the cart |
| 409  | `insufficient_stock`          | Not enough stock to satisfy request                    |
| 409  | `cart_not_checkout_ready`     | Missing address, payment method, etc.                  |
| 409  | `cart_version_conflict`       | `If-Match` version didn't match current version        |
| 409  | `coupon_invalid`              | Coupon failed some other constraint                    |
| 409  | `coupon_already_applied`      | Coupon is already on this cart                         |
| 409  | `coupon_min_not_met`          | Cart subtotal below coupon's minimum                   |
| 409  | `coupon_country_restricted`   | Shipping country not in coupon's allowed list          |
| 409  | `coupon_exhausted`            | `max_uses` reached                                     |
| 409  | `gateway_unsupported_currency`| Selected gateway doesn't support cart currency         |
| 410  | `coupon_expired`              | Past `valid_until`                                     |
| 402  | `payment_failed`              | Gateway declined                                       |
| 422  | `validation_error`            | Request body schema violation; `source.pointer` for the field |

---

## Tests

The test suite is TypeScript and runs under Bun against a live Django server. It treats the system as a black box and exercises everything reachable through the HTTP surface.

```powershell
# Make sure the server (and infra) is up, then:
bun test --cwd tests-ts
```

Or via Make:

```powershell
make test
```

Files in `tests-ts/`:

- **`tenant-isolation.test.ts`** — cross-tenant catalogue separation, customer-scoped-per-tenant, indirect-reference isolation (Bob can't bind Alice's address), unknown-subdomain routing.
- **`cart-operations.test.ts`** — lazy creation, increment on re-add, currency lock-in + mismatch, insufficient stock, unknown product, version bumps, removal + currency unlock, totals math.
- **`idempotency.test.ts`** — duplicate-key replay returns the same order; 10 concurrent retries with the same key all converge on one `order_id`; stale `If-Match` + missing key both fail with the documented error codes.
- **`concurrency.test.ts`** — two customers race for `stock=1` over `Promise.all`; exactly one wins; the other gets `409 insufficient_stock`; product ends fully consumed.
- **`coupons.test.ts`** — every constraint dimension (min, expiry/not-yet-valid, max_uses, country, customer type, fixed-currency); percent + fixed discount math; cap-at-subtotal; re-apply / remove / not-found.
- **`journey.test.ts`** — full end-to-end smoke walk of the storefront flow (26 tests across Stages 0–9: tenant resolution → catalog → cart → checkout → invoice).

What is **not** covered by the TS suite (in-process invariants you can only check from inside Python):

- Manager-level fail-closed when `app.current_tenant` is unset.
- `Model.all_objects` (UnscopedManager) escape hatch.
- The `Tenant` root model being unscoped.
- Postgres RLS at the raw-SQL layer.

These are still worth verifying when touching `apps/core/models.py` or the RLS migration — easiest via `manage.py shell`.

---

## File map

The most important files to look at first:

1. **`apps/orders/services/checkout.py`** — the saga. If anything reads as "ah, that's the system", it's this file.
2. **`apps/core/middleware/`** — the three-stage middleware that drives tenant isolation.
3. **`apps/core/models.py`** — the base abstract model and the two-manager pattern.
4. **`apps/core/migrations/0001_enable_rls.py`** — the database-layer half of tenant isolation.
5. **`apps/payments/gateways/base.py`** — the seam that makes payments pluggable.
6. **`apps/carts/services.py`** — cart business logic, including the `_bump_and_return` pattern.
7. **`apps/payments/tasks.py`** — `reconcile_pending_payments`, the "outage = money lost" safety net. Pair-read with `apps/core/celery_helpers.py` for the DLQ wiring.
8. **`tests-ts/concurrency.test.ts`** — the proof that the row locks do what we think they do (two parallel HTTP checkouts for `stock=1`; exactly one wins).
