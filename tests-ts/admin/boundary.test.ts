// Cross-rail boundary tests.
// Storefront auth (X-Customer-Id) and admin auth (Authorization: Token) are
// two separate rails; tokens from one MUST NOT be accepted by the other.

import { describe, expect, test } from "bun:test";
import { ALICE, call, TENANT_A_HOST } from "../helpers";
import {
  ADMIN_HOST,
  adminCall,
  adminLogin,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  PLATFORM_EMAIL,
  PLATFORM_PASSWORD,
} from "./helpers";

describe("cross-rail auth boundary", () => {
  test("X-Customer-Id on an admin endpoint → 401 (no token issued)", async () => {
    const r = await adminCall("/admin/products", {
      host: TENANT_A_HOST,
      headers: { "X-Customer-Id": ALICE },
    });
    expect(r.status).toBe(401);
  });

  test("admin token on a storefront endpoint → 401 (token auth not honored there)", async () => {
    const { token } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD);
    const r = await call("/products", {
      host: TENANT_A_HOST,
      customer: null,
      headers: { Authorization: `Token ${token}` },
    });
    expect(r.status).toBe(401);
  });

  test("tenant admin against platform endpoint → 403 forbidden", async () => {
    const { token } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD);
    const r = await adminCall("/admin/platform/tenants", { host: ADMIN_HOST, token });
    expect(r.status).toBe(403);
  });

  test("platform admin against tenant-admin endpoint → 200 (superuser bypasses membership check)", async () => {
    const { token } = await adminLogin(PLATFORM_EMAIL, PLATFORM_PASSWORD);
    const r = await adminCall("/admin/products", { host: TENANT_A_HOST, token });
    expect(r.status).toBe(200);
  });

  test("admin endpoint without any auth → 401", async () => {
    const r = await adminCall("/admin/products", { host: TENANT_A_HOST });
    expect(r.status).toBe(401);
  });
});
