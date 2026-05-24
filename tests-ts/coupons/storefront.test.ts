// Drives POST /cart/coupons against the coupons provisioned by
// tests-ts/provision_fixtures.ts:
//   WELCOME10  — 10% off, no constraints
//   MIN100K    — 10%, min_cart_subtotal=100000 (always fails)
//   EXPIRED    — valid_until in the past
//   NOTYET     — valid_from in the future
//   EXHAUSTED  — max_uses=1, uses_count=1
//   AEONLY     — allowed_countries=["AE"]
//   B2BONLY    — customer_type_restriction=B2B (Alice is B2C)
//   USDFIXED   — fixed-amount in USD (cart is SAR)
//   FLAT5      — fixed 5 SAR off
//   CAP100     — fixed 100000 SAR off (cap-at-subtotal test)

import { beforeEach, describe, expect, test } from "bun:test";
import { COUPONS, SKUS } from "../fixtures";
import {
  type Cart,
  call,
  ensureAddress,
  firstErrorCode,
  getProductBySku,
  resetCart,
} from "../helpers";

async function seedCart(opts: { quantity?: number; country?: string } = {}) {
  const quantity = opts.quantity ?? 1;
  const country = opts.country ?? "SA";
  await resetCart();
  const widget = await getProductBySku(SKUS.widget);
  await call<Cart>("/cart/items", {
    method: "POST",
    body: { productId: widget.id, quantity },
  });
  const addressId = await ensureAddress(undefined, undefined, country);
  await call("/cart/shipping-address", { method: "PUT", body: { id: addressId } });
}

beforeEach(async () => {
  await resetCart();
});

describe("coupons — happy path", () => {
  test("apply WELCOME10 → appliedCoupons populated, discountTotal > 0", async () => {
    await seedCart({ quantity: 3 });

    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.welcome10 },
    });
    expect(r.status).toBe(200);
    const cart = r.body.data!;
    expect(cart.appliedCoupons.map((c) => c.code)).toContain(COUPONS.welcome10);
    expect(parseFloat(cart.totals.discountTotal)).toBeGreaterThan(0);
  });

  test("percentage discount: 10% off a 299.97 subtotal = 30.00", async () => {
    await seedCart({ quantity: 3 }); // 3 * 99.99 = 299.97
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.welcome10 },
    });
    expect(r.status).toBe(200);
    const t = r.body.data!.totals;
    expect(t.subtotal).toBe("299.97");
    expect(t.discountTotal).toBe("30.00");
    expect(t.grandTotal).toBe("269.97");
  });

  test("fixed discount: FLAT5 takes 5.00 off", async () => {
    await seedCart({ quantity: 1 }); // 99.99
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.flat5 },
    });
    expect(r.status).toBe(200);
    expect(r.body.data!.totals.discountTotal).toBe("5.00");
    expect(r.body.data!.totals.grandTotal).toBe("94.99");
  });

  test("fixed discount > subtotal is capped at subtotal (grandTotal = 0)", async () => {
    await seedCart({ quantity: 1 }); // 99.99
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.cap100 },
    });
    expect(r.status).toBe(200);
    expect(r.body.data!.totals.discountTotal).toBe("99.99");
    expect(r.body.data!.totals.grandTotal).toBe("0.00");
  });

  test("re-applying the same coupon → 409 coupon_already_applied", async () => {
    await seedCart();
    const a = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.welcome10 },
    });
    expect(a.status).toBe(200);

    const b = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.welcome10 },
    });
    expect(b.status).toBe(409);
    expect(firstErrorCode(b)).toBe("coupon_already_applied");
  });

  test("DELETE /cart/coupons/{code} removes the coupon and zeroes the discount", async () => {
    await seedCart();
    await call<Cart>("/cart/coupons", { method: "POST", body: { code: COUPONS.welcome10 } });

    const del = await call<Cart>(`/cart/coupons/${COUPONS.welcome10}`, { method: "DELETE" });
    expect([200, 204]).toContain(del.status);

    const after = await call<Cart>("/cart");
    expect(after.body.data!.appliedCoupons.length).toBe(0);
    expect(after.body.data!.totals.discountTotal).toBe("0.00");
  });

  test("DELETE is idempotent: removing a coupon never applied → 200 unchanged, no version bump", async () => {
    await seedCart();
    const before = await call<Cart>("/cart");
    expect(before.status).toBe(200);
    const v0 = before.body.data!.version;

    // FLAT5 exists on this tenant but is not applied to the cart.
    const del = await call<Cart>(`/cart/coupons/${COUPONS.flat5}`, { method: "DELETE" });
    expect(del.status).toBe(200);
    expect(del.body.data!.appliedCoupons.length).toBe(0);
    expect(del.body.data!.version).toBe(v0);

    // Second DELETE is still a no-op success.
    const again = await call<Cart>(`/cart/coupons/${COUPONS.flat5}`, { method: "DELETE" });
    expect(again.status).toBe(200);
    expect(again.body.data!.version).toBe(v0);
  });

  test("DELETE with an unknown code → 404 coupon_not_found", async () => {
    await seedCart();
    const r = await call<Cart>(`/cart/coupons/NOPE-${crypto.randomUUID().slice(0, 6)}`, {
      method: "DELETE",
    });
    expect(r.status).toBe(404);
    expect(firstErrorCode(r)).toBe("coupon_not_found");
  });
});

describe("coupons — constraints", () => {
  test("min cart subtotal not met → coupon_min_not_met", async () => {
    await seedCart({ quantity: 1 });
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.min100k },
    });
    expect([409, 422]).toContain(r.status);
    expect(firstErrorCode(r)).toBe("coupon_min_not_met");
  });

  test("expired coupon → coupon_expired", async () => {
    await seedCart();
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.expired },
    });
    expect([409, 410, 422]).toContain(r.status);
    expect(firstErrorCode(r)).toBe("coupon_expired");
  });

  test("not yet valid → coupon_invalid", async () => {
    await seedCart();
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.notyet },
    });
    expect([409, 422]).toContain(r.status);
    expect(firstErrorCode(r)).toBe("coupon_invalid");
  });

  test("max_uses exhausted → coupon_exhausted", async () => {
    await seedCart();
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.exhausted },
    });
    expect([409, 422]).toContain(r.status);
    expect(firstErrorCode(r)).toBe("coupon_exhausted");
  });

  test("country restriction blocks SA address when coupon is AE-only", async () => {
    await seedCart({ country: "SA" });
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.aeOnly },
    });
    expect([409, 422]).toContain(r.status);
    expect(firstErrorCode(r)).toBe("coupon_country_restricted");
  });

  test("customer-type restriction blocks B2C customer for a B2B-only coupon", async () => {
    await seedCart();
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.b2bOnly },
    });
    expect([409, 422]).toContain(r.status);
    expect(firstErrorCode(r)).toBe("coupon_invalid");
  });

  test("fixed-amount coupon currency mismatch → coupon_invalid", async () => {
    await seedCart(); // SAR cart
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: COUPONS.usdFixed },
    });
    expect([409, 422]).toContain(r.status);
    expect(firstErrorCode(r)).toBe("coupon_invalid");
  });

  test("non-existent code → coupon_not_found", async () => {
    await seedCart();
    const r = await call<Cart>("/cart/coupons", {
      method: "POST",
      body: { code: `NOPE-${crypto.randomUUID().slice(0, 6)}` },
    });
    expect(r.status).toBe(404);
    expect(firstErrorCode(r)).toBe("coupon_not_found");
  });
});
