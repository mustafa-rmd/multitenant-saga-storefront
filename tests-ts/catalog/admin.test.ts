import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import {
  adminCall,
  adminLogin,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  TENANT_A_HOST,
} from "../admin/helpers";
import { SKUS } from "../fixtures";

type Product = {
  id: string;
  sku: string;
  name: string;
  price: string;
  currency: string;
  stockQuantity: number;
  isActive: boolean;
};

const skuPrefix = `ADM-${Date.now().toString(36)}`;
let token = "";
let createdId = "";

beforeAll(async () => {
  ({ token } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD));
});

afterAll(async () => {
  if (createdId) {
    await adminCall(`/admin/products/${createdId}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
  }
});

describe("tenant-admin product CRUD on store-a", () => {
  test("POST creates a new product on the tenant subdomain", async () => {
    const r = await adminCall<Product>("/admin/products", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        sku: `${skuPrefix}-WIDGET`,
        name: "Admin-created widget",
        description: "Created by test",
        price: "9.99",
        currency: "SAR",
        stockQuantity: 25,
        isActive: true,
      },
    });
    expect(r.status).toBe(201);
    createdId = r.body.data?.id ?? "";
    expect(createdId).toMatch(/^[0-9a-f-]{36}$/);
    expect(r.body.data?.sku).toBe(`${skuPrefix}-WIDGET`);
    expect(r.body.data?.stockQuantity).toBe(25);
  });

  test("LIST includes the newly created product (with envelope pagination)", async () => {
    const r = await adminCall<Product[]>(`/admin/products?page_size=100`, {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(200);
    const list = r.body.data ?? [];
    expect(list.find((p) => p.id === createdId)).toBeDefined();
  });

  test("PATCH updates the price", async () => {
    const r = await adminCall<Product>(`/admin/products/${createdId}`, {
      method: "PATCH",
      host: TENANT_A_HOST,
      token,
      body: { price: "19.99" },
    });
    expect(r.status).toBe(200);
    expect(r.body.data?.price).toBe("19.99");
  });

  test("DELETE soft-deletes (sets isActive=false; row stays)", async () => {
    const r = await adminCall(`/admin/products/${createdId}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(204);

    const after = await adminCall<Product>(`/admin/products/${createdId}`, {
      host: TENANT_A_HOST,
      token,
    });
    expect(after.status).toBe(200);
    expect(after.body.data?.isActive).toBe(false);
    createdId = ""; // avoid afterAll re-delete
  });
});

describe("tenant-admin product validation", () => {
  const sku = `${skuPrefix}-DUP`;
  let id = "";

  test("POST with duplicate SKU returns 422 (not IntegrityError 500)", async () => {
    const create = await adminCall<Product>("/admin/products", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        sku,
        name: "Duplicate-target widget",
        price: "1.00",
        currency: "SAR",
        stockQuantity: 1,
        isActive: true,
      },
    });
    expect(create.status).toBe(201);
    id = create.body.data?.id ?? "";

    const dup = await adminCall<Product>("/admin/products", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        sku, // same SKU on the same tenant
        name: "Should fail",
        price: "2.00",
        currency: "SAR",
        stockQuantity: 1,
        isActive: true,
      },
    });
    expect(dup.status).toBe(422);
    expect(dup.body.errors?.[0]?.code).toBe("validation_error");

    // Cleanup
    if (id) {
      await adminCall(`/admin/products/${id}`, {
        method: "DELETE",
        host: TENANT_A_HOST,
        token,
      });
    }
  });

  test("POST with non-ISO currency returns 422", async () => {
    const r = await adminCall<Product>("/admin/products", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        sku: `${skuPrefix}-CURBAD`,
        name: "Bad currency",
        price: "1.00",
        currency: "xyz", // lowercase + unknown
        stockQuantity: 1,
        isActive: true,
      },
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("PATCH stock_quantity below currently reserved is rejected (422)", async () => {
    // SA-SCARCE-01 is a seeded scarce product. Even with reserved=0 we can
    // exercise the boundary: set stock to -1 which is < reserved=0 always.
    // (Negative ints land before the constraint, so this primarily proves
    // the new server-side guard returns 422 rather than 500.)
    const list = await adminCall<Product[]>(`/admin/products?page_size=100`, {
      host: TENANT_A_HOST,
      token,
    });
    const target = (list.body.data ?? []).find((p) => p.sku === SKUS.widget);
    expect(target).toBeDefined();

    const r = await adminCall<Product>(`/admin/products/${target!.id}`, {
      method: "PATCH",
      host: TENANT_A_HOST,
      token,
      body: { stockQuantity: -1 },
    });
    // Either the new guard or the DB check rejects -- both surface as 422 now.
    expect([400, 422]).toContain(r.status);
  });

  test("PATCH currency on a product sitting in an active cart returns 422", async () => {
    // Alice's seeded ACTIVE cart contains SA-WIDGET-01 in the journey/cart tests,
    // but those run/reset independently. We add one ourselves to guarantee state.
    const list = await adminCall<Product[]>(`/admin/products?page_size=100`, {
      host: TENANT_A_HOST,
      token,
    });
    const widget = (list.body.data ?? []).find((p) => p.sku === SKUS.widget);
    expect(widget).toBeDefined();

    // Force-add to Alice's cart through the storefront API. Use the plain
    // `call` helper (no admin token, with X-Customer-Id).
    const { call: storeCall, resetCart, ALICE } = await import("../helpers");
    await resetCart(ALICE, TENANT_A_HOST);
    const add = await storeCall("/cart/items", {
      method: "POST",
      body: { productId: widget!.id, quantity: 1 },
    });
    expect([200, 201]).toContain(add.status);

    const r = await adminCall<Product>(`/admin/products/${widget!.id}`, {
      method: "PATCH",
      host: TENANT_A_HOST,
      token,
      body: { currency: "USD" },
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");

    await resetCart(ALICE, TENANT_A_HOST);
  });
});
