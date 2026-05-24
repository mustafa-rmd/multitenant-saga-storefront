import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import {
  adminCall,
  adminLogin,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  TENANT_A_HOST,
} from "../admin/helpers";
import { SKUS } from "../fixtures";

type Coupon = {
  id: string;
  code: string;
  discountType: string;
  discountValue: string;
  isActive: boolean;
};

const code = `TEST-${Date.now().toString(36)}`.toUpperCase();
let token = "";
let createdId = "";

beforeAll(async () => {
  ({ token } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD));
});

afterAll(async () => {
  if (createdId) {
    await adminCall(`/admin/coupons/${createdId}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
  }
});

describe("tenant-admin coupon CRUD on store-a", () => {
  test("POST creates a percentage coupon", async () => {
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code,
        discountType: "percentage",
        discountValue: "15",
        isActive: true,
      },
    });
    expect(r.status).toBe(201);
    createdId = r.body.data?.id ?? "";
    expect(r.body.data?.code).toBe(code);
  });

  test("PATCH sets a min-cart-subtotal constraint", async () => {
    const r = await adminCall<Coupon>(`/admin/coupons/${createdId}`, {
      method: "PATCH",
      host: TENANT_A_HOST,
      token,
      body: { minCartSubtotal: "200.00" },
    });
    expect(r.status).toBe(200);
  });

  test("DELETE soft-deletes (isActive=false)", async () => {
    const r = await adminCall(`/admin/coupons/${createdId}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(204);
    const after = await adminCall<Coupon>(`/admin/coupons/${createdId}`, {
      host: TENANT_A_HOST,
      token,
    });
    expect(after.body.data?.isActive).toBe(false);
    createdId = "";
  });
});

describe("tenant-admin coupon field-shape validation", () => {
  test("POST with non-ISO currency returns 422", async () => {
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: `${code}-BADCUR`,
        discountType: "fixed",
        discountValue: "5.00",
        currency: "xyz", // lowercase + unknown
        isActive: true,
      },
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("POST with empty currency on a percentage coupon is accepted", async () => {
    // Percentage coupons don't use currency; empty string allowed (the
    // cross-field "fixed requires currency" rule is a separate bug-tier fix).
    const localCode = `${code}-PCT`;
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: localCode,
        discountType: "percentage",
        discountValue: "10",
        isActive: true,
      },
    });
    expect(r.status).toBe(201);
    const id = r.body.data?.id;
    if (id) {
      await adminCall(`/admin/coupons/${id}`, {
        method: "DELETE",
        host: TENANT_A_HOST,
        token,
      });
    }
  });

  test("POST with non-ISO country code in allowedCountries returns 422", async () => {
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: `${code}-BADCTRY`,
        discountType: "percentage",
        discountValue: "10",
        allowedCountries: ["SA", "NotACountry"],
        isActive: true,
      },
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("POST with lowercase country code in allowedCountries returns 422", async () => {
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: `${code}-LOWCTRY`,
        discountType: "percentage",
        discountValue: "10",
        allowedCountries: ["sa"],
        isActive: true,
      },
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("POST with valid ISO country codes succeeds", async () => {
    const localCode = `${code}-OKCTRY`;
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: localCode,
        discountType: "percentage",
        discountValue: "10",
        allowedCountries: ["SA", "AE"],
        isActive: true,
      },
    });
    expect(r.status).toBe(201);
    const id = r.body.data?.id;
    if (id) {
      await adminCall(`/admin/coupons/${id}`, {
        method: "DELETE",
        host: TENANT_A_HOST,
        token,
      });
    }
  });
});

describe("tenant-admin coupon — cross-field + state validation (bug fixes)", () => {
  test("GET /admin/coupons/{unknown} returns coupon_not_found (not generic not_found)", async () => {
    const r = await adminCall<Coupon>(`/admin/coupons/${crypto.randomUUID()}`, {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(404);
    expect(r.body.errors?.[0]?.code).toBe("coupon_not_found");
  });

  test("POST fixed coupon without currency → 422 (currency required for FIXED)", async () => {
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: `${code}-FIXNOCUR`,
        discountType: "fixed",
        discountValue: "5.00",
        isActive: true,
      },
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("POST percentage > 100 → 422", async () => {
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: `${code}-OVER100`,
        discountType: "percentage",
        discountValue: "150",
        isActive: true,
      },
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("POST discount_value <= 0 → 422", async () => {
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: `${code}-ZERO`,
        discountType: "percentage",
        discountValue: "0",
        isActive: true,
      },
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("POST duplicate code on the same tenant → 422 (not IntegrityError 500)", async () => {
    const dupCode = `${code}-DUP`;
    const create = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: dupCode,
        discountType: "percentage",
        discountValue: "10",
        isActive: true,
      },
    });
    expect(create.status).toBe(201);
    const id = create.body.data?.id;

    const dup = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: dupCode,
        discountType: "percentage",
        discountValue: "20",
        isActive: true,
      },
    });
    expect(dup.status).toBe(422);
    expect(dup.body.errors?.[0]?.code).toBe("validation_error");

    if (id) {
      await adminCall(`/admin/coupons/${id}`, {
        method: "DELETE",
        host: TENANT_A_HOST,
        token,
      });
    }
  });

  test("POST normalizes code (strip whitespace + uppercase)", async () => {
    // code constant is uppercase already; lowercase the suffix to prove
    // upper-casing fires, and pad with whitespace to prove stripping fires.
    const suffix = `norm-${Date.now().toString(36)}`;
    const rawCode = `  ${suffix}  `;
    const expectedCode = suffix.toUpperCase();
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: rawCode,
        discountType: "percentage",
        discountValue: "25",
        isActive: true,
      },
    });
    expect(r.status).toBe(201);
    expect(r.body.data?.code).toBe(expectedCode);
    const id = r.body.data?.id;
    if (id) {
      await adminCall(`/admin/coupons/${id}`, {
        method: "DELETE",
        host: TENANT_A_HOST,
        token,
      });
    }
  });

  test("POST code with disallowed characters → 422", async () => {
    const r = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: "hello world!",
        discountType: "percentage",
        discountValue: "10",
        isActive: true,
      },
    });
    expect(r.status).toBe(422);
    expect(r.body.errors?.[0]?.code).toBe("validation_error");
  });

  test("PATCH max_uses below current uses_count → 422", async () => {
    // Seed: create coupon with max_uses=10 but no uses yet, then PATCH to 0.
    // uses_count starts at 0, so any negative-or-zero new max that's still
    // >=0 wouldn't trigger; we test setting max_uses to a value below the
    // current uses_count by first bumping uses_count via... actually
    // uses_count is server-internal. Use uses_count=0 + new max_uses=-1.
    // But min_value isn't on max_uses so negative is accepted at field level.
    // The guard kicks in: -1 < 0 → 422.
    const create = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: `${code}-MAXG`,
        discountType: "percentage",
        discountValue: "10",
        maxUses: 10,
        isActive: true,
      },
    });
    expect(create.status).toBe(201);
    const id = create.body.data!.id;

    const patch = await adminCall<Coupon>(`/admin/coupons/${id}`, {
      method: "PATCH",
      host: TENANT_A_HOST,
      token,
      body: { maxUses: -1 },
    });
    expect(patch.status).toBe(422);
    expect(patch.body.errors?.[0]?.code).toBe("validation_error");

    await adminCall(`/admin/coupons/${id}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
  });

  test("PATCH valid_until to a past timestamp → 422", async () => {
    const create = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: `${code}-PASTUNT`,
        discountType: "percentage",
        discountValue: "10",
        isActive: true,
      },
    });
    expect(create.status).toBe(201);
    const id = create.body.data!.id;

    const patch = await adminCall<Coupon>(`/admin/coupons/${id}`, {
      method: "PATCH",
      host: TENANT_A_HOST,
      token,
      body: { validUntil: "2020-01-01T00:00:00Z" },
    });
    expect(patch.status).toBe(422);
    expect(patch.body.errors?.[0]?.code).toBe("validation_error");

    await adminCall(`/admin/coupons/${id}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
  });

  test("PATCH currency while coupon is applied to an active cart → 422", async () => {
    // Create a SAR-fixed coupon, apply it to Alice's cart, try to PATCH
    // currency to USD.
    const localCode = `${code}-CURG`;
    const create = await adminCall<Coupon>("/admin/coupons", {
      method: "POST",
      host: TENANT_A_HOST,
      token,
      body: {
        code: localCode,
        discountType: "fixed",
        discountValue: "5.00",
        currency: "SAR",
        isActive: true,
      },
    });
    expect(create.status).toBe(201);
    const id = create.body.data!.id;

    // Storefront path: add to cart + apply coupon.
    const { call: storeCall, resetCart, ALICE, getProductBySku } = await import("../helpers");
    await resetCart(ALICE, TENANT_A_HOST);
    const widget = await getProductBySku(SKUS.widget);
    const add = await storeCall("/cart/items", {
      method: "POST",
      body: { productId: widget.id, quantity: 1 },
    });
    expect([200, 201]).toContain(add.status);
    const apply = await storeCall("/cart/coupons", {
      method: "POST",
      body: { code: localCode },
    });
    expect(apply.status).toBe(200);

    const patch = await adminCall<Coupon>(`/admin/coupons/${id}`, {
      method: "PATCH",
      host: TENANT_A_HOST,
      token,
      body: { currency: "USD" },
    });
    expect(patch.status).toBe(422);
    expect(patch.body.errors?.[0]?.code).toBe("validation_error");

    // Cleanup
    await resetCart(ALICE, TENANT_A_HOST);
    await adminCall(`/admin/coupons/${id}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
  });
});
