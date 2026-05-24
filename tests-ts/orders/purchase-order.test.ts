// PO (purchase-order) checkout path.
//
// Asserts the saga's PO branch:
//   * B2B customer adds a `purchase_order` payment method, no gateway.
//   * Checkout returns paymentStatus="invoice_pending"; order stays PENDING.
//   * Order snapshot includes payment_terms + payment_due_date + is_b2b.
//   * Replay with the same idempotency key returns the same orderId.
//   * B2C customer is forbidden from adding a PO method.
//   * Tenant admin's POST /admin/orders/{id}/mark-paid flips order to PAID
//     and is idempotent on a second call.
//   * Reconciliation sweep does NOT touch INVOICE_PENDING payments.

import { describe, expect, test } from "bun:test";
import {
  ADMIN_HOST,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  PLATFORM_EMAIL,
  PLATFORM_PASSWORD,
  TENANT_A_HOST,
  adminCall,
  adminLogin,
} from "../admin/helpers";
import { DIANA, SKUS } from "../fixtures";
import {
  ALICE,
  type Cart,
  type CheckoutData,
  attemptCheckout,
  call,
  ensureAddress,
  firstErrorCode,
  getProductBySku,
  readyCart,
  resetCart,
  uuid,
} from "../helpers";

type PaymentMethodResp = {
  id: string;
  methodType: string;
  gatewayName: string | null;
  paymentTerms?: string;
  poAccountLabel?: string;
};

async function createPoMethod(
  customer: string,
  host: string = TENANT_A_HOST,
): Promise<PaymentMethodResp> {
  const r = await call<PaymentMethodResp>(`/customers/${customer}/payment-methods`, {
    method: "POST",
    customer,
    host,
    body: {
      methodType: "purchase_order",
      paymentTerms: "net_30",
      poAccountLabel: "Diana Industries net-30",
      isDefault: true,
    },
  });
  if (r.status !== 201 || !r.body.data) {
    throw new Error(`createPoMethod failed: ${r.status} ${JSON.stringify(r.body)}`);
  }
  return r.body.data;
}

async function readyPoCart(customer: string = DIANA): Promise<{ cart: Cart; methodId: string }> {
  await resetCart(customer);
  const product = await getProductBySku(SKUS.widget, { customer });
  const addressId = await ensureAddress(customer);
  const pm = await createPoMethod(customer);

  const add = await call<Cart>("/cart/items", {
    method: "POST",
    customer,
    body: { productId: product.id, quantity: 1 },
  });
  if (add.status !== 200) {
    throw new Error(`add item failed: ${add.status} ${JSON.stringify(add.body)}`);
  }
  await call("/cart/shipping-address", { method: "PUT", customer, body: { id: addressId } });
  await call("/cart/billing-address", { method: "PUT", customer, body: { id: addressId } });
  await call("/cart/payment-method", { method: "PUT", customer, body: { id: pm.id } });

  const fresh = await call<Cart>("/cart", { customer });
  return { cart: fresh.body.data!, methodId: pm.id };
}

describe("purchase-order checkout path", () => {
  test("B2B customer with PO method checks out → order PENDING + invoice_pending", async () => {
    await readyPoCart();

    const key = `po-${uuid()}`;
    const r = await call<CheckoutData>("/cart/checkout", {
      method: "POST",
      customer: DIANA,
      headers: { "Idempotency-Key": key },
      body: { paymentMetadata: {} },
    });
    // 202 — payment is not yet "captured" (mark-paid by admin is what flips it).
    expect(r.status).toBe(202);
    const co = r.body.data!;
    expect(co.paymentStatus).toBe("invoice_pending");
    expect(co.status).toBe("pending");

    // Order detail surfaces the PO snapshot. RetrieveAPIView returns the
    // bare model — no `data` envelope — so accept either shape.
    type PoOrder = {
      status: string;
      isB2b: boolean;
      paymentTerms: string;
      paymentDueDate: string | null;
    };
    const orderRes = await call<PoOrder>(`/orders/${co.orderId}`, { customer: DIANA });
    expect(orderRes.status).toBe(200);
    const order = (orderRes.body.data ?? (orderRes.body as unknown as PoOrder)) as PoOrder;
    expect(order.status).toBe("pending");
    expect(order.isB2b).toBe(true);
    expect(order.paymentTerms).toBe("net_30");
    expect(order.paymentDueDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  test("idempotent replay returns same order on PO path", async () => {
    await readyPoCart();
    const key = `po-${uuid()}`;
    const first = await call<CheckoutData>("/cart/checkout", {
      method: "POST",
      customer: DIANA,
      headers: { "Idempotency-Key": key },
      body: { paymentMetadata: {} },
    });
    expect(first.status).toBe(202);

    const second = await call<CheckoutData>("/cart/checkout", {
      method: "POST",
      customer: DIANA,
      headers: { "Idempotency-Key": key },
      body: { paymentMetadata: {} },
    });
    expect(second.body.data!.orderId).toBe(first.body.data!.orderId);
    expect(second.body.data!.paymentStatus).toBe("invoice_pending");
  });

  test("B2C customer cannot add a purchase_order payment method", async () => {
    const r = await call(`/customers/${ALICE}/payment-methods`, {
      method: "POST",
      customer: ALICE,
      body: {
        methodType: "purchase_order",
        paymentTerms: "net_30",
      },
    });
    expect(r.status).toBe(403);
    expect(firstErrorCode(r)).toBe("forbidden");
  });

  test("PO method create rejected without payment_terms", async () => {
    const r = await call(`/customers/${DIANA}/payment-methods`, {
      method: "POST",
      customer: DIANA,
      body: { methodType: "purchase_order" },
    });
    expect(r.status).toBe(422);
  });
});

describe("admin mark-paid", () => {
  test("admin marks PO order paid → status PAID + idempotent", async () => {
    await readyPoCart();
    const key = `po-paid-${uuid()}`;
    const co = await call<CheckoutData>("/cart/checkout", {
      method: "POST",
      customer: DIANA,
      headers: { "Idempotency-Key": key },
      body: { paymentMetadata: {} },
    });
    const orderId = co.body.data!.orderId;

    const login = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD, TENANT_A_HOST);

    const mark = await adminCall<{ status: string }>(`/admin/orders/${orderId}/mark-paid`, {
      method: "POST",
      host: TENANT_A_HOST,
      token: login.token,
      body: { reference: "wire-2026-05-23-001" },
    });
    expect(mark.status).toBe(200);
    expect(mark.body.data!.status).toBe("paid");

    // Idempotent: second call returns the order in paid state, no error.
    const again = await adminCall<{ status: string }>(`/admin/orders/${orderId}/mark-paid`, {
      method: "POST",
      host: TENANT_A_HOST,
      token: login.token,
      body: {},
    });
    expect(again.status).toBe(200);
    expect(again.body.data!.status).toBe("paid");
  });

  test("mark-paid is a no-op on a card order (already PAID via capture)", async () => {
    await readyCart();
    const co = await attemptCheckout(ALICE, `card-${uuid()}`);
    if (!co.ok) throw new Error(`setup checkout failed: ${co.status} ${co.code}`);

    const login = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD, TENANT_A_HOST);
    const mark = await adminCall<{ status: string }>(
      `/admin/orders/${co.data.orderId}/mark-paid`,
      {
        method: "POST",
        host: TENANT_A_HOST,
        token: login.token,
        body: {},
      },
    );
    // Card orders go straight to PAID via gateway capture; mark-paid
    // hits the "already PAID" idempotent return and leaves state alone.
    expect(mark.status).toBe(200);
    expect(mark.body.data!.status).toBe("paid");
  });
});

describe("reconciliation does not touch INVOICE_PENDING payments", () => {
  test("force reconcile leaves PO payments alone", async () => {
    await readyPoCart();
    const key = `po-recon-${uuid()}`;
    const co = await call<CheckoutData>("/cart/checkout", {
      method: "POST",
      customer: DIANA,
      headers: { "Idempotency-Key": key },
      body: { paymentMetadata: {} },
    });
    const orderId = co.body.data!.orderId;

    // Trigger the platform-admin reconciliation sweep
    const platform = await adminLogin(PLATFORM_EMAIL, PLATFORM_PASSWORD, ADMIN_HOST);
    const sweep = await adminCall(`/admin/platform/ops/reconcile-payments?stale_after_minutes=0`, {
      method: "POST",
      host: ADMIN_HOST,
      token: platform.token,
    });
    expect(sweep.status).toBe(200);

    // Order is still PENDING; the sweep did not flip the PO payment.
    const owner = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD, TENANT_A_HOST);
    const detail = await adminCall<{
      status: string;
      payments: Array<{ status: string }>;
    }>(`/admin/orders/${orderId}`, {
      host: TENANT_A_HOST,
      token: owner.token,
    });
    expect(detail.body.data!.status).toBe("pending");
    expect(detail.body.data!.payments.some((p) => p.status === "invoice_pending")).toBe(true);
  });
});
