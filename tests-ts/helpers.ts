// Shared HTTP helpers for the smoke + behavioural tests.
//
// Talks to the local Django server. We always send an explicit `Host` header
// so tests work without editing /etc/hosts — multi-tenant routing happens by
// Host. Heavier helpers (resetCart, ensureAddress, readyCart) sit at the
// bottom; the call surface above is a thin wrapper over fetch.
//
// Wire format is camelCase (CamelCaseMiddleware translates to/from snake_case
// for the Python side). All type definitions and JSON bodies here use camelCase.

import { SKUS, ALICE, CHARLIE, BOB } from "./fixtures";

// Re-export from fixtures so existing tests that import these from
// ./helpers keep working without churn.
export { ALICE, CHARLIE, BOB };

export const BASE = process.env.ECOM_BASE_URL ?? "http://localhost:8000";
export const API = `${BASE}/api/v1`;

export const TENANT_A_HOST = process.env.ECOM_TENANT_A_HOST ?? "store-a.acme.test";
export const TENANT_B_HOST = process.env.ECOM_TENANT_B_HOST ?? "store-b.acme.test";

export type Envelope<T> = {
  data?: T;
  errors?: Array<{ code: string; detail?: string; meta?: Record<string, unknown> }>;
  meta: { requestId: string; version: string; pagination?: unknown };
};

export type CallOptions = {
  method?: string;
  host?: string;
  customer?: string | null;
  body?: unknown;
  headers?: Record<string, string>;
};

export type Response<T> = {
  status: number;
  ok: boolean;
  body: Envelope<T>;
  raw: globalThis.Response;
};

export async function call<T = unknown>(
  path: string,
  opts: CallOptions = {},
): Promise<Response<T>> {
  const method = opts.method ?? "GET";
  const host = opts.host ?? TENANT_A_HOST;
  const customer = opts.customer === null ? null : (opts.customer ?? ALICE);

  const headers: Record<string, string> = {
    Host: host,
    Accept: "application/json",
    ...opts.headers,
  };
  if (customer) headers["X-Customer-Id"] = customer;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  const url = path.startsWith("http") ? path : `${API}${path}`;
  const res = await fetch(url, {
    method,
    headers,
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });

  let body: Envelope<T>;
  const text = await res.text();
  try {
    body = text ? JSON.parse(text) : ({ meta: { requestId: "", version: "" } } as Envelope<T>);
  } catch {
    body = { meta: { requestId: "", version: "" } } as Envelope<T>;
    (body as unknown as { rawText: string }).rawText = text;
  }
  return { status: res.status, ok: res.ok, body, raw: res };
}

export function uuid(): string {
  return crypto.randomUUID();
}

export function firstErrorCode<T>(r: Response<T>): string | undefined {
  return r.body.errors?.[0]?.code;
}

export type Product = {
  id: string;
  sku: string;
  name: string;
  price: string;
  currency: string;
  stockQuantity: number;
  // reservedQuantity is intentionally NOT exposed by the public /products
  // endpoint -- operational state, leaks contention info. Use the admin
  // surface (AdminProduct) if you need it.
  availableQuantity: number;
  isActive: boolean;
};

export type CartItem = {
  id: string;
  productId: string;
  productName: string;
  productSku: string;
  quantity: number;
  unitPriceSnapshot: string;
  currency: string;
  lineTotal: string;
};

export type Cart = {
  id: string;
  customerId: string;
  version: number;
  status: string;
  currency: string;
  items: CartItem[];
  appliedCoupons: Array<{ code: string }>;
  shippingAddressId: string | null;
  billingAddressId: string | null;
  selectedPaymentMethodId: string | null;
  totals: { subtotal: string; discountTotal: string; grandTotal: string; currency: string };
};

export type Order = {
  id: string;
  orderNumber: number;
  status: string;
  subtotal: string;
  discountTotal: string;
  grandTotal: string;
  currency: string;
  isB2b?: boolean;
  taxId?: string | null;
  items: Array<{ productId: string; quantity: number; unitPrice: string; lineTotal: string }>;
};

export type CheckoutData = {
  orderId: string;
  orderNumber: number;
  status: string;
  paymentStatus: string;
  grandTotal: string;
  currency: string;
  nextAction: Record<string, unknown> | null;
};

// ---------------------------------------------------------------------------
// Higher-level helpers
// ---------------------------------------------------------------------------

export async function listProducts(
  opts: { host?: string; customer?: string } = {},
): Promise<Product[]> {
  const r = await call<Product[]>("/products", opts);
  if (r.status !== 200) throw new Error(`GET /products failed: ${r.status}`);
  return r.body.data!;
}

export async function getProductBySku(
  sku: string,
  opts: { host?: string; customer?: string } = {},
): Promise<Product> {
  const products = await listProducts(opts);
  const p = products.find((x) => x.sku === sku);
  if (!p) throw new Error(`No product with sku=${sku} on this tenant`);
  return p;
}

/** Empty the active cart for `customer`. No-op if there is no cart. */
export async function resetCart(
  customer: string = ALICE,
  host: string = TENANT_A_HOST,
): Promise<void> {
  const r = await call<Cart>("/cart", { customer, host });
  if (r.status !== 200) return;
  const cart = r.body.data!;
  for (const c of cart.appliedCoupons ?? []) {
    await call(`/cart/coupons/${c.code}`, { method: "DELETE", customer, host });
  }
  for (const item of cart.items) {
    await call(`/cart/items/${item.id}`, { method: "DELETE", customer, host });
  }
}

/** Create or reuse an address for the customer. Endpoint skips the envelope. */
export async function ensureAddress(
  customer: string = ALICE,
  host: string = TENANT_A_HOST,
  country: string = "SA",
): Promise<string> {
  const r = await call<{ id: string }>(`/customers/${customer}/addresses`, {
    method: "POST",
    customer,
    host,
    body: {
      label: "shipping",
      country,
      city: "Riyadh",
      street: "Test St 1",
      postalCode: "12345",
      isDefault: true,
    },
  });
  const id = r.body.data?.id ?? (r.body as unknown as { id?: string }).id;
  if (!id) throw new Error(`ensureAddress failed: ${r.status} ${JSON.stringify(r.body)}`);
  return id;
}

export async function ensurePaymentMethod(
  customer: string = ALICE,
  host: string = TENANT_A_HOST,
): Promise<string> {
  const r = await call<{ id: string }>(`/customers/${customer}/payment-methods`, {
    method: "POST",
    customer,
    host,
    body: {
      gatewayName: "mock",
      token: `tok_${uuid().slice(0, 8)}`,
      brand: "visa",
      lastFour: "4242",
      isDefault: true,
    },
  });
  const id = r.body.data?.id;
  if (!id) throw new Error(`ensurePaymentMethod failed: ${r.status} ${JSON.stringify(r.body)}`);
  return id;
}

export type ReadyCartOpts = {
  customer?: string;
  host?: string;
  sku?: string;
  quantity?: number;
  country?: string;
};

/**
 * Empty the cart, add one product, and bind addresses + payment method.
 * Returns a cart that's checkout-ready. The `country` controls the address
 * (used to exercise coupon country restrictions).
 */
export async function readyCart(opts: ReadyCartOpts = {}): Promise<Cart> {
  const customer = opts.customer ?? ALICE;
  const host = opts.host ?? TENANT_A_HOST;
  const sku = opts.sku ?? SKUS.widget;
  const quantity = opts.quantity ?? 1;
  const country = opts.country ?? "SA";

  await resetCart(customer, host);
  const product = await getProductBySku(sku, { customer, host });
  const addressId = await ensureAddress(customer, host, country);
  const paymentMethodId = await ensurePaymentMethod(customer, host);

  const add = await call<Cart>("/cart/items", {
    method: "POST",
    customer,
    host,
    body: { productId: product.id, quantity },
  });
  if (add.status !== 200) {
    throw new Error(`add item failed: ${add.status} ${JSON.stringify(add.body)}`);
  }
  await call("/cart/shipping-address", { method: "PUT", customer, host, body: { id: addressId } });
  await call("/cart/billing-address", { method: "PUT", customer, host, body: { id: addressId } });
  await call("/cart/payment-method", {
    method: "PUT",
    customer,
    host,
    body: { id: paymentMethodId },
  });

  const fresh = await call<Cart>("/cart", { customer, host });
  return fresh.body.data!;
}

export type CheckoutAttempt =
  | { ok: true; data: CheckoutData; status: number }
  | { ok: false; status: number; code?: string; detail?: string };

export async function attemptCheckout(
  customer: string,
  idempotencyKey: string,
  ifMatch?: number,
  host: string = TENANT_A_HOST,
): Promise<CheckoutAttempt> {
  const headers: Record<string, string> = { "Idempotency-Key": idempotencyKey };
  if (ifMatch !== undefined) headers["If-Match"] = String(ifMatch);
  const r = await call<CheckoutData>("/cart/checkout", {
    method: "POST",
    customer,
    host,
    headers,
    body: { paymentMetadata: {} },
  });
  if (r.status >= 200 && r.status < 300 && r.body.data) {
    return { ok: true, data: r.body.data, status: r.status };
  }
  return {
    ok: false,
    status: r.status,
    code: firstErrorCode(r),
    detail: r.body.errors?.[0]?.detail,
  };
}
