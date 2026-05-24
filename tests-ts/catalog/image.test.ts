// Product image upload end-to-end:
//   POST multipart → admin shows imageUrl → URL serves the bytes → storefront
//   also surfaces imageUrl → DELETE clears it → bad content-type is 422.
// Requires MinIO running on the configured AWS_S3_ENDPOINT_URL.

import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { adminCall, adminLogin, OWNER_A_EMAIL, OWNER_A_PASSWORD } from "../admin/helpers";
import { ALICE, API, call, TENANT_A_HOST } from "../helpers";

type AdminProduct = {
  id: string;
  sku: string;
  imageKey: string;
  imageUrl: string;
};
type StorefrontProduct = { id: string; sku: string; imageUrl: string };

// 1x1 transparent PNG -- smallest valid PNG.
const TINY_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";
const TINY_PNG = Uint8Array.from(atob(TINY_PNG_B64), (c) => c.charCodeAt(0));

let token = "";
let productId = "";
const skuSuffix = Date.now().toString(36);

async function multipartUpload(productIdLocal: string, blob: Blob, filename: string) {
  const fd = new FormData();
  fd.append("file", blob, filename);
  const res = await fetch(`${API}/admin/products/${productIdLocal}/image`, {
    method: "POST",
    headers: {
      Host: TENANT_A_HOST,
      Authorization: `Token ${token}`,
    },
    body: fd,
  });
  const text = await res.text();
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    body = { rawText: text };
  }
  return { status: res.status, body: body as { data?: AdminProduct; errors?: unknown[] } };
}

beforeAll(async () => {
  ({ token } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD));
  // Create a throwaway product so we don't pollute the SA-WIDGET-01 image
  // that journey.test.ts relies on staying clean.
  const created = await adminCall<AdminProduct>("/admin/products", {
    method: "POST",
    host: TENANT_A_HOST,
    token,
    body: {
      sku: `IMG-${skuSuffix}`,
      name: "Image upload test product",
      price: "5.00",
      currency: "SAR",
      stockQuantity: 1,
      isActive: true,
    },
  });
  if (created.status !== 201 || !created.body.data) {
    throw new Error(`product create failed: ${created.status} ${JSON.stringify(created.body)}`);
  }
  productId = created.body.data.id;
});

afterAll(async () => {
  if (productId) {
    await adminCall(`/admin/products/${productId}`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
  }
});

describe("tenant-admin product image upload", () => {
  test("POST multipart sets image_key + image_url; URL serves the bytes", async () => {
    const r = await multipartUpload(
      productId,
      new Blob([TINY_PNG], { type: "image/png" }),
      "tiny.png",
    );
    expect(r.status).toBe(200);
    expect(r.body.data!.imageKey).toMatch(/tenants\/.+\/products\/.+\/main\.png$/);
    expect(r.body.data!.imageUrl).toMatch(/^https?:\/\/.+\/media\/tenants\/.+\.png$/);

    const fetched = await fetch(r.body.data!.imageUrl);
    expect(fetched.status).toBe(200);
    expect(fetched.headers.get("content-type")).toBe("image/png");
    const bytes = new Uint8Array(await fetched.arrayBuffer());
    expect(bytes.length).toBe(TINY_PNG.length);
    // PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
    expect(bytes[0]).toBe(0x89);
    expect(bytes[1]).toBe(0x50);
  });

  test("storefront GET /products/{id} surfaces the same imageUrl", async () => {
    // The storefront detail endpoint returns the bare model (no envelope),
    // so read the field at the top level.
    const r = await call<StorefrontProduct>(`/products/${productId}`, { customer: ALICE });
    expect(r.status).toBe(200);
    const body = r.body as unknown as StorefrontProduct;
    expect(body.imageUrl).toMatch(/^https?:\/\/.+\.png$/);
  });

  test("DELETE clears image_key + image_url", async () => {
    const del = await adminCall(`/admin/products/${productId}/image`, {
      method: "DELETE",
      host: TENANT_A_HOST,
      token,
    });
    expect(del.status).toBe(204);

    const after = await adminCall<AdminProduct>(`/admin/products/${productId}`, {
      host: TENANT_A_HOST,
      token,
    });
    expect(after.body.data!.imageKey).toBe("");
    expect(after.body.data!.imageUrl).toBe("");
  });

  test("bad content-type → 422 validation_error", async () => {
    const r = await multipartUpload(
      productId,
      new Blob([new TextEncoder().encode("not an image")], { type: "text/plain" }),
      "bad.txt",
    );
    expect(r.status).toBe(422);
  });

  test("missing file field → 422", async () => {
    const fd = new FormData();
    const res = await fetch(`${API}/admin/products/${productId}/image`, {
      method: "POST",
      headers: { Host: TENANT_A_HOST, Authorization: `Token ${token}` },
      body: fd,
    });
    expect(res.status).toBe(422);
  });

  test("no auth → 401", async () => {
    const fd = new FormData();
    fd.append("file", new Blob([TINY_PNG], { type: "image/png" }), "tiny.png");
    const res = await fetch(`${API}/admin/products/${productId}/image`, {
      method: "POST",
      headers: { Host: TENANT_A_HOST },
      body: fd,
    });
    expect(res.status).toBe(401);
  });
});
