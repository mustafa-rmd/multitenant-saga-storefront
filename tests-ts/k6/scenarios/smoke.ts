// Sanity-check the server is reachable and the storefront read path works.
// Runs 1 VU for 20s. If this fails, the heavier scenarios will fail too — fix
// here first.
//
// Run: k6 run tests-k6/scenarios/smoke.ts

import { check, sleep } from "k6";
import type { Options } from "k6/options";
import { getCart, getProducts } from "../lib/api.ts";
import { CUSTOMERS, type Product, TENANT_A } from "../lib/fixtures.ts";

export const options: Options = {
  vus: 1,
  duration: "20s",
  thresholds: {
    // Scope failure-rate to the products endpoint — /cart legitimately 404s
    // when the customer has no active cart, and k6 counts that as "failed".
    "http_req_failed{name:products_list}": ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const products = getProducts(TENANT_A.host, CUSTOMERS.alice);
  check(products, {
    "products status 200": (r) => r.status === 200,
    "products has data array": (r) => {
      const body = r.json() as { data?: Product[] } | null;
      return Array.isArray(body?.data);
    },
  });

  const cart = getCart(TENANT_A.host, CUSTOMERS.alice);
  check(cart, {
    // 200 if the customer has an active cart; 404 if not. Either is a
    // healthy server response — smoke is checking the endpoint is wired,
    // not that the customer has state.
    "cart 200 or 404": (r) => r.status === 200 || r.status === 404,
  });

  sleep(1);
}
