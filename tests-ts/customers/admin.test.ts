import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { adminCall, adminLogin, OWNER_A_EMAIL, OWNER_A_PASSWORD } from "../admin/helpers";
import { ALICE, call, firstErrorCode, TENANT_A_HOST } from "../helpers";

type AdminCustomer = {
  id: string;
  email: string;
  name: string;
  customerType: "B2C" | "B2B";
  taxId: string;
  companyName: string;
  isB2b: boolean;
  isActive: boolean;
};

let token = "";
let createdId = "";
const suffix = Date.now().toString(36);
const b2cEmail = `b2c-${suffix}@test.local`;
const b2bEmail = `b2b-${suffix}@test.local`;

beforeAll(async () => {
  ({ token } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD));
});

afterAll(async () => {
  // Best-effort cleanup -- soft-delete is fine if a test left the row active.
  if (createdId) {
    await adminCall(`/admin/customers/${createdId}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
  }
});

describe("tenant-admin customer CRUD on store-a", () => {
  test("LIST returns Alice + Charlie at minimum (seed)", async () => {
    const r = await adminCall<AdminCustomer[]>("/admin/customers?page_size=100", {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(200);
    const emails = (r.body.data ?? []).map((c) => c.email);
    expect(emails).toContain("alice@store-a.test");
    expect(emails).toContain("charlie@store-a.test");
  });

  test("LIST supports ?email= substring + ?customer_type=", async () => {
    const r = await adminCall<AdminCustomer[]>("/admin/customers?email=alice&customer_type=B2C", {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(200);
    for (const c of r.body.data ?? []) {
      expect(c.email.toLowerCase()).toContain("alice");
      expect(c.customerType).toBe("B2C");
    }
  });

  test("POST creates a B2C customer", async () => {
    const r = await adminCall<AdminCustomer>("/admin/customers", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: { email: b2cEmail, name: "B2C tester", customerType: "B2C" },
    });
    expect(r.status).toBe(201);
    expect(r.body.data?.email).toBe(b2cEmail);
    expect(r.body.data?.isB2b).toBe(false);
    expect(r.body.data?.isActive).toBe(true);
    createdId = r.body.data!.id;
  });

  test("POST B2B without taxId/companyName → 422", async () => {
    const r = await adminCall("/admin/customers", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: { email: `bad-${suffix}@test.local`, customerType: "B2B" },
    });
    expect(r.status).toBe(422);
  });

  test("POST B2B with full fields → 201 + isB2b=true", async () => {
    const r = await adminCall<AdminCustomer>("/admin/customers", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        email: b2bEmail,
        name: "B2B tester",
        customerType: "B2B",
        taxId: "VAT-123",
        companyName: "Test Co Ltd",
      },
    });
    expect(r.status).toBe(201);
    expect(r.body.data?.isB2b).toBe(true);
    // Soft-delete this one in cleanup -- replace createdId so afterAll cleans
    // the most recently created row.
    createdId = r.body.data!.id;
  });

  test("POST duplicate email on the same tenant → 422 validation_error", async () => {
    const r = await adminCall("/admin/customers", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: { email: b2cEmail, customerType: "B2C" },
    });
    expect(r.status).toBe(422);
  });

  test("PATCH updates name + phone", async () => {
    const r = await adminCall<AdminCustomer>(`/admin/customers/${createdId}`, {
      method: "PATCH",
      host: TENANT_A_HOST,
      token,
      body: { name: "Renamed Co", phone: "+966555111222" },
    });
    expect(r.status).toBe(200);
    expect(r.body.data?.name).toBe("Renamed Co");
  });

  test("DELETE soft-deletes; storefront auth then 401s for that customer", async () => {
    const del = await adminCall(`/admin/customers/${createdId}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
    expect(del.status).toBe(204);

    const after = await adminCall<AdminCustomer>(`/admin/customers/${createdId}`, {
      host: TENANT_A_HOST,
      token,
    });
    expect(after.body.data?.isActive).toBe(false);

    // Storefront request with the now-blocked customer must fail.
    const blocked = await call("/products", {
      host: TENANT_A_HOST,
      customer: createdId,
    });
    expect(blocked.status).toBe(401);
    expect(["customer_not_found", "missing_customer_id"]).toContain(firstErrorCode(blocked) ?? "");

    // Alice (still active) keeps working -- soft-delete is scoped to the row.
    const alice = await call("/products", { host: TENANT_A_HOST, customer: ALICE });
    expect(alice.status).toBe(200);
  });

  test("PATCH isActive=true unblocks the customer", async () => {
    const r = await adminCall<AdminCustomer>(`/admin/customers/${createdId}`, {
      method: "PATCH",
      host: TENANT_A_HOST,
      token,
      body: { isActive: true },
    });
    expect(r.status).toBe(200);
    expect(r.body.data?.isActive).toBe(true);
  });
});

describe("tenant-admin customer — query + validation guards (bug fixes)", () => {
  test("GET /admin/customers/{unknown} returns customer_not_found (not generic not_found)", async () => {
    const r = await adminCall<AdminCustomer>(`/admin/customers/${crypto.randomUUID()}`, {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(404);
    expect(r.body.errors?.[0]?.code).toBe("customer_not_found");
  });

  test("LIST ?is_active=banana → 422 (invalid value, not silently parsed)", async () => {
    const r = await adminCall<AdminCustomer[]>("/admin/customers?is_active=banana", {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("LIST ?is_active=true still works (regression guard)", async () => {
    const r = await adminCall<AdminCustomer[]>("/admin/customers?is_active=true&page_size=100", {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(200);
    for (const c of r.body.data ?? []) {
      expect(c.isActive).toBe(true);
    }
  });

  test("LIST ?customer_type=banana → 422 (unknown type)", async () => {
    const r = await adminCall<AdminCustomer[]>("/admin/customers?customer_type=banana", {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("POST normalizes email to lowercase + strips whitespace", async () => {
    const rawEmail = `  Mixed-${suffix}@TEST.local  `;
    const expectedEmail = `mixed-${suffix}@test.local`;
    const r = await adminCall<AdminCustomer>("/admin/customers", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: { email: rawEmail, name: "Casing tester", customerType: "B2C" },
    });
    expect(r.status).toBe(201);
    expect(r.body.data?.email).toBe(expectedEmail);
    const id = r.body.data?.id;
    if (id) {
      await adminCall(`/admin/customers/${id}`, {
        method: "DELETE",
        host: TENANT_A_HOST,
        token,
      });
    }
  });

  test("POST same email with different casing → 422 (catches via normalization)", async () => {
    const baseEmail = `casing-${suffix}@test.local`;
    const a = await adminCall<AdminCustomer>("/admin/customers", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: { email: baseEmail, customerType: "B2C" },
    });
    expect(a.status).toBe(201);
    const id = a.body.data?.id;

    const b = await adminCall("/admin/customers", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: { email: baseEmail.toUpperCase(), customerType: "B2C" },
    });
    expect(b.status).toBe(422);

    if (id) {
      await adminCall(`/admin/customers/${id}`, {
        method: "DELETE",
        host: TENANT_A_HOST,
        token,
      });
    }
  });
});

describe("storefront address — country validation (bug #6)", () => {
  test("POST address with bad country → 422", async () => {
    const r = await call(`/customers/${ALICE}/addresses`, {
      method: "POST",
      customer: ALICE,
      host: TENANT_A_HOST,
      body: {
        label: "shipping",
        country: "NotACountry",
        city: "Riyadh",
        street: "Test St 99",
        postalCode: "12345",
        isDefault: false,
      },
    });
    expect(r.status).toBe(422);
    expect(firstErrorCode(r)).toBe("validation_error");
  });

  test("POST address with lowercase country normalizes to uppercase", async () => {
    const r = await call<{ id: string; country: string }>(`/customers/${ALICE}/addresses`, {
      method: "POST",
      customer: ALICE,
      host: TENANT_A_HOST,
      body: {
        label: "shipping",
        country: "sa",
        city: "Riyadh",
        street: "Test St 100",
        postalCode: "12345",
        isDefault: false,
      },
    });
    expect(r.status).toBe(201);
    // Endpoint returns the bare model (no envelope); accept both shapes.
    const body = r.body as unknown as {
      id?: string;
      country?: string;
      data?: { id: string; country: string };
    };
    const addr = body.data ?? (body as { id: string; country: string });
    expect(addr.country).toBe("SA");
    if (addr.id) {
      await call(`/customers/${ALICE}/addresses/${addr.id}`, {
        method: "DELETE",
        customer: ALICE,
        host: TENANT_A_HOST,
      });
    }
  });
});
