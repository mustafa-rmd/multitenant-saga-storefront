// End-to-end smoke test that walks the full storefront flow from top to bottom.
//
// Tests run in file order and share state via module-level `state`. Each `test`
// makes the precondition explicit (skips with a log line when the prior step
// didn't seed what it needs) so the suite still produces a useful report even
// if the server is partially configured.
//
// Real-shape deviations from service-journey.md (verified against the live
// server):
//   * Health endpoint is /api/v1/health (not /).
//   * Address `label` is a choice field: "shipping" | "billing" | "both".
//   * GET /cart returns 404 cart_not_found when no active cart exists; the
//     cart is lazy-created by POST /cart/items, not by the GET.
//   * Cart `status` values are lowercase ("active", "checked_out", ...).
//   * Cart shape uses flat *Id fields: shippingAddressId,
//     billingAddressId, selectedPaymentMethodId.

import { beforeAll, describe, expect, test } from "bun:test";
import { SKUS } from "./fixtures";
import {
  ALICE,
  API,
  BOB,
  type Cart,
  call,
  firstErrorCode,
  type Order,
  type Product,
  resetCart,
  TENANT_A_HOST,
  TENANT_B_HOST,
  uuid,
} from "./helpers";

type State = {
  product?: Product;
  lowStockProduct?: Product;
  addressId?: string;
  paymentMethodId?: string;
  cart?: Cart;
  itemId?: string;
  orderId?: string;
  orderNumber?: number;
  idempotencyKey?: string;
};
const state: State = {};

const skipIf = (cond: boolean, why: string) => {
  if (cond) console.warn(`  SKIP: ${why}`);
  return cond;
};

beforeAll(async () => {
  // Other test files (cart-operations, coupons, idempotency, concurrency) can
  // leave residual state on Alice's cart — start the journey from a clean slate.
  await resetCart();
});

describe("Stage 0 — health & docs", () => {
  test("0.1 health probe (no auth, no tenant)", async () => {
    const r = await fetch(`${API}/health`);
    expect(r.status).toBe(200);
    const body = (await r.json()) as { data: { status: string } };
    expect(body.data.status).toBe("ok");
  });

  test("0.2 OpenAPI schema", async () => {
    const r = await fetch(`${API}/schema/`, { headers: { Host: TENANT_A_HOST } });
    expect(r.status).toBe(200);
    const ct = r.headers.get("content-type") ?? "";
    expect(ct.length).toBeGreaterThan(0);
  });
});

describe("Stage 1 — discover products", () => {
  test("1.1 list products for store-a", async () => {
    const r = await call<Product[]>("/products");
    expect(r.status).toBe(200);
    expect(Array.isArray(r.body.data)).toBe(true);
    expect(r.body.data!.length).toBeGreaterThan(0);

    // Pin to known SARs so the journey is deterministic regardless of seeded
    // currency variants (SA-USD-01 carries USD and would 409 on currency lock).
    const sarOnly = r.body.data!.filter((p) => p.currency === "SAR");
    const sorted = [...sarOnly].sort((a, b) => a.availableQuantity - b.availableQuantity);
    state.lowStockProduct = sorted.find((p) => p.sku !== SKUS.scarce) ?? sorted[0];
    // Pick the SAR widget specifically — it has the most stable stock for repeated runs.
    state.product = r.body.data!.find((p) => p.sku === SKUS.widget) ?? sorted[sorted.length - 1];
  });

  test("1.1b cross-tenant: store-b shows a different catalogue", async () => {
    const a = await call<Product[]>("/products");
    const b = await call<Product[]>("/products", { host: TENANT_B_HOST, customer: BOB });
    if (skipIf(b.status !== 200, `store-b returned ${b.status} — host header or seed missing`))
      return;

    const aSkus = new Set((a.body.data ?? []).map((p) => p.sku));
    const bSkus = new Set((b.body.data ?? []).map((p) => p.sku));
    const overlap = [...aSkus].filter((s) => bSkus.has(s));
    expect(overlap.length).toBe(0);
  });
});

describe("Stage 2 — customer profile data", () => {
  test("2.1 create shipping address (label is a choice: shipping|billing|both)", async () => {
    const r = await call<{ id: string }>(`/customers/${ALICE}/addresses`, {
      method: "POST",
      body: {
        label: "shipping",
        country: "SA",
        city: "Riyadh",
        street: "King Fahd Rd 123",
        postalCode: "12345",
        isDefault: true,
      },
    });
    expect([200, 201]).toContain(r.status);
    // The address endpoint uses a bare CreateAPIView and skips the envelope —
    // the id is at the top level rather than under `data`.
    const id = r.body.data?.id ?? (r.body as unknown as { id?: string }).id;
    expect(id).toBeTruthy();
    state.addressId = id!;
  });

  test("2.2 tokenize + save mock payment method", async () => {
    const r = await call<{ id: string }>(`/customers/${ALICE}/payment-methods`, {
      method: "POST",
      body: {
        gatewayName: "mock",
        token: "tok_visa_ok",
        brand: "visa",
        lastFour: "4242",
        isDefault: true,
      },
    });
    expect([200, 201]).toContain(r.status);
    expect(r.body.data?.id).toBeTruthy();
    state.paymentMethodId = r.body.data!.id;
  });
});

describe("Stage 3 — build the cart", () => {
  test("3.1 GET /cart on an empty profile may 404 (cart is lazy-created on POST /cart/items)", async () => {
    const r = await call<Cart>("/cart");
    // Either 200 (existing cart from a prior run) or 404 cart_not_found.
    expect([200, 404]).toContain(r.status);
    if (r.status === 200) {
      expect(r.body.data!.status).toBe("active");
      state.cart = r.body.data!;
    } else {
      expect(firstErrorCode(r)).toBe("cart_not_found");
    }
  });

  test("3.2 add first product (qty 1) — lazy-creates the cart on first call", async () => {
    if (skipIf(!state.product, "no product to add")) return;
    const r = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: state.product!.id, quantity: 1 },
    });
    expect(r.status).toBe(200);
    expect(r.body.data!.status).toBe("active");
    expect(r.body.data!.items.length).toBeGreaterThanOrEqual(1);
    const line = r.body.data!.items.find((i) => i.productId === state.product!.id)!;
    expect(line).toBeDefined();
    state.cart = r.body.data!;
    state.itemId = line.id;
  });

  test("3.3 re-add same product → idempotent line merge (qty bumps, no new line)", async () => {
    if (skipIf(!state.product || !state.itemId, "no product / item")) return;
    const beforeQty = state.cart!.items.find((i) => i.productId === state.product!.id)!.quantity;
    const beforeLines = state.cart!.items.length;

    const r = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: state.product!.id, quantity: 1 },
    });
    expect(r.status).toBe(200);
    expect(r.body.data!.items.length).toBe(beforeLines);
    const line = r.body.data!.items.find((i) => i.productId === state.product!.id)!;
    expect(line.quantity).toBe(beforeQty + 1);
    state.cart = r.body.data!;
  });

  test("3.4 insufficient stock → 409 insufficient_stock with {available, requested}", async () => {
    // Serializer caps quantity at 999, so we need a product whose stock is < 999
    // and we ask for stock + 1 (within the serializer cap, exceeds product stock).
    const target = state.lowStockProduct ?? state.product;
    if (skipIf(!target, "no product to test against")) return;
    const requested = Math.min(999, target!.stockQuantity + 1);
    if (skipIf(requested <= target!.availableQuantity, "product has too much stock to test"))
      return;

    const r = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: target!.id, quantity: requested },
    });
    expect(r.status).toBe(409);
    expect(firstErrorCode(r)).toBe("insufficient_stock");
    const meta = r.body.errors?.[0]?.meta ?? {};
    expect(meta).toHaveProperty("available");
    expect(meta).toHaveProperty("requested");
  });

  test("3.5 remove a line item, then re-add so checkout has something to charge", async () => {
    if (skipIf(!state.itemId, "no item to remove")) return;
    const del = await call<Cart>(`/cart/items/${state.itemId}`, { method: "DELETE" });
    expect([200, 204]).toContain(del.status);

    const re = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: state.product!.id, quantity: 1 },
    });
    expect(re.status).toBe(200);
    const line = re.body.data!.items.find((i) => i.productId === state.product!.id)!;
    expect(line).toBeDefined();
    state.cart = re.body.data!;
    state.itemId = line.id;
  });
});

describe("Stage 4 — coupons (negative paths only; WELCOME10 not seeded by default)", () => {
  test("applying a non-existent coupon → 404 coupon_not_found", async () => {
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: `DOES-NOT-EXIST-${uuid().slice(0, 8)}` },
    });
    expect(r.status).toBe(404);
    expect(firstErrorCode(r)).toBe("coupon_not_found");
  });
});

describe("Stage 5 — bind addresses and payment to the cart", () => {
  test("5.1 set shipping address (response uses flat shippingAddressId)", async () => {
    if (skipIf(!state.addressId, "no address id")) return;
    const r = await call<Cart>("/cart/shipping-address", {
      method: "PUT",
      body: { id: state.addressId },
    });
    expect(r.status).toBe(200);
    expect(r.body.data!.shippingAddressId).toBe(state.addressId!);
    state.cart = r.body.data!;
  });

  test("5.2 set billing address", async () => {
    if (skipIf(!state.addressId, "no address id")) return;
    const r = await call<Cart>("/cart/billing-address", {
      method: "PUT",
      body: { id: state.addressId },
    });
    expect(r.status).toBe(200);
    expect(r.body.data!.billingAddressId).toBe(state.addressId!);
    state.cart = r.body.data!;
  });

  test("5.3 set payment method", async () => {
    if (skipIf(!state.paymentMethodId, "no payment method id")) return;
    const r = await call<Cart>("/cart/payment-method", {
      method: "PUT",
      body: { id: state.paymentMethodId },
    });
    expect(r.status).toBe(200);
    expect(r.body.data!.selectedPaymentMethodId).toBe(state.paymentMethodId!);
    state.cart = r.body.data!;
  });

  test("5.4 bogus address UUID → 404 (tenant isolation through references)", async () => {
    const r = await call<Cart>("/cart/shipping-address", {
      method: "PUT",
      body: { id: uuid() },
    });
    expect(r.status).toBe(404);
  });
});

describe("Stage 6 — checkout", () => {
  test("6.5 missing Idempotency-Key → 400 idempotency_key_required", async () => {
    if (skipIf(!state.cart, "no cart")) return;
    const r = await call<{ order: Order }>("/cart/checkout", {
      method: "POST",
      body: { paymentMetadata: {} },
      headers: { "If-Match": String(state.cart!.version) },
    });
    expect(r.status).toBe(400);
    expect(firstErrorCode(r)).toBe("idempotency_key_required");
  });

  test("6.4 stale If-Match → 409 cart_version_conflict", async () => {
    if (skipIf(!state.cart, "no cart")) return;
    const fresh = await call<Cart>("/cart");
    if (skipIf(fresh.status !== 200, "cart fetch failed")) return;
    const stale = fresh.body.data!.version - 1;
    const r = await call<{ order: Order }>("/cart/checkout", {
      method: "POST",
      body: { paymentMetadata: {} },
      headers: { "Idempotency-Key": uuid(), "If-Match": String(stale) },
    });
    expect(r.status).toBe(409);
    expect(firstErrorCode(r)).toBe("cart_version_conflict");
  });

  test("6.2 successful checkout returns 201/202 with orderId + orderNumber", async () => {
    if (skipIf(!state.cart, "no cart")) return;
    const fresh = await call<Cart>("/cart");
    if (skipIf(fresh.status !== 200, "cart fetch failed")) return;
    const version = fresh.body.data!.version;
    const key = uuid();
    state.idempotencyKey = key;

    const r = await call<{
      orderId: string;
      orderNumber: number;
      status: string;
      paymentStatus: string;
    }>("/cart/checkout", {
      method: "POST",
      body: { paymentMetadata: {} },
      headers: { "Idempotency-Key": key, "If-Match": String(version) },
    });
    if (![200, 201, 202].includes(r.status)) {
      console.error("  checkout failed:", r.status, JSON.stringify(r.body));
    }
    expect([200, 201, 202]).toContain(r.status);
    expect(r.body.data?.orderId).toBeTruthy();
    expect(typeof r.body.data?.orderNumber).toBe("number");
    state.orderId = r.body.data!.orderId;
    state.orderNumber = r.body.data!.orderNumber;
  });

  test("6.3 idempotency replay returns the same orderId", async () => {
    if (skipIf(!state.orderId || !state.idempotencyKey, "no order to replay against")) return;
    const r = await call<{ orderId: string }>("/cart/checkout", {
      method: "POST",
      body: { paymentMetadata: {} },
      headers: { "Idempotency-Key": state.idempotencyKey! },
    });
    expect([200, 201, 202]).toContain(r.status);
    expect(r.body.data!.orderId).toBe(state.orderId!);
  });
});

describe("Stage 7 — post-checkout", () => {
  test("7.1 order detail includes line items and currency", async () => {
    if (skipIf(!state.orderId, "no order")) return;
    const r = await call<Order>(`/orders/${state.orderId!}`);
    expect(r.status).toBe(200);
    // RetrieveAPIView returns the model directly (no `data` envelope).
    const order = (r.body.data ?? (r.body as unknown as Order)) as Order;
    expect(order.id).toBe(state.orderId!);
    expect((order.items ?? []).length).toBeGreaterThan(0);
  });

  test("7.2 cross-customer access (Bob reading Alice's order) → 401 or 404", async () => {
    if (skipIf(!state.orderId, "no order")) return;
    const r = await call<Order>(`/orders/${state.orderId!}`, { customer: BOB });
    expect([401, 404]).toContain(r.status);
  });

  test("7.3 invoice (tolerates 404 if Celery worker hasn't rendered yet)", async () => {
    if (skipIf(!state.orderId, "no order")) return;
    const r = await call<{ invoiceNumber: number; pdfUrl: string; orderId: string }>(
      `/orders/${state.orderId!}/invoice`,
    );
    if (skipIf(r.status === 404, "invoice not yet generated (celery async)")) return;
    expect(r.status).toBe(200);
    expect(r.body.data!.invoiceNumber).toBeDefined();
    expect(r.body.data!.orderId).toBe(state.orderId!);
    // pdfUrl is populated by the same Celery task that creates the invoice
    // row, but the row may be visible while the upload is still in flight.
    // Tolerate empty here; tests-ts/invoices.test.ts polls and verifies
    // the URL serves a real PDF.
    if (r.body.data!.pdfUrl) {
      expect(r.body.data!.pdfUrl).toMatch(/^https?:\/\//);
    }
  });

  test("7.4 GET /cart after checkout: prior cart converted; new active cart is lazy on POST /cart/items", async () => {
    const r = await call<Cart>("/cart");
    expect([200, 404]).toContain(r.status);
    if (r.status === 200) {
      expect(r.body.data!.status).toBe("active");
      expect(r.body.data!.id).not.toBe(state.cart?.id);
    } else {
      expect(firstErrorCode(r)).toBe("cart_not_found");
    }
  });
});

describe("Stage 8 — webhooks (gateway-initiated)", () => {
  test("8.1 mock gateway accepts a payment.captured webhook", async () => {
    if (skipIf(!state.idempotencyKey, "no payment idempotency key")) return;
    const payload = {
      event: "payment.captured",
      payment: {
        idempotency_key: `${state.idempotencyKey}:auth`,
        gateway_transaction_id: "mock_txn_journey",
      },
    };
    const r = await fetch(`${API}/webhooks/payments/mock`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Host: TENANT_A_HOST },
      body: JSON.stringify(payload),
    });
    // Webhook handler shouldn't 5xx. 4xx is acceptable (payload may not match the expected shape).
    expect(r.status).toBeLessThan(500);
  });
});

describe("Stage 9 — tenant isolation cross-check", () => {
  test("Alice's UUID against store-b → 401 customer_not_found (or 404)", async () => {
    const r = await call("/products", { host: TENANT_B_HOST, customer: ALICE });
    expect([401, 404]).toContain(r.status);
    if (r.status === 401) {
      expect(["customer_not_found", "missing_customer_id", "unauthorized"]).toContain(
        firstErrorCode(r) ?? "",
      );
    }
  });
});
