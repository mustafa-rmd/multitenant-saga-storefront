import { describe, expect, test } from "bun:test";
import { firstErrorCode } from "../helpers";
import {
  ADMIN_HOST,
  adminCall,
  adminLogin,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  PLATFORM_EMAIL,
  PLATFORM_PASSWORD,
} from "./helpers";

describe("admin auth", () => {
  test("platform admin can log in and /auth/me reflects superuser=true", async () => {
    const data = await adminLogin(PLATFORM_EMAIL, PLATFORM_PASSWORD);
    expect(data.token.length).toBeGreaterThan(20);
    expect(data.user.email).toBe(PLATFORM_EMAIL);
    expect(data.user.isSuperuser).toBe(true);
    expect(data.user.memberships).toEqual([]);
    // Token TTL: response carries an ISO-8601 timestamp ~8h in the future
    // (ADMIN_TOKEN_TTL_SECONDS default = 28800).
    expect(typeof data.expiresAt).toBe("string");
    const minutesAhead = (new Date(data.expiresAt!).getTime() - Date.now()) / 60_000;
    expect(minutesAhead).toBeGreaterThan(60);

    const me = await adminCall<{ email: string; isSuperuser: boolean }>("/admin/auth/me", {
      token: data.token,
    });
    expect(me.status).toBe(200);
    expect(me.body.data?.isSuperuser).toBe(true);
  });

  test("re-login rotates the token; the old token stops authenticating", async () => {
    const first = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD);
    const second = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD);
    expect(second.token).not.toBe(first.token);

    // The old token should now 401 (it was deleted when the new one was minted).
    const dead = await adminCall("/admin/auth/me", { token: first.token });
    expect(dead.status).toBe(401);

    const live = await adminCall("/admin/auth/me", { token: second.token });
    expect(live.status).toBe(200);
  });

  test("tenant admin can log in and sees a single TENANT_ADMIN membership", async () => {
    const { user } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD);
    expect(user.isSuperuser).toBe(false);
    expect(user.memberships.length).toBe(1);
    expect(user.memberships[0].tenantSubdomain).toBe("store-a");
    expect(user.memberships[0].role).toBe("tenant_admin");
  });

  test("wrong password → 401 invalid_credentials (same code for unknown email)", async () => {
    const bad = await adminCall("/admin/auth/login", {
      method: "POST",
      body: { email: PLATFORM_EMAIL, password: "wrong" },
    });
    expect(bad.status).toBe(401);
    expect(firstErrorCode(bad)).toBe("invalid_credentials");

    const unknown = await adminCall("/admin/auth/login", {
      method: "POST",
      body: { email: "ghost@nowhere.test", password: "anything" },
    });
    expect(unknown.status).toBe(401);
    expect(firstErrorCode(unknown)).toBe("invalid_credentials");
  });

  test("logout revokes the token; subsequent calls 401", async () => {
    // Use a tenant-admin user here so we don't kill the platform token mid-suite
    // (other tests in the suite may rely on a shared platform login).
    const { token } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD);
    const ok = await adminCall("/admin/auth/me", { token });
    expect(ok.status).toBe(200);

    const logout = await adminCall("/admin/auth/logout", { method: "POST", token });
    expect(logout.status).toBe(204);

    const dead = await adminCall("/admin/auth/me", { token });
    expect(dead.status).toBe(401);
  });

  test("admin login from any host works (platform login is host-independent)", async () => {
    // Login is in GLOBAL_EXEMPT_PATHS so tenant resolution is skipped; the
    // endpoint should respond regardless of which subdomain it hits.
    const onTenant = await adminCall("/admin/auth/login", {
      method: "POST",
      host: "store-a.acme.test",
      body: { email: PLATFORM_EMAIL, password: PLATFORM_PASSWORD },
    });
    expect(onTenant.status).toBe(200);

    const onAdmin = await adminCall("/admin/auth/login", {
      method: "POST",
      host: ADMIN_HOST,
      body: { email: PLATFORM_EMAIL, password: PLATFORM_PASSWORD },
    });
    expect(onAdmin.status).toBe(200);
  });
});
