// HTTP port of tests/test_cart_operations.py.
//
// Tests the cart-mutation behaviour: lazy creation, quantity merge on re-add,
// currency lock-in + mismatch, insufficient stock, version bumps, removal,
// totals calculation.

import { beforeEach, describe, expect, test } from "bun:test";
import { SKUS } from "../fixtures";
import { type Cart, call, getProductBySku, resetCart } from "../helpers";

beforeEach(async () => {
  await resetCart();
});

describe("cart operations", () => {
  test("first POST /cart/items lazy-creates the cart", async () => {
    // After resetCart the cart is empty (or 404). The first item-add must
    // produce an ACTIVE cart with one line.
    const widget = await getProductBySku(SKUS.widget);
    const r = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 2 },
    });
    expect(r.status).toBe(200);
    const cart = r.body.data!;
    expect(cart.status).toBe("active");
    expect(cart.currency).toBe("SAR");
    expect(cart.items.length).toBe(1);
    expect(cart.items[0].quantity).toBe(2);
  });

  test("re-adding the same product increments quantity (line merge)", async () => {
    const widget = await getProductBySku(SKUS.widget);
    await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 1 },
    });
    const r = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 2 },
    });
    expect(r.status).toBe(200);
    expect(r.body.data!.items.length).toBe(1);
    expect(r.body.data!.items[0].quantity).toBe(3);
  });

  test("currency mismatch: adding a USD product after a SAR product → 409 currency_mismatch", async () => {
    const sar = await getProductBySku(SKUS.widget);
    const usd = await getProductBySku(SKUS.usd);

    const seed = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: sar.id, quantity: 1 },
    });
    expect(seed.status).toBe(200);
    expect(seed.body.data!.currency).toBe("SAR");

    const r = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: usd.id, quantity: 1 },
    });
    expect(r.status).toBe(409);
    expect(r.body.errors?.[0]?.code).toBe("currency_mismatch");
  });

  test("insufficient stock: requesting more than available → 409 insufficient_stock", async () => {
    const gizmo = await getProductBySku(SKUS.gizmo); // stock 5
    const r = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: gizmo.id, quantity: gizmo.stockQuantity + 1 },
    });
    expect(r.status).toBe(409);
    expect(r.body.errors?.[0]?.code).toBe("insufficient_stock");
    const meta = r.body.errors?.[0]?.meta ?? {};
    expect(meta).toHaveProperty("available");
    expect(meta).toHaveProperty("requested");
  });

  test("unknown product → 404 product_not_found", async () => {
    const r = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: crypto.randomUUID(), quantity: 1 },
    });
    expect(r.status).toBe(404);
    expect(r.body.errors?.[0]?.code).toBe("product_not_found");
  });

  test("version bumps on each mutation", async () => {
    const widget = await getProductBySku(SKUS.widget);
    const a = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 1 },
    });
    const v1 = a.body.data!.version;
    const b = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 2 },
    });
    expect(b.body.data!.version).toBeGreaterThan(v1);
  });

  test("remove the last item: cart becomes empty and currency unlocks", async () => {
    const widget = await getProductBySku(SKUS.widget);
    const a = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 1 },
    });
    expect(a.body.data!.currency).toBe("SAR");

    const itemId = a.body.data!.items[0].id;
    const del = await call<Cart>(`/cart/items/${itemId}`, { method: "DELETE" });
    expect([200, 204]).toContain(del.status);

    const after = await call<Cart>("/cart");
    expect(after.status).toBe(200);
    expect(after.body.data!.items.length).toBe(0);
    expect(after.body.data!.currency).toBe("");
  });

  test("totals reflect quantity × snapshot price", async () => {
    const widget = await getProductBySku(SKUS.widget); // price 99.99
    const r = await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 3 },
    });
    expect(r.status).toBe(200);
    const totals = r.body.data!.totals;
    expect(totals.subtotal).toBe("299.97");
    expect(totals.discountTotal).toBe("0.00");
    expect(totals.grandTotal).toBe("299.97");
    expect(totals.currency).toBe("SAR");
  });

  test("PUT /cart/shipping-address with unknown id → 404 address_not_found", async () => {
    // Seed an item so the cart exists.
    const widget = await getProductBySku(SKUS.widget);
    await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 1 },
    });

    const r = await call("/cart/shipping-address", {
      method: "PUT",
      body: { id: crypto.randomUUID() },
    });
    expect(r.status).toBe(404);
    expect(r.body.errors?.[0]?.code).toBe("address_not_found");
  });

  test("PUT /cart/billing-address with unknown id → 404 address_not_found", async () => {
    const widget = await getProductBySku(SKUS.widget);
    await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 1 },
    });

    const r = await call("/cart/billing-address", {
      method: "PUT",
      body: { id: crypto.randomUUID() },
    });
    expect(r.status).toBe(404);
    expect(r.body.errors?.[0]?.code).toBe("address_not_found");
  });

  test("PUT /cart/payment-method with unknown id → 404 payment_method_not_found", async () => {
    const widget = await getProductBySku(SKUS.widget);
    await call<Cart>("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 1 },
    });

    const r = await call("/cart/payment-method", {
      method: "PUT",
      body: { id: crypto.randomUUID() },
    });
    expect(r.status).toBe(404);
    expect(r.body.errors?.[0]?.code).toBe("payment_method_not_found");
  });
});
