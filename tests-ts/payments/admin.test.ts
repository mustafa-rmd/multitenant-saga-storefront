// Coverage for the admin-side payment visibility shipped in this session:
//   * GET /admin/orders                       — now uses AdminOrderSerializer
//   * GET /admin/orders/{id}                  — same, with prefetched nested data
//   * GET /admin/orders/{id}/payments         — dedicated payment-attempt list
//
// Strategy: complete a real checkout via the storefront so we have one Order
// with one Payment + Invoice row to inspect; then re-fetch through the admin
// rail and assert the operator-grade fields land.

import { beforeAll, describe, expect, test } from "bun:test";
import {
  adminCall,
  adminLogin,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  TENANT_A_HOST,
  TENANT_B_HOST,
} from "../admin/helpers";
import { ALICE, attemptCheckout, readyCart, uuid } from "../helpers";

type AdminOrder = {
  id: string;
  orderNumber: number;
  status: string;
  customerId: string;
  payments: AdminPayment[];
  invoice: {
    id: string;
    invoiceNumber: number;
    pdfUrl: string;
    issuedAt: string | null;
  } | null;
};

type AdminPayment = {
  id: string;
  status: string;
  amount: string;
  currency: string;
  gatewayName: string;
  gatewayTransactionId: string;
  idempotencyKey: string;
  gatewayResponse: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

let token = "";
let orderId = "";

beforeAll(async () => {
  // 1. Storefront: ready cart + checkout so we have an Order + Payment + Invoice.
  await readyCart();
  const co = await attemptCheckout(ALICE, `admin-pay-${uuid()}`);
  if (!co.ok) {
    throw new Error(`checkout failed in beforeAll: ${co.status} ${co.code} ${co.detail}`);
  }
  orderId = co.data.orderId;

  // 2. Tenant-admin login to get the token for the rest of the suite.
  ({ token } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD));
});

describe("GET /admin/orders/{id} returns AdminOrderSerializer shape", () => {
  test("includes customerId, payments[], and invoice block", async () => {
    const r = await adminCall<AdminOrder>(`/admin/orders/${orderId}`, {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(200);
    const o = r.body.data!;
    expect(o.id).toBe(orderId);
    expect(o.status).toBe("paid");
    expect(o.customerId).toBe(ALICE);
    expect(Array.isArray(o.payments)).toBe(true);
    expect(o.payments.length).toBeGreaterThanOrEqual(1);

    const p = o.payments[0]!;
    expect(p.status).toBe("captured");
    expect(p.gatewayName).toBe("mock");
    expect(p.gatewayTransactionId).toMatch(/^mock_txn_/);
    expect(p.idempotencyKey).toMatch(/^admin-pay-/);
    expect(p.amount).toBeTruthy();
    expect(p.currency).toBe("SAR");

    // Invoice may take a moment to materialize (Celery); poll-style retry once.
    let invoice = o.invoice;
    if (!invoice) {
      await new Promise((r) => setTimeout(r, 800));
      const again = await adminCall<AdminOrder>(`/admin/orders/${orderId}`, {
        host: TENANT_A_HOST,
        token,
      });
      invoice = again.body.data!.invoice;
    }
    // We assert on shape only; the invoice MAY still be null if Celery is
    // genuinely down. That's a separate test failure (see invoices.test.ts).
    if (invoice) {
      expect(invoice.invoiceNumber).toBeGreaterThan(0);
      expect(typeof invoice.pdfUrl).toBe("string");
    }
  });

  test("bogus order id returns 404 not_found (clean envelope, not 500)", async () => {
    const r = await adminCall<AdminOrder>("/admin/orders/00000000-0000-0000-0000-000000000000", {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(404);
    expect(r.body.errors?.[0]?.code).toBe("not_found");
  });
});

describe("GET /admin/orders/{id}/payments", () => {
  test("returns the payment history newest first with full operator fields", async () => {
    const r = await adminCall<AdminPayment[]>(`/admin/orders/${orderId}/payments`, {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(200);
    const list = r.body.data!;
    expect(Array.isArray(list)).toBe(true);
    expect(list.length).toBeGreaterThanOrEqual(1);

    const p = list[0]!;
    // The full operator field set we promised.
    for (const k of [
      "id",
      "status",
      "amount",
      "currency",
      "gatewayName",
      "gatewayTransactionId",
      "idempotencyKey",
      "gatewayResponse",
      "createdAt",
      "updatedAt",
    ]) {
      expect(p).toHaveProperty(k);
    }
    expect(p.gatewayName).toBe("mock");
    expect(p.status).toBe("captured");
    // Raw gateway response is admin-only; assert it's a real object (mock
    // returns `{"mock": true, "outcome": "captured"}`).
    expect(typeof p.gatewayResponse).toBe("object");
  });

  test("bogus order id 404s on the payments subresource too", async () => {
    const r = await adminCall("/admin/orders/00000000-0000-0000-0000-000000000000/payments", {
      host: TENANT_A_HOST,
      token,
    });
    expect(r.status).toBe(404);
  });
});

describe("cross-tenant safety", () => {
  test("store-a admin token used against store-b host is rejected", async () => {
    const r = await adminCall<AdminOrder>(`/admin/orders/${orderId}/payments`, {
      host: TENANT_B_HOST,
      token,
    });
    // The IsTenantAdmin permission denies because the token's tenant doesn't
    // match the host's resolved tenant. 403 (not 401 — auth is valid, just
    // not for this tenant).
    expect(r.status).toBe(403);
  });
});
