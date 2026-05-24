# Postman collection

Two files:

- `acme-cart.postman_collection.json` — the full API surface, grouped into folders:
  - **Storefront:** Health, Products, Customers, Cart, Orders, Webhooks.
  - **Admin:** Admin - Auth, Admin - Tenant, Admin - Platform.
- `acme-cart.postman_environment.json` — variables (`baseUrl`, `tenantHost`, `customerId`, `adminHost`, `adminToken`, etc.) for the local dev stack.

## Import

1. Postman → **Import** → drop both files in.
2. Top-right environment picker → pick **Acme Cart - Local**.

## Wire format: camelCase

All request bodies and response payloads use **camelCase** keys (`productId`, `postalCode`, `paymentMetadata`, `orderId`, …). `CamelCaseMiddleware` translates to/from the Python side's snake_case at the wire boundary, so you don't need to worry about Python conventions — just send and read camelCase.

Two exceptions:
- **Path params** stay as-is (`/customers/{customerId}/addresses` is just the URL shape).
- **Webhook payloads** (`/api/v1/webhooks/...`) are gateway-native and pass through untransformed. The seeded "Payment Webhook (Mock)" request mimics a Stripe-shaped body and stays snake_case where Stripe does.

## Postman setup gotcha — the `Host` header

Postman blocks `Host` from being sent by default ("restricted header"). The collection sets `Host: store-a.acme.test` so the tenant resolver gets the right subdomain. You have three ways to get a tenant resolved:

1. **Enable restricted headers in Postman** — Postman → **Settings (⚙)** → **General** → enable **"Allow sending restricted headers"**. The collection's `Host` header then reaches the server.
2. **Use the dev fallback** — `DEV_DEFAULT_TENANT_SUBDOMAIN=store-a` in your `.env` (already set if you copied `.env.example`) makes plain `localhost` resolve to `store-a`. You can ignore `Host` entirely, but you're locked to one tenant per server restart.
3. **Hosts-file entries (recommended for QA)** — add `127.0.0.1 store-a.acme.test store-b.acme.test acme.acme.test` to your hosts file (`C:\Windows\System32\drivers\etc\hosts` on Windows, `/etc/hosts` on macOS/Linux). Then point `baseUrl` directly at the tenant host, e.g. `http://store-a.acme.test:8000/api/v1`, and the `Host` header is implicit. Switching tenants becomes a one-line change to `baseUrl`, no Postman setting needed.

## Recommended run order

The requests auto-capture IDs from each response (via `pm.collectionVariables.set`) so subsequent requests find what they need. Run them in this order on a fresh DB:

1. **Health** → Health Check
2. **Products** → List Products *(captures `productId`)*
   - *Optional:* **List Products (filtered)** to exercise `search` / `currency` / `inStock` / `minPrice` / `maxPrice` query params, and **Get Product** to fetch the captured id.
3. **Customers** → Add Address *(captures `addressId`)*
   - *Optional:* List / Get / Update / Delete Address for full CRUD.
4. **Customers** → List Payment Gateways *(captures `gatewayName` from the tenant's default active gateway — the `mock` gateway is hidden in any environment with `PAYMENTS_ALLOW_MOCK_GATEWAY=False`)*
   - *Optional:* **Get Payment Gateway** to inspect one gateway's capabilities (`supportedCurrencies`, `tokenization`, `supports3ds`, `publicCredentials`) — what the storefront frontend uses to pick the right SDK + render the right form.
5. **Customers** → Add Payment Method *(captures `paymentMethodId`; uses the `gatewayName` from the previous step. Invalid names return 422 with a field-level error; valid-but-unconfigured gateways return 409 `gateway_not_configured`)*
   - *Optional:* List / Get / Set Default / Delete Payment Method.
6. **Cart** → Add Item *(captures `itemId`; the cart is implicit — no cart_id needed in any URL)*
   - *Optional:* **Update Item Quantity** for cart-edit flows, **Preview Coupon** to dry-run a code.
7. **Cart** → Set Shipping Address
8. **Cart** → Set Billing Address
9. **Cart** → Set Payment Method
10. **Cart** → Checkout *(captures `orderId`; needs `Idempotency-Key`)*
11. **Orders** → Get Order
12. **Orders** → Get Invoice *(captures `invoicePdfUrl`; may 404 for ~1s while Celery renders — re-send)*
13. **Orders** → Download Invoice PDF *(fetches the captured URL from MinIO/S3 directly; Postman previews the PDF inline)*
   - *Optional:* **List Orders** for paginated history, **Cancel Order** (only works on `pending` status).

Need to reset between runs? **Cart** → **Abandon Cart** empties everything and lets you start over.

The Coupon endpoints are optional — the seed script doesn't create a coupon, so you'll need to add one via Django admin or shell before *Apply Coupon* returns 200.

### B2B purchase-order flow

Storefront PO checkout reuses the same cart endpoints — only the `X-Customer-Id` and payment method differ. To exercise it:

1. Set `customerId = {{b2bCustomerId}}` in the environment (or override per-request). The seeded B2B customer is Diana (`00000000-0000-0000-0000-0000000000ad`).
2. **Customers** → **Add Address** (now scoped to Diana)
3. **Customers** → **Add Payment Method (Purchase Order)** *(captures `poPaymentMethodId`; restricted to B2B customers — sending it as Alice returns `403 forbidden`)*
4. **Cart** → **Add Item**, **Set Shipping Address**, **Set Billing Address**
5. **Cart** → **Set Payment Method** with `id = {{poPaymentMethodId}}`
6. **Cart** → **Checkout** — returns `202` with `paymentStatus: "invoice_pending"`. Order is `pending`, stock is committed, invoice PDF is generated immediately (with payment terms + due date in the footer).
7. **Admin - Tenant** → **Mark Order Paid (admin)** *(after logging in as the tenant admin)* — flips the order to `paid` and the payment to `captured`. Idempotent.

## Admin API (separate auth rail)

The admin folders use DRF token auth instead of `X-Customer-Id`, so they never share credentials with the storefront. Three folders:

- **Admin - Auth** — `Login (Tenant Admin)`, `Login (Platform Admin)`, `Me`, `Logout`. Login captures the issued token into `adminToken`; every other admin request sends it as `Authorization: Token {{adminToken}}`.
- **Admin - Tenant** — Per-tenant CRUD for products, coupons, payment gateway configs, **customers** (incl. block/unblock via `isActive`), and read-only orders (list / detail / **payment-attempt history** with gateway transaction ids for reconciliation). Lives under `tenantHost`, so Postgres RLS still scopes every query to the resolved tenant. A token issued for store-a returns `403` if used against store-b.
- **Admin - Platform** — Cross-tenant ops: tenant CRUD, membership assign/revoke, **cross-tenant customer search** (requires `?email=`). Lives under `adminHost` (default `admin.acme.test`) and routes through the `app_admin` DB connection. Requires `User.is_superuser=True`.

### Recommended run order (admin)

**Tenant-admin flow:**

1. **Admin - Auth** → **Login (Tenant Admin)** *(captures `adminToken`)*
2. **Admin - Tenant** → **List Products** / **Create Product** *(captures `adminProductId`)*
3. **Admin - Tenant** → **Update Product** / **Delete Product (soft)**
4. *(Coupons + gateway configs follow the same pattern: list / create / patch / delete.)*
5. **Admin - Tenant** → **List Orders (admin)** to see every order in the tenant (each row carries nested payments + invoice — scan for `paid` orders with empty `invoice.pdfUrl` to find stuck Celery tasks).
6. **Admin - Tenant** → **Get Order (admin)** for one order's full detail.
7. **Admin - Tenant** → **List Order Payments (admin)** for the dedicated payment-attempt history — use the `gatewayTransactionId` from the response to cross-check the gateway dashboard.
8. **Admin - Tenant** → **Mark Order Paid (admin)** — for PO orders whose invoice has cleared (see the B2B section above). Idempotent; a no-op on card orders.

**Platform-admin flow:**

1. **Admin - Auth** → **Login (Platform Admin)** *(captures `adminToken`)*
2. **Admin - Platform** → **List Tenants**
3. **Admin - Platform** → **Create Tenant** *(captures `newTenantId`, `newTenantSubdomain`)*
4. **Admin - Platform** → **Assign Tenant Admin (create user inline)** *(captures `newMembershipId`; the new admin can immediately log in via Admin - Auth → Login (Tenant Admin) with their new credentials and `ownerEmail` swapped)*
5. **Admin - Platform** → **Get Tenant** / **List Tenants** — the response now embeds `tenantAdmins: [...]` (membership id + user email + role) so you can see who admins each tenant in the same call.
6. **Admin - Platform** → **Revoke Membership** to clean up.

### Seeded admin credentials

| Variable          | Default value          |
|-------------------|------------------------|
| `platformEmail`   | `platform@acme.test`   |
| `platformPassword`| `platform-pass`        |
| `ownerEmail`      | `owner-a@store-a.test` |
| `ownerPassword`   | `owner-a-pass`         |

Store-b admin is `owner-b@store-b.test` / `owner-b-pass` — swap `ownerEmail`/`ownerPassword`/`tenantHost` together to operate that tenant.

### Cross-rail sanity checks

These should each fail with the documented status — quick proof that the two rails are isolated:

- Storefront request with `Authorization: Token {{adminToken}}` and no `X-Customer-Id` → `401`.
- Admin request with `X-Customer-Id: {{customerId}}` and no token → `401`.
- Tenant-admin token against `adminHost`'s **Admin - Platform** endpoints → `403`.
- Tenant-admin token issued on store-a, used against store-b → `403`.

## Switching tenants

Change the `tenantHost` and `customerId` env vars:

- Alice (store-a): `customerId = 00000000-0000-0000-0000-0000000000aa`, `tenantHost = store-a.acme.test`
- Bob (store-b):   `customerId = 00000000-0000-0000-0000-0000000000bb`, `tenantHost = store-b.acme.test`

Mixing them (Alice's ID against store-b's host, or vice versa) should return `401 customer_not_found` — a quick sanity check that tenant isolation is doing its job.
