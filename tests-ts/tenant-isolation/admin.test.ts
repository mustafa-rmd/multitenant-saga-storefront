import { beforeAll, describe, expect, test } from "bun:test";
import {
  adminCall,
  adminLogin,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  TENANT_A_HOST,
  TENANT_B_HOST,
} from "../admin/helpers";

let ownerAToken = "";

beforeAll(async () => {
  ({ token: ownerAToken } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD));
});

describe("tenant-admin cannot reach another tenant's data", () => {
  test("owner-a's token against store-b list-products → 403 forbidden", async () => {
    const r = await adminCall("/admin/products", { host: TENANT_B_HOST, token: ownerAToken });
    expect(r.status).toBe(403);
  });

  test("owner-a's token against store-b create-product → 403 forbidden", async () => {
    const r = await adminCall("/admin/products", {
      method: "POST",
      host: TENANT_B_HOST,
      token: ownerAToken,
      body: { sku: "X-EVIL", name: "evil", price: "1.00", currency: "USD", stockQuantity: 1 },
    });
    expect(r.status).toBe(403);
  });

  test("owner-a's token against store-b orders → 403 forbidden", async () => {
    const r = await adminCall("/admin/orders", { host: TENANT_B_HOST, token: ownerAToken });
    expect(r.status).toBe(403);
  });

  test("owner-a's token against store-a still works (sanity)", async () => {
    const r = await adminCall("/admin/products", { host: TENANT_A_HOST, token: ownerAToken });
    expect(r.status).toBe(200);
  });
});
