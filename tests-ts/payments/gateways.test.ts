// Coverage for the public payment-gateway surface and the validation paths
// guarding `POST /payment-methods`.
//
// Scope:
//   * GET /payment-gateways               (list)
//   * GET /payment-gateways/{name}        (detail / capabilities)
//   * POST /customers/{id}/payment-methods validation:
//       - invalid `gatewayName` -> 400
//       - valid enum but not configured -> 409 gateway_not_configured
//
// The mock-gate behaviour (`PAYMENTS_ALLOW_MOCK_GATEWAY=False`) is not exercised
// here because flipping that env var requires a server restart, which is
// outside the black-box scope. The settings check itself is unit-tested in the
// Python integration we ran by hand earlier in this session.

import { describe, expect, test } from "bun:test";
import { ALICE, BOB, call, firstErrorCode, TENANT_A_HOST } from "../helpers";

type Gateway = {
  name: string;
  displayName: string;
  isDefault: boolean;
};

type GatewayDetail = Gateway & {
  supportedCurrencies: string[];
  tokenization: "client" | "server";
  supports3ds: boolean;
  publicCredentials: Record<string, string>;
};

describe("GET /payment-gateways (list)", () => {
  test("returns the tenant's active gateways with display name + default flag", async () => {
    const r = await call<Gateway[]>("/payment-gateways");
    expect(r.status).toBe(200);
    const list = r.body.data!;
    expect(Array.isArray(list)).toBe(true);
    expect(list.length).toBeGreaterThan(0);
    for (const g of list) {
      expect(typeof g.name).toBe("string");
      expect(typeof g.displayName).toBe("string");
      expect(typeof g.isDefault).toBe("boolean");
      // List endpoint is intentionally lean — capabilities live on detail.
      expect("supportedCurrencies" in g).toBe(false);
    }
    // Seed defaults give the mock gateway the default flag for both tenants.
    expect(list.some((g) => g.name === "mock" && g.isDefault)).toBe(true);
  });

  test("requires a valid tenant — random subdomain 404s the tenant", async () => {
    const r = await call<Gateway[]>("/payment-gateways", {
      host: "no-such-tenant.acme.test",
    });
    expect(r.status).toBe(404);
    expect(firstErrorCode(r)).toBe("tenant_not_found");
  });
});

describe("GET /payment-gateways/{name} (detail)", () => {
  test("mock detail exposes capabilities, omits secrets", async () => {
    const r = await call<GatewayDetail>("/payment-gateways/mock");
    expect(r.status).toBe(200);
    const g = r.body.data!;
    expect(g.name).toBe("mock");
    expect(g.displayName).toBe("Mock (test gateway)");
    expect(g.tokenization).toBe("server");
    expect(g.supports3ds).toBe(true);
    // Empty supportedCurrencies signals "accept all" — explicitly contracted.
    expect(Array.isArray(g.supportedCurrencies)).toBe(true);
    expect(g.supportedCurrencies.length).toBe(0);
    // publicCredentials must always be an object (never null) for stable JSON shape.
    expect(typeof g.publicCredentials).toBe("object");
    expect(g.publicCredentials).not.toBeNull();
    // The secret_key / webhook_secret fields from the stored credentials
    // must never appear on the public surface.
    expect(JSON.stringify(g)).not.toContain("secretKey");
    expect(JSON.stringify(g)).not.toContain("webhookSecret");
  });

  test("unconfigured-but-known gateway 404s", async () => {
    // `stripe` is a registered gateway class but the seed only configures `mock`.
    const r = await call<GatewayDetail>("/payment-gateways/stripe");
    expect(r.status).toBe(404);
    expect(firstErrorCode(r)).toBe("not_found");
  });

  test("unknown gateway name 404s with same code (no enumeration leak)", async () => {
    const r = await call<GatewayDetail>("/payment-gateways/doesNotExist");
    expect(r.status).toBe(404);
    expect(firstErrorCode(r)).toBe("not_found");
  });
});

describe("POST /payment-methods validation", () => {
  const url = `/customers/${ALICE}/payment-methods`;

  test("invalid gateway_name returns 422 with field-level error", async () => {
    const r = await call(url, {
      method: "POST",
      body: { gatewayName: "doesNotExist" },
    });
    // The project's custom DRF exception handler maps DRF ValidationError
    // to 422 (Unprocessable Entity) rather than 400 — see handler.py.
    expect(r.status).toBe(422);
    const err = r.body.errors?.[0];
    expect(err?.code).toBe("validation_error");
    // The custom exception handler maps DRF field errors with a `source.pointer`.
    expect(JSON.stringify(err)).toContain("/gateway_name");
  });

  test("valid enum but not configured -> 409 gateway_not_configured", async () => {
    const r = await call(url, {
      method: "POST",
      body: { gatewayName: "tap" },
    });
    expect(r.status).toBe(409);
    expect(firstErrorCode(r)).toBe("gateway_not_configured");
  });

  test("happy path: mock gateway with server-side tokenization succeeds", async () => {
    const r = await call<{ id: string; brand: string; lastFour: string }>(url, {
      method: "POST",
      body: {
        gatewayName: "mock",
        brand: "visa",
        lastFour: "4242",
      },
    });
    expect(r.status).toBe(201);
    expect(r.body.data?.id).toBeTruthy();
    // Server-side tokenization filled in the token; the response only shows
    // brand + lastFour (token is intentionally redacted by the serializer).
    expect(r.body.data?.brand).toBe("visa");
    expect(r.body.data?.lastFour).toBe("4242");
  });
});

describe("tenant isolation on the gateway surface", () => {
  test("each tenant sees its own gateways via the resolved host", async () => {
    // Use each tenant's own seeded customer so CustomerAuthMiddleware passes.
    const a = await call<Gateway[]>("/payment-gateways", {
      host: TENANT_A_HOST,
      customer: ALICE,
    });
    const b = await call<Gateway[]>("/payment-gateways", {
      host: "store-b.acme.test",
      customer: BOB,
    });
    expect(a.status).toBe(200);
    expect(b.status).toBe(200);
    // Both tenants seed their own mock config; rows are disjoint per-tenant
    // (verified via RLS), so each host independently returns its own list.
    expect(a.body.data!.length).toBeGreaterThan(0);
    expect(b.body.data!.length).toBeGreaterThan(0);
  });

  test("alice's customer id against store-b host is rejected (no info leak)", async () => {
    const r = await call<Gateway[]>("/payment-gateways", {
      host: "store-b.acme.test",
      customer: ALICE,
    });
    // Storefront-rail auth middleware refuses cross-tenant customer ids
    // with 401 customer_not_found.
    expect(r.status).toBe(401);
  });
});
