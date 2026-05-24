import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import {
  ADMIN_HOST,
  adminCall,
  adminLogin,
  PLATFORM_EMAIL,
  PLATFORM_PASSWORD,
} from "../admin/helpers";

type TenantAdmin = { id: string; userId: string; userEmail: string; role: string };
type Tenant = {
  id: string;
  name: string;
  subdomain: string;
  defaultCurrency: string;
  isActive: boolean;
  tenantAdmins: TenantAdmin[];
};
type Membership = { id: string; userId: number; tenantId: string; role: string };

const subdomain = `plat-${Date.now().toString(36)}`;
const newAdminEmail = `${subdomain}-owner@test.local`;
let token = "";
let tenantId = "";
let membershipId = "";

beforeAll(async () => {
  ({ token } = await adminLogin(PLATFORM_EMAIL, PLATFORM_PASSWORD));
});

afterAll(async () => {
  if (membershipId) {
    await adminCall(`/admin/platform/memberships/${membershipId}`, {
      method: "DELETE",
      host: ADMIN_HOST,
      token,
    });
  }
  if (tenantId) {
    // Soft-deactivate; we never hard-delete tenants because orders may FK to them.
    await adminCall(`/admin/platform/tenants/${tenantId}`, {
      method: "PATCH",
      host: ADMIN_HOST,
      token,
      body: { isActive: false },
    });
  }
});

describe("platform-admin tenant + membership lifecycle", () => {
  test("POST /platform/tenants creates a tenant", async () => {
    const r = await adminCall<Tenant>("/admin/platform/tenants", {
      method: "POST",
      host: ADMIN_HOST,
      token,
      body: { name: "Platform Test", subdomain, defaultCurrency: "USD", isActive: true },
    });
    expect(r.status).toBe(201);
    tenantId = r.body.data?.id ?? "";
    expect(tenantId).toMatch(/^[0-9a-f-]{36}$/);
    expect(r.body.data?.subdomain).toBe(subdomain);
  });

  test("GET /platform/tenants/{id} returns it", async () => {
    const r = await adminCall<Tenant>(`/admin/platform/tenants/${tenantId}`, {
      host: ADMIN_HOST,
      token,
    });
    expect(r.status).toBe(200);
    expect(r.body.data?.subdomain).toBe(subdomain);
  });

  test("POST membership creates the admin user inline and binds them", async () => {
    const r = await adminCall<Membership>(`/admin/platform/tenants/${tenantId}/memberships`, {
      method: "POST",
      host: ADMIN_HOST,
      token,
      body: {
        email: newAdminEmail,
        role: "tenant_admin",
        createUserIfMissing: true,
        initialPassword: "first-pass-123",
        firstName: "New",
        lastName: "Owner",
      },
    });
    expect(r.status).toBe(201);
    membershipId = r.body.data?.id ?? "";
    expect(r.body.data?.role).toBe("tenant_admin");
    expect(r.body.data?.tenantId).toBe(tenantId);
  });

  test("the new admin can log in and sees their membership", async () => {
    const { user } = await adminLogin(newAdminEmail, "first-pass-123");
    expect(user.memberships.length).toBe(1);
    expect(user.memberships[0].tenantSubdomain).toBe(subdomain);
  });

  test("GET /platform/tenants/{id} embeds tenantAdmins", async () => {
    const r = await adminCall<Tenant>(`/admin/platform/tenants/${tenantId}`, {
      host: ADMIN_HOST,
      token,
    });
    expect(r.status).toBe(200);
    const admins = r.body.data?.tenantAdmins ?? [];
    const match = admins.find((a) => a.userEmail === newAdminEmail);
    expect(match).toBeDefined();
    expect(match?.role).toBe("tenant_admin");
  });

  test("reserved subdomain is rejected with 422", async () => {
    const r = await adminCall("/admin/platform/tenants", {
      method: "POST",
      host: ADMIN_HOST,
      token,
      body: { name: "Bad", subdomain: "www", defaultCurrency: "USD", isActive: true },
    });
    expect(r.status).toBe(422);
  });
});
