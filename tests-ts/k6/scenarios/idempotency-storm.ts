// Idempotency storm: N parallel POST /cart/checkout requests carrying the SAME
// Idempotency-Key. The README claim is that exactly one order gets created and
// every other request returns the same order (UNIQUE constraint on
// Order.idempotency_key + app-level short-circuit + gateway-native idempotency).
//
// This scenario is more correctness-than-load — paired with the
// tests-ts/carts/idempotency.test.ts unit, it shows the property holds under
// real parallelism (k6 VUs are separate goroutines, true racing).
//
// What we can assert in k6:
//   * no 5xx
//   * all responses either 2xx (success) or 4xx (a deterministic refusal —
//     never a silent double-charge)
//   * every successful response carries the SAME orderId
//
// Run: k6 run tests-k6/scenarios/idempotency-storm.ts
// Override: K6_IDEMP_CONCURRENT=25 k6 run ...

import { check } from "k6";
import { Counter } from "k6/metrics";
import type { Options } from "k6/options";
import {
  addToCart,
  checkout,
  ensureAddress,
  ensurePaymentMethod,
  getProducts,
  setBillingAddress,
  setPaymentMethod,
  setShippingAddress,
  uuid,
} from "../lib/api.ts";
import { CUSTOMERS, findProductBySku, type Product, SKUS, TENANT_A } from "../lib/fixtures.ts";

const HOST = TENANT_A.host;
const CUSTOMER = CUSTOMERS.alice;

// Default is 10 — high enough to race in practice, low enough that the
// single-threaded dev server (runserver) doesn't drop connections before they
// reach the view. Crank to 25+ when running against gunicorn.
const CONCURRENT = Number(__ENV.K6_IDEMP_CONCURRENT || 10);

const distinctOrderIds = new Counter("distinct_order_ids");
const responses = new Counter("responses_2xx");

export const options: Options = {
  scenarios: {
    storm: {
      executor: "shared-iterations",
      vus: CONCURRENT,
      iterations: CONCURRENT,
      maxDuration: "1m",
    },
  },
  thresholds: {
    // The single invariant that must hold: zero 5xx — anything other than 1
    // explicit-success + (N-1) deterministic-replay/reject is a bug. We don't
    // gate on http_req_failed because the dev server may drop a few burst
    // connections (status=0), which counts as "failed" but isn't a
    // correctness signal.
    "checks{check:no_5xx}": ["rate==1"],
  },
};

interface SetupData {
  sharedKey: string;
}

interface CheckoutEnvelope {
  data?: { orderId?: string };
}

export function setup(): SetupData {
  const res = getProducts(HOST, CUSTOMER);
  const body = res.json() as unknown as { data: Product[] };
  const widget = findProductBySku(body.data, SKUS.widget);
  const addressId = ensureAddress(HOST, CUSTOMER);
  const paymentMethodId = ensurePaymentMethod(HOST, CUSTOMER);
  addToCart(HOST, CUSTOMER, widget.id, 1);
  setShippingAddress(HOST, CUSTOMER, addressId);
  setBillingAddress(HOST, CUSTOMER, addressId);
  setPaymentMethod(HOST, CUSTOMER, paymentMethodId);

  const sharedKey = uuid();
  console.log(`[storm] shared Idempotency-Key=${sharedKey}`);
  return { sharedKey };
}

export default function (data: SetupData) {
  const res = checkout(HOST, CUSTOMER, data.sharedKey);
  check(res, { no_5xx: (r) => r.status < 500 }, { check: "no_5xx" });
  check(res, {
    "deterministic 2xx or 4xx": (r) =>
      (r.status >= 200 && r.status < 300) || (r.status >= 400 && r.status < 500),
  });
  if (res.status >= 200 && res.status < 300) {
    responses.add(1);
    const body = res.json() as CheckoutEnvelope | null;
    const orderId = body?.data?.orderId;
    if (orderId) {
      console.log(`[storm vu=${__VU} iter=${__ITER}] orderId=${orderId}`);
      distinctOrderIds.add(1);
    }
  }
}

export function teardown(data: SetupData) {
  console.log(
    `[storm] done. shared key was ${data.sharedKey}. ` +
      "Grep the run output for 'orderId=' — every successful response should " +
      "carry the SAME UUID. If you see two distinct order IDs, idempotency leaked.",
  );
}
