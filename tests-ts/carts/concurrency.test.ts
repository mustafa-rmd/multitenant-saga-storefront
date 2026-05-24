// HTTP port of tests/test_checkout_concurrency.py.
//
// Scenario: a product with `stock=1`, two distinct customers (Alice + Charlie,
// both on store-a), simultaneous checkout requests. Exactly one wins; the
// other fails with `insufficient_stock`. The Python original uses threads
// with a barrier; over HTTP we use Promise.all, which Bun fires onto separate
// TCP sockets — different DB connections from Django's perspective, which
// is what makes the SELECT FOR UPDATE in the saga meaningful.
//
// State note: the scarce product (SA-SCARCE-01) is seeded with stock=1. After
// a successful run its stock is 0 and subsequent runs SKIP unless you re-seed.

import { describe, expect, test } from "bun:test";
import { SKUS } from "../fixtures";
import { ALICE, attemptCheckout, CHARLIE, getProductBySku, readyCart, uuid } from "../helpers";

describe("checkout concurrency", () => {
  test("two customers race for stock=1; exactly one wins, one gets insufficient_stock", async () => {
    const scarce = await getProductBySku(SKUS.scarce);
    if (scarce.availableQuantity < 1) {
      console.warn(
        `  SKIP: SA-SCARCE-01 is depleted (available=${scarce.availableQuantity}). PATCH stockQuantity back to 1 via /admin/products to reset.`,
      );
      return;
    }

    const aliceCart = await readyCart({
      customer: ALICE,
      sku: SKUS.scarce,
      quantity: 1,
    });
    const charlieCart = await readyCart({
      customer: CHARLIE,
      sku: SKUS.scarce,
      quantity: 1,
    });

    const results = await Promise.all([
      attemptCheckout(ALICE, uuid(), aliceCart.version),
      attemptCheckout(CHARLIE, uuid(), charlieCart.version),
    ]);

    const wins = results.filter((r) => r.ok);
    const losses = results.filter((r) => !r.ok);

    expect(wins.length).toBe(1);
    expect(losses.length).toBe(1);

    const loss = losses[0];
    if (loss.ok) return; // type narrowing
    // The loser fails fast at stock validation (409 insufficient_stock).
    expect(loss.status).toBe(409);
    expect(loss.code).toBe("insufficient_stock");

    // After the race, the product is fully consumed: availableQuantity == 0.
    const after = await getProductBySku(SKUS.scarce);
    expect(after.availableQuantity).toBe(0);
  });
});
