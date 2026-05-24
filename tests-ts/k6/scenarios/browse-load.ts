// Read-path load: ramp to 50 VUs all hitting GET /products.
// Tests the unauth'd-equivalent storefront catalogue under sustained read load.
// Exercises tenant resolution + RLS predicate + serializer hot path.
//
// Run: k6 run tests-k6/scenarios/browse-load.ts
// Override: K6_BROWSE_PEAK=100 k6 run ... (peak VU count)

import { check, sleep } from "k6";
import type { Options } from "k6/options";
import { getProducts } from "../lib/api.ts";
import { CUSTOMERS, type Product, TENANT_A, TENANT_B, type TenantRef } from "../lib/fixtures.ts";

const PEAK = Number(__ENV.K6_BROWSE_PEAK || 50);

export const options: Options = {
  stages: [
    { duration: "30s", target: Math.floor(PEAK / 2) },
    { duration: "1m", target: PEAK },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{name:products_list}": ["p(95)<400", "p(99)<1000"],
    checks: ["rate>0.99"],
  },
};

// Alternate between the two tenants so RLS + tenant resolution gets exercised
// in both directions. Even-VU → store-a (alice), odd-VU → store-b (bob).
// Customers MUST match their tenant — CustomerAuthMiddleware uses the
// tenant-scoped manager to resolve X-Customer-Id, so a cross-tenant header
// correctly returns 401 customer_not_found (tenant isolation working as
// designed — see tests-ts/tenant-isolation.test.ts).
interface TenantPick {
  tenant: TenantRef;
  customer: string;
}

const TENANT_CUSTOMER: TenantPick[] = [
  { tenant: TENANT_A, customer: CUSTOMERS.alice },
  { tenant: TENANT_B, customer: CUSTOMERS.bob },
];

export default function () {
  const pick = TENANT_CUSTOMER[__VU % TENANT_CUSTOMER.length];
  const res = getProducts(pick.tenant.host, pick.customer);
  check(res, {
    "status 200": (r) => r.status === 200,
    "non-empty catalogue": (r) => {
      const body = r.json() as { data?: Product[] } | null;
      return Array.isArray(body?.data) && body.data.length > 0;
    },
  });
  sleep(Math.random() * 0.5);
}
