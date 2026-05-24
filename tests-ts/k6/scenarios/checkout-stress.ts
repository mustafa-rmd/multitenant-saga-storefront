// Full-journey stress: VUs ramp through add-item → bind-shipping/billing/payment
// → checkout. Each iteration completes a checkout against the mock gateway and
// the cart auto-resets (the next add creates a new active cart).
//
// Stresses the saga end-to-end: tenant resolution, RLS, cart row-lock, stock
// reservation, idempotency lookup, gateway capture, invoice task enqueue.
//
// IMPORTANT — VUs ≤ customers. The default PEAK is 3 because the fixtures
// provision 3 customers on store-a (alice/charlie/diana). Each VU pins to one
// customer; if multiple VUs share a customer, they race on the same cart row
// and the checkout-time optimistic version-lock rejects most attempts with
// cart_version_conflict — that's by design (covered by cart-contention.ts +
// tests-ts/carts/concurrency.test.ts), not what this scenario measures.
//
// To raise PEAK, first provision more customers via the admin REST API.
//
// Run: k6 run tests-k6/scenarios/checkout-stress.ts
// Override: K6_CHECKOUT_PEAK=3 k6 run ...

import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";
import type { Options } from "k6/options";
import {
  addToCart,
  type CustomerSetup,
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

const TENANT_A_CUSTOMERS: string[] = [CUSTOMERS.alice, CUSTOMERS.charlie, CUSTOMERS.diana];

// Default PEAK = customer count so each VU pins to a unique customer (avoiding
// same-cart contention that would dominate the failure mode — see header).
const PEAK = Number(__ENV.K6_CHECKOUT_PEAK || TENANT_A_CUSTOMERS.length);

const checkoutLatency = new Trend("checkout_latency_ms", true);
const checkoutOk = new Counter("checkout_ok_total");
const checkoutFail = new Counter("checkout_fail_total");

export const options: Options = {
  stages: [
    { duration: "30s", target: Math.max(1, Math.floor(PEAK / 3)) },
    { duration: "1m", target: PEAK },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.05"],
    "http_req_duration{name:checkout}": ["p(95)<3000", "p(99)<5000"],
    "checks{check_group:checkout}": ["rate>0.90"],
  },
};

interface SetupData {
  widgetId: string;
  perCustomer: Record<string, CustomerSetup>;
}

interface CheckoutEnvelope {
  data?: { orderId?: string };
}

export function setup(): SetupData {
  const res = getProducts(HOST, TENANT_A_CUSTOMERS[0]);
  if (res.status !== 200) {
    throw new Error(`setup: GET /products failed status=${res.status}`);
  }
  const body = res.json() as unknown as { data: Product[] };
  const widget = findProductBySku(body.data, SKUS.widget);

  const perCustomer: Record<string, CustomerSetup> = {};
  for (const c of TENANT_A_CUSTOMERS) {
    perCustomer[c] = {
      addressId: ensureAddress(HOST, c),
      paymentMethodId: ensurePaymentMethod(HOST, c),
    };
  }

  return { widgetId: widget.id, perCustomer };
}

export default function (data: SetupData) {
  const customer = TENANT_A_CUSTOMERS[__VU % TENANT_A_CUSTOMERS.length];
  const { addressId, paymentMethodId } = data.perCustomer[customer];

  // 1. Add to cart (creates a fresh active cart if the previous one converted)
  const add = addToCart(HOST, customer, data.widgetId, 1);
  const addOk = check(
    add,
    { "add 2xx": (r) => r.status >= 200 && r.status < 300 },
    { check_group: "add" },
  );
  if (!addOk) {
    sleep(0.5);
    return;
  }

  // 2. Bind shipping / billing / payment to the now-existing active cart
  setShippingAddress(HOST, customer, addressId);
  setBillingAddress(HOST, customer, addressId);
  setPaymentMethod(HOST, customer, paymentMethodId);

  // 3. Checkout — fresh idempotency key per iteration
  const idemKey = uuid();
  const t0 = Date.now();
  const res = checkout(HOST, customer, idemKey);
  checkoutLatency.add(Date.now() - t0);

  const ok = check(
    res,
    {
      "checkout 2xx": (r) => r.status >= 200 && r.status < 300,
      "has orderId": (r) => {
        const body = r.json() as CheckoutEnvelope | null;
        return typeof body?.data?.orderId === "string";
      },
    },
    { check_group: "checkout" },
  );
  if (ok) {
    checkoutOk.add(1);
  } else {
    checkoutFail.add(1);
  }

  sleep(Math.random() * 0.5);
}
