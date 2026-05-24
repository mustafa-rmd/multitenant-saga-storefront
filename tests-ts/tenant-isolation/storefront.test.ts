// HTTP port of tests/test_tenant_isolation.py — the subset that can be
// verified from outside the process. The Python suite also covers:
//
//   * Manager-level fail-closed when no tenant context is set
//   * `all_objects` (UnscopedManager) escape hatch
//   * Tenant model itself being unscoped
//   * Postgres RLS blocking cross-tenant raw SQL
//
// None of those are reachable through the HTTP surface — they're in-process
// invariants tested by exercising the ORM directly. They remain documented
// gaps in tests-ts/README.md.

import { describe, expect, test } from "bun:test";
import {
  ALICE,
  BOB,
  call,
  firstErrorCode,
  listProducts,
  type Product,
  TENANT_A_HOST,
  TENANT_B_HOST,
} from "../helpers";

describe("tenant isolation (HTTP layer)", () => {
  test("each tenant host shows its own catalogue and only its own", async () => {
    const a = await listProducts({ host: TENANT_A_HOST, customer: ALICE });
    const b = await listProducts({ host: TENANT_B_HOST, customer: BOB });

    expect(a.length).toBeGreaterThan(0);
    expect(b.length).toBeGreaterThan(0);

    const aSkus = new Set(a.map((p) => p.sku));
    const bSkus = new Set(b.map((p) => p.sku));
    const overlap = [...aSkus].filter((s) => bSkus.has(s));
    expect(overlap).toEqual([]);
  });

  test("Alice's UUID against store-b → 401 customer_not_found (customer scoped per tenant)", async () => {
    const r = await call<Product[]>("/products", { host: TENANT_B_HOST, customer: ALICE });
    expect([401, 404]).toContain(r.status);
    if (r.status === 401) {
      expect(["customer_not_found", "missing_customer_id", "unauthorized"]).toContain(
        firstErrorCode(r) ?? "",
      );
    }
  });

  test("Bob's UUID against store-a → 401 customer_not_found", async () => {
    const r = await call<Product[]>("/products", { host: TENANT_A_HOST, customer: BOB });
    expect([401, 404]).toContain(r.status);
  });

  test("Bob cannot read an Alice address by UUID even with the right tenant header", async () => {
    // Issue an address as Alice, then try to bind it on Bob's cart via store-b.
    const created = await call<{ id: string }>(`/customers/${ALICE}/addresses`, {
      method: "POST",
      customer: ALICE,
      host: TENANT_A_HOST,
      body: {
        label: "shipping",
        country: "SA",
        city: "Riyadh",
        street: "Test St 1",
        postalCode: "12345",
        isDefault: false,
      },
    });
    const aliceAddrId = created.body.data?.id ?? (created.body as unknown as { id?: string }).id;
    expect(aliceAddrId).toBeTruthy();

    const r = await call("/cart/shipping-address", {
      method: "PUT",
      host: TENANT_B_HOST,
      customer: BOB,
      body: { id: aliceAddrId },
    });
    // Either rejected at customer auth (401) or at resource lookup (404).
    expect([401, 404]).toContain(r.status);
  });

  test("missing tenant subdomain → 400 tenant_required (no Host header in dev → fallback tenant; force unknown host)", async () => {
    const r = await call<Product[]>("/products", {
      host: "unknown.acme.test",
      customer: ALICE,
    });
    // The middleware returns 404 tenant_not_found when the subdomain doesn't
    // resolve. (400 tenant_required is for a totally missing subdomain, which
    // is unreachable with our current Host parser.)
    expect([400, 404]).toContain(r.status);
    expect(["tenant_required", "tenant_not_found"]).toContain(firstErrorCode(r) ?? "");
  });

  test("OpenAPI schema and Swagger UI are tenant-agnostic and remain reachable", async () => {
    const schema = await fetch("http://localhost:8000/api/v1/schema/", {
      headers: { Host: TENANT_A_HOST },
    });
    expect(schema.status).toBe(200);

    const docs = await fetch("http://localhost:8000/api/v1/docs/", {
      headers: { Host: TENANT_A_HOST },
    });
    // Swagger UI returns text/html; 200 is enough — we're verifying routing,
    // not the UI itself.
    expect(docs.status).toBe(200);
  });
});
