import { beforeAll, describe, expect, test } from "bun:test";
import {
  ADMIN_HOST,
  adminCall,
  adminLogin,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  PLATFORM_EMAIL,
  PLATFORM_PASSWORD,
} from "../admin/helpers";
import { firstErrorCode } from "../helpers";

type PlatformCustomer = {
  id: string;
  tenantId: string;
  tenantSubdomain: string;
  email: string;
  isActive: boolean;
};

let platformToken = "";
let tenantToken = "";

beforeAll(async () => {
  ({ token: platformToken } = await adminLogin(PLATFORM_EMAIL, PLATFORM_PASSWORD));
  ({ token: tenantToken } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD));
});

describe("platform-admin cross-tenant customer search", () => {
  test("?email= returns matches from any tenant with tenantSubdomain attached", async () => {
    const r = await adminCall<PlatformCustomer[]>("/admin/platform/customers?email=store", {
      host: ADMIN_HOST,
      token: platformToken,
    });
    expect(r.status).toBe(200);
    const subdomains = new Set((r.body.data ?? []).map((c) => c.tenantSubdomain));
    // Seeded customers live on store-a and store-b; both should appear.
    expect(subdomains.has("store-a")).toBe(true);
    expect(subdomains.has("store-b")).toBe(true);
  });

  test("?email=alice&tenant_subdomain=store-a narrows to one tenant", async () => {
    const r = await adminCall<PlatformCustomer[]>(
      "/admin/platform/customers?email=alice&tenant_subdomain=store-a",
      { host: ADMIN_HOST, token: platformToken },
    );
    expect(r.status).toBe(200);
    for (const c of r.body.data ?? []) {
      expect(c.tenantSubdomain).toBe("store-a");
      expect(c.email.toLowerCase()).toContain("alice");
    }
  });

  test("missing ?email= → 400 email_query_required (no accidental cross-tenant dump)", async () => {
    const r = await adminCall("/admin/platform/customers", {
      host: ADMIN_HOST,
      token: platformToken,
    });
    expect(r.status).toBe(400);
    expect(firstErrorCode(r)).toBe("email_query_required");
  });

  test("tenant-admin token → 403 (IsPlatformAdmin requires superuser)", async () => {
    const r = await adminCall("/admin/platform/customers?email=alice", {
      host: ADMIN_HOST,
      token: tenantToken,
    });
    expect(r.status).toBe(403);
  });

  test("no auth → 401", async () => {
    const r = await adminCall("/admin/platform/customers?email=alice", {
      host: ADMIN_HOST,
    });
    expect(r.status).toBe(401);
  });

  test("?email longer than 254 chars → 400 email_query_too_long", async () => {
    const longEmail = "a".repeat(300);
    const r = await adminCall(`/admin/platform/customers?email=${encodeURIComponent(longEmail)}`, {
      host: ADMIN_HOST,
      token: platformToken,
    });
    expect(r.status).toBe(400);
    expect(firstErrorCode(r)).toBe("email_query_too_long");
  });
});
