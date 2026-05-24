// Storefront /products filter validation. The handler used to pass minPrice
// and inStock straight through, surfacing bad input as 500s. These tests
// cover the validation guards added on those query params.

import { describe, expect, test } from "bun:test";
import { call, firstErrorCode, type Product } from "../helpers";

describe("GET /products — filter validation", () => {
  test("minPrice=abc → 422 validation_error", async () => {
    const r = await call<Product[]>("/products?minPrice=abc");
    expect(r.status).toBe(422);
    expect(firstErrorCode(r)).toBe("validation_error");
  });

  test("maxPrice=oops → 422 validation_error", async () => {
    const r = await call<Product[]>("/products?maxPrice=oops");
    expect(r.status).toBe(422);
    expect(firstErrorCode(r)).toBe("validation_error");
  });

  test("inStock=banana → 422 validation_error", async () => {
    const r = await call<Product[]>("/products?inStock=banana");
    expect(r.status).toBe(422);
    expect(firstErrorCode(r)).toBe("validation_error");
  });

  test("inStock=true returns only available products", async () => {
    const r = await call<Product[]>("/products?inStock=true");
    expect(r.status).toBe(200);
    for (const p of r.body.data ?? []) {
      expect(p.availableQuantity).toBeGreaterThan(0);
    }
  });

  test("inStock=false returns only out-of-stock products (may be empty)", async () => {
    const r = await call<Product[]>("/products?inStock=false");
    expect(r.status).toBe(200);
    for (const p of r.body.data ?? []) {
      expect(p.availableQuantity).toBeLessThanOrEqual(0);
    }
  });

  test("minPrice / maxPrice still work on valid input", async () => {
    const r = await call<Product[]>("/products?minPrice=10&maxPrice=10000");
    expect(r.status).toBe(200);
    for (const p of r.body.data ?? []) {
      const price = parseFloat(p.price);
      expect(price).toBeGreaterThanOrEqual(10);
      expect(price).toBeLessThanOrEqual(10000);
    }
  });
});
