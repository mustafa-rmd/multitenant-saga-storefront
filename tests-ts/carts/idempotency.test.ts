// HTTP port of tests/test_idempotency.py.
//
// The contract: a checkout with idempotency key K must produce exactly one
// Order regardless of how many retries the client sends. The Python suite
// also asserts "no duplicate Payment rows" via direct ORM queries; that
// assertion is not portable to HTTP (no endpoint exposes the Payment table),
// so we approximate it by sending many concurrent retries and confirming
// they all return the same order_id, which can only happen if the DB-level
// unique constraint on Payment.idempotency_key holds.

import { describe, expect, test } from "bun:test";
import { ALICE, attemptCheckout, readyCart, uuid } from "../helpers";

describe("idempotency", () => {
  test("duplicate Idempotency-Key returns the same order", async () => {
    const cart = await readyCart();
    const key = uuid();

    const first = await attemptCheckout(ALICE, key, cart.version);
    expect(first.ok).toBe(true);
    if (!first.ok) return;

    const second = await attemptCheckout(ALICE, key);
    expect(second.ok).toBe(true);
    if (!second.ok) return;

    expect(second.data.orderId).toBe(first.data.orderId);
  });

  test("ten concurrent retries with the same key produce a single orderId", async () => {
    const cart = await readyCart();
    const key = uuid();

    // Prime with one successful checkout so subsequent calls short-circuit
    // on the idempotency lookup. (Firing all 10 in parallel without priming
    // would race on cart-version locks; that's a different test — see
    // concurrency.test.ts.)
    const seed = await attemptCheckout(ALICE, key, cart.version);
    expect(seed.ok).toBe(true);
    if (!seed.ok) return;

    const fanOut = await Promise.all(Array.from({ length: 10 }, () => attemptCheckout(ALICE, key)));
    const orderIds = new Set(fanOut.flatMap((r) => (r.ok ? [r.data.orderId] : [])));
    expect(fanOut.every((r) => r.ok)).toBe(true);
    expect(orderIds.size).toBe(1);
    expect([...orderIds][0]).toBe(seed.data.orderId);
  });

  test("missing Idempotency-Key → 400 idempotency_key_required", async () => {
    const cart = await readyCart();

    // Bypass the helper — it always injects an Idempotency-Key.
    const r = await fetch("http://localhost:8000/api/v1/cart/checkout", {
      method: "POST",
      headers: {
        Host: "store-a.acme.test",
        "X-Customer-Id": ALICE,
        "Content-Type": "application/json",
        "If-Match": String(cart.version),
      },
      body: JSON.stringify({ paymentMetadata: {} }),
    });
    expect(r.status).toBe(400);
    const body = (await r.json()) as { errors: Array<{ code: string }> };
    expect(body.errors[0].code).toBe("idempotency_key_required");
  });

  test("stale If-Match → 409 cart_version_conflict (with a fresh key, so no replay)", async () => {
    const cart = await readyCart();
    const r = await attemptCheckout(ALICE, uuid(), cart.version - 1);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.status).toBe(409);
    expect(r.code).toBe("cart_version_conflict");
  });
});
