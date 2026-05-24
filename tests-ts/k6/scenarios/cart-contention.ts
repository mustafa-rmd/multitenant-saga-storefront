// Cart row-lock contention: many VUs hammer the SAME customer's active cart.
// Each iteration adds an item and then deletes the line — net inventory impact
// per iteration is zero, so the test runs indefinitely without exhausting stock.
//
// Both endpoints take SELECT FOR UPDATE on the Cart row, so every iteration
// generates two writes that contend on the same row. The goal is to verify:
//   * no 5xx leaks out (lock waits resolve, no deadlock)
//   * the row-lock serialises mutations cleanly (no constraint violations)
//   * latency p95 stays bounded
//
// Run: k6 run tests-k6/scenarios/cart-contention.ts
// Override: K6_CART_VUS=40 k6 run ...

import { check, sleep } from "k6";
import http from "k6/http";
import type { Options } from "k6/options";
import { API, addToCart, getCart, getProducts, headers, type K6Response } from "../lib/api.ts";
import { CUSTOMERS, findProductBySku, type Product, SKUS, TENANT_A } from "../lib/fixtures.ts";

const HOST = TENANT_A.host;
const CUSTOMER = CUSTOMERS.alice; // one customer = one cart row = max contention
const VUS = Number(__ENV.K6_CART_VUS || 20);

export const options: Options = {
  scenarios: {
    contention: {
      executor: "constant-vus",
      vus: VUS,
      duration: "30s",
    },
  },
  thresholds: {
    // http_req_failed counts 404s as "failed" — but here a 404 on DELETE means
    // another VU got there first (expected, the `delete 2xx or 404` check
    // catches the real semantic). So the right gate is the explicit no_5xx
    // checks plus the latency budget, not http_req_failed.
    "http_req_duration{name:cart_add}": ["p(95)<2000"],
    "http_req_duration{name:cart_delete_item}": ["p(95)<2000"],
    checks: ["rate>0.95"],
  },
};

interface SetupData {
  widgetId: string;
}

interface CartItem {
  id: string;
  productId: string;
}

interface CartEnvelope {
  data?: { items?: CartItem[] };
}

export function setup(): SetupData {
  const res = getProducts(HOST, CUSTOMER);
  if (res.status !== 200) throw new Error(`setup failed: ${res.status}`);
  const body = res.json() as unknown as { data: Product[] };
  const widget = findProductBySku(body.data, SKUS.widget);
  return { widgetId: widget.id };
}

function deleteItem(itemId: string): K6Response {
  return http.del(`${API}/cart/items/${itemId}`, null, {
    headers: headers({ host: HOST, customer: CUSTOMER }),
    tags: { name: "cart_delete_item" },
  });
}

export default function (data: SetupData) {
  if (__ITER % 5 === 0) {
    const r = getCart(HOST, CUSTOMER);
    check(r, { "cart get 200": (x) => x.status === 200 });
    sleep(0.05);
    return;
  }

  const add = addToCart(HOST, CUSTOMER, data.widgetId, 1);
  const addOk = check(add, {
    "add 2xx": (x) => x.status >= 200 && x.status < 300,
    "no 5xx": (x) => x.status < 500,
  });
  if (!addOk) {
    sleep(0.05);
    return;
  }

  const cart = add.json() as CartEnvelope | null;
  const myLine = cart?.data?.items?.find((it) => it.productId === data.widgetId);
  if (myLine) {
    const del = deleteItem(myLine.id);
    check(del, {
      "delete 2xx or 404": (x) => (x.status >= 200 && x.status < 300) || x.status === 404,
      "no 5xx on delete": (x) => x.status < 500,
    });
  }

  sleep(0.05);
}
