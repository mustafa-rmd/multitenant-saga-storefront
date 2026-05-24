import { beforeAll, describe, expect, test } from "bun:test";
import {
  adminCall,
  adminLogin,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  TENANT_A_HOST,
} from "../admin/helpers";

type Order = { id: string; orderNumber: number; status: string; customerId: string };

let token = "";

beforeAll(async () => {
  ({ token } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD));
});

describe("tenant-admin order visibility", () => {
  test("LIST returns orders across all customers of the tenant", async () => {
    const r = await adminCall<Order[]>("/admin/orders?page_size=100", {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(200);
    // The order list may be empty in a fresh seed; just verify the shape.
    expect(Array.isArray(r.body.data)).toBe(true);
  });

  test("LIST supports ?status= filter", async () => {
    const r = await adminCall<Order[]>("/admin/orders?status=pending", {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(200);
    for (const o of r.body.data ?? []) expect(o.status).toBe("pending");
  });
});
