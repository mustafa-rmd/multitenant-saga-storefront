#!/usr/bin/env bun
/**
 * Provision the test-fixture state via the admin REST API.
 *
 * Walks the admin API to create the two demo tenants, three admin
 * accounts, the per-tenant gateway configs, customers (Alice / Charlie
 * / Diana / Bob), products, and coupons that the Bun test suite expects.
 *
 * Captures the dynamic IDs (customer UUIDs primarily; tenant IDs as a
 * bonus) into ./.fixtures.json. ./fixtures.ts loads from that file so
 * the test suite no longer hardcodes UUIDs.
 *
 * Idempotent. Each ensure* helper does a "look up first, create if
 * missing" so re-running on an already-provisioned DB is safe.
 *
 * Requires the platform admin to already exist (i.e. `make bootstrap`
 * was run, or `make reset-full`). The server must be up.
 *
 *   Usage:
 *     bun run provision         # from tests-ts/
 *     # or
 *     make provision-fixtures   # from repo root
 */

import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE = process.env.ECOM_BASE_URL ?? "http://localhost:8000";
const API = `${BASE}/api/v1`;
const ADMIN_HOST = process.env.ECOM_ADMIN_HOST ?? "admin.acme.test";

const PLATFORM_EMAIL = process.env.PLATFORM_ADMIN_EMAIL ?? "platform@acme.test";
const PLATFORM_PASSWORD = process.env.PLATFORM_ADMIN_PASSWORD ?? "platform-pass";

const TENANT_A = { name: "Store A", subdomain: "store-a", currency: "SAR" };
const TENANT_B = { name: "Store B", subdomain: "store-b", currency: "USD" };
const TENANT_A_HOST = `${TENANT_A.subdomain}.acme.test`;
const TENANT_B_HOST = `${TENANT_B.subdomain}.acme.test`;

const OWNER_A = { email: "owner-a@store-a.test", password: "owner-a-pass" };
const OWNER_B = { email: "owner-b@store-b.test", password: "owner-b-pass" };

const FIXTURES_PATH = resolve(import.meta.dir, ".fixtures.json");

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------
type Envelope<T> = {
  data?: T;
  errors?: Array<{ code: string; detail?: string }>;
  meta?: unknown;
};

async function http<T = unknown>(
  path: string,
  opts: {
    method?: string;
    host?: string;
    token?: string;
    body?: unknown;
  } = {},
): Promise<{ status: number; body: Envelope<T> & Record<string, unknown> }> {
  const headers: Record<string, string> = {
    Host: opts.host ?? ADMIN_HOST,
    Accept: "application/json",
  };
  if (opts.token) headers.Authorization = `Token ${opts.token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  let body: Envelope<T> & Record<string, unknown> = {};
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { rawText: text } as Envelope<T> & Record<string, unknown>;
    }
  }
  return { status: res.status, body };
}

function unwrap<T>(r: { status: number; body: Envelope<T> & Record<string, unknown> }): T {
  if (r.status < 200 || r.status >= 300) {
    throw new Error(`HTTP ${r.status}: ${JSON.stringify(r.body)}`);
  }
  // Some endpoints (RetrieveAPIView) return the bare model; tolerate both.
  return (r.body.data ?? (r.body as unknown as T)) as T;
}

async function login(email: string, password: string, host: string): Promise<string> {
  const r = await http<{ token: string }>("/admin/auth/login", {
    method: "POST",
    host,
    body: { email, password },
  });
  if (r.status !== 200) {
    throw new Error(
      `Login failed for ${email} on ${host}: ${r.status} ${JSON.stringify(r.body)}. ` +
        `Did you run 'make bootstrap' first?`,
    );
  }
  return (r.body.data as { token: string }).token;
}

// ---------------------------------------------------------------------------
// Ensure-or-create helpers
// ---------------------------------------------------------------------------
type Tenant = { id: string; subdomain: string; name: string };

async function ensureTenant(
  token: string,
  spec: { name: string; subdomain: string; currency: string },
): Promise<Tenant> {
  const list = await http<Tenant[]>("/admin/platform/tenants?page_size=100", { token });
  const existing = (
    (list.body.data as Tenant[] | undefined) ??
    (list.body as unknown as { results?: Tenant[] }).results ??
    []
  ).find((t) => t.subdomain === spec.subdomain);
  if (existing) return existing;

  const created = await http<Tenant>("/admin/platform/tenants", {
    method: "POST",
    token,
    body: {
      name: spec.name,
      subdomain: spec.subdomain,
      defaultCurrency: spec.currency,
      isActive: true,
    },
  });
  return unwrap<Tenant>(created);
}

async function ensureMembership(
  token: string,
  tenantId: string,
  email: string,
  password: string,
): Promise<void> {
  // The endpoint uses update_or_create internally, so a second POST with
  // the same (email, tenant) returns 201 with the existing row's role
  // refreshed. Effectively idempotent.
  const r = await http("/admin/platform/tenants/" + tenantId + "/memberships", {
    method: "POST",
    token,
    body: {
      email,
      role: "tenant_admin",
      createUserIfMissing: true,
      initialPassword: password,
      firstName: "Tenant",
      lastName: "Admin",
    },
  });
  if (r.status !== 201 && r.status !== 200) {
    throw new Error(
      `Membership create failed for ${email} -> ${tenantId}: ${r.status} ${JSON.stringify(r.body)}`,
    );
  }
}

type Customer = {
  id: string;
  email: string;
  customerType?: string;
};

async function ensureCustomer(
  token: string,
  host: string,
  body: {
    email: string;
    name: string;
    customerType?: "B2C" | "B2B";
    taxId?: string;
    companyName?: string;
  },
): Promise<Customer> {
  const list = await http<Customer[]>(
    `/admin/customers?email=${encodeURIComponent(body.email)}&page_size=100`,
    { token, host },
  );
  const rows =
    (list.body.data as Customer[] | undefined) ??
    (list.body as unknown as { results?: Customer[] }).results ??
    [];
  const existing = rows.find((c) => c.email.toLowerCase() === body.email.toLowerCase());
  if (existing) return existing;

  const created = await http<Customer>("/admin/customers", {
    method: "POST",
    token,
    host,
    body: { ...body, customerType: body.customerType ?? "B2C" },
  });
  return unwrap<Customer>(created);
}

async function ensureGatewayConfig(token: string, host: string): Promise<void> {
  const list = await http<Array<{ gatewayName: string }>>(
    "/admin/payment-gateways?page_size=100",
    { token, host },
  );
  const rows =
    (list.body.data as Array<{ gatewayName: string }> | undefined) ??
    (list.body as unknown as { results?: Array<{ gatewayName: string }> }).results ??
    [];
  if (rows.some((g) => g.gatewayName === "mock")) return;

  const r = await http("/admin/payment-gateways", {
    method: "POST",
    token,
    host,
    body: {
      gatewayName: "mock",
      credentials: {},
      isActive: true,
      isDefault: true,
    },
  });
  unwrap(r);
}

type ProductSpec = {
  sku: string;
  name: string;
  description: string;
  price: string;
  currency: string;
  stockQuantity: number;
};

async function ensureProduct(token: string, host: string, spec: ProductSpec): Promise<void> {
  // The admin product list supports filtering by search, which matches sku.
  const list = await http<Array<{ sku: string }>>(
    `/admin/products?search=${encodeURIComponent(spec.sku)}&page_size=100`,
    { token, host },
  );
  const rows =
    (list.body.data as Array<{ sku: string }> | undefined) ??
    (list.body as unknown as { results?: Array<{ sku: string }> }).results ??
    [];
  if (rows.some((p) => p.sku === spec.sku)) return;

  const r = await http("/admin/products", {
    method: "POST",
    token,
    host,
    body: { ...spec, isActive: true },
  });
  unwrap(r);
}

type CouponSpec = {
  code: string;
  discountType: "percentage" | "fixed";
  discountValue: string;
  currency?: string;
  minCartSubtotal?: string;
  validFrom?: string;
  validUntil?: string;
  maxUses?: number;
  usesCount?: number;
  allowedCountries?: string[];
  // DB stores the 3-char enum values ("B2C", "B2B"), not the *_ONLY labels.
  customerTypeRestriction?: "B2C" | "B2B";
};

async function ensureCoupon(token: string, host: string, spec: CouponSpec): Promise<void> {
  const list = await http<Array<{ code: string }>>(
    `/admin/coupons?search=${encodeURIComponent(spec.code)}&page_size=100`,
    { token, host },
  );
  const rows =
    (list.body.data as Array<{ code: string }> | undefined) ??
    (list.body as unknown as { results?: Array<{ code: string }> }).results ??
    [];
  if (rows.some((c) => c.code === spec.code)) return;

  const r = await http("/admin/coupons", {
    method: "POST",
    token,
    host,
    body: { ...spec, isActive: true },
  });
  unwrap(r);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  console.log(`Provisioning fixtures against ${API}`);
  console.log("");

  // 1. Platform login (relies on `make bootstrap`)
  const platformToken = await login(PLATFORM_EMAIL, PLATFORM_PASSWORD, ADMIN_HOST);
  console.log(`  [+] platform login (${PLATFORM_EMAIL})`);

  // 2. Tenants
  const tenantA = await ensureTenant(platformToken, TENANT_A);
  console.log(`  [+] tenant A: ${tenantA.subdomain} (${tenantA.id})`);
  const tenantB = await ensureTenant(platformToken, TENANT_B);
  console.log(`  [+] tenant B: ${tenantB.subdomain} (${tenantB.id})`);

  // 3. Tenant admins
  await ensureMembership(platformToken, tenantA.id, OWNER_A.email, OWNER_A.password);
  console.log(`  [+] tenant admin: ${OWNER_A.email} -> store-a`);
  await ensureMembership(platformToken, tenantB.id, OWNER_B.email, OWNER_B.password);
  console.log(`  [+] tenant admin: ${OWNER_B.email} -> store-b`);

  // 4. Store-a provisioning
  const ownerAToken = await login(OWNER_A.email, OWNER_A.password, TENANT_A_HOST);
  await ensureGatewayConfig(ownerAToken, TENANT_A_HOST);
  console.log("  [+] store-a: mock gateway config");

  const alice = await ensureCustomer(ownerAToken, TENANT_A_HOST, {
    email: "alice@store-a.test",
    name: "Alice",
  });
  const charlie = await ensureCustomer(ownerAToken, TENANT_A_HOST, {
    email: "charlie@store-a.test",
    name: "Charlie",
  });
  const diana = await ensureCustomer(ownerAToken, TENANT_A_HOST, {
    email: "diana@store-a.test",
    name: "Diana",
    customerType: "B2B",
    taxId: "SA-TAX-987654",
    companyName: "Diana Industries LLC",
  });
  console.log(
    `  [+] store-a customers: alice=${alice.id}, charlie=${charlie.id}, diana=${diana.id}`,
  );

  const products: ProductSpec[] = [
    { sku: "SA-WIDGET-01", name: "Saudi Widget", description: "A classic widget", price: "99.99", currency: "SAR", stockQuantity: 50 },
    { sku: "SA-GIZMO-01", name: "Saudi Gizmo", description: "A premium gizmo", price: "249.50", currency: "SAR", stockQuantity: 5 },
    { sku: "SA-SCARCE-01", name: "Last One", description: "Used by the concurrency test — stock=1", price: "500.00", currency: "SAR", stockQuantity: 1 },
    { sku: "SA-USD-01", name: "USD-priced widget on store-a", description: "Currency-mismatch test fixture", price: "49.99", currency: "USD", stockQuantity: 100 },
  ];
  for (const p of products) {
    await ensureProduct(ownerAToken, TENANT_A_HOST, p);
  }
  console.log(`  [+] store-a products: ${products.map((p) => p.sku).join(", ")}`);

  const now = new Date();
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
  const nextYear = new Date(now.getTime() + 365 * 24 * 60 * 60 * 1000).toISOString();
  const coupons: CouponSpec[] = [
    { code: "WELCOME10", discountType: "percentage", discountValue: "10" },
    { code: "FLAT5", discountType: "fixed", discountValue: "5", currency: "SAR" },
    { code: "CAP100", discountType: "fixed", discountValue: "100000", currency: "SAR" },
    { code: "MIN100K", discountType: "percentage", discountValue: "10", minCartSubtotal: "100000" },
    { code: "EXPIRED", discountType: "percentage", discountValue: "10", validUntil: yesterday },
    { code: "NOTYET", discountType: "percentage", discountValue: "10", validFrom: nextYear },
    { code: "EXHAUSTED", discountType: "percentage", discountValue: "10", maxUses: 1, usesCount: 1 },
    { code: "AEONLY", discountType: "percentage", discountValue: "10", allowedCountries: ["AE"] },
    { code: "B2BONLY", discountType: "percentage", discountValue: "10", customerTypeRestriction: "B2B" },
    { code: "USDFIXED", discountType: "fixed", discountValue: "20", currency: "USD" },
  ];
  for (const c of coupons) {
    await ensureCoupon(ownerAToken, TENANT_A_HOST, c);
  }
  console.log(`  [+] store-a coupons: ${coupons.map((c) => c.code).join(", ")}`);

  // 5. Store-b provisioning
  const ownerBToken = await login(OWNER_B.email, OWNER_B.password, TENANT_B_HOST);
  await ensureGatewayConfig(ownerBToken, TENANT_B_HOST);
  console.log("  [+] store-b: mock gateway config");
  const bob = await ensureCustomer(ownerBToken, TENANT_B_HOST, {
    email: "bob@store-b.test",
    name: "Bob",
  });
  console.log(`  [+] store-b customer: bob=${bob.id}`);

  await ensureProduct(ownerBToken, TENANT_B_HOST, {
    sku: "US-WIDGET-01",
    name: "US Widget",
    description: "Made in the US",
    price: "29.99",
    currency: "USD",
    stockQuantity: 100,
  });
  console.log("  [+] store-b product: US-WIDGET-01");

  // 6. Persist fixtures
  const out = {
    generatedAt: new Date().toISOString(),
    tenants: {
      a: { id: tenantA.id, subdomain: tenantA.subdomain },
      b: { id: tenantB.id, subdomain: tenantB.subdomain },
    },
    customers: {
      alice: alice.id,
      charlie: charlie.id,
      diana: diana.id,
      bob: bob.id,
    },
  };
  writeFileSync(FIXTURES_PATH, JSON.stringify(out, null, 2) + "\n");
  console.log("");
  console.log(`Wrote ${FIXTURES_PATH}`);
  console.log("Test suite is now provisioned. Run `bun test --cwd tests-ts`.");
}

main().catch((err) => {
  console.error("");
  console.error("Provisioning failed:", err.message);
  process.exit(1);
});
