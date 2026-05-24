// HTTP helpers for the k6 stress scenarios. Mirrors tests-ts/helpers.ts in
// shape — same Host-header tenant routing, same X-Customer-Id auth, same
// camelCase wire format.

import http, { type RefinedResponse, type ResponseType } from "k6/http";

export const BASE = __ENV.ECOM_BASE_URL || "http://localhost:8000";
export const API = `${BASE}/api/v1`;

export type K6Response = RefinedResponse<ResponseType | undefined>;

export interface HeaderOpts {
  host: string;
  customer?: string;
  extra?: Record<string, string>;
}

// RFC-4122 v4 — sufficient for idempotency keys and correlation IDs.
// k6 doesn't expose crypto.randomUUID() across all versions, so we roll one.
export function uuid(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function headers({ host, customer, extra }: HeaderOpts): Record<string, string> {
  const h: Record<string, string> = {
    Host: host,
    Accept: "application/json",
    "Content-Type": "application/json",
    ...(extra || {}),
  };
  if (customer) h["X-Customer-Id"] = customer;
  return h;
}

type Tags = Record<string, string>;

// ---------------------------------------------------------------------------
// Storefront endpoints
// ---------------------------------------------------------------------------

export function getProducts(host: string, customer: string, tags?: Tags): K6Response {
  return http.get(`${API}/products`, {
    headers: headers({ host, customer }),
    tags: tags || { name: "products_list" },
  });
}

export function getCart(host: string, customer: string, tags?: Tags): K6Response {
  return http.get(`${API}/cart`, {
    headers: headers({ host, customer }),
    tags: tags || { name: "cart_get" },
  });
}

export function addToCart(
  host: string,
  customer: string,
  productId: string,
  quantity: number,
  tags?: Tags,
): K6Response {
  return http.post(`${API}/cart/items`, JSON.stringify({ productId, quantity }), {
    headers: headers({ host, customer }),
    tags: tags || { name: "cart_add" },
  });
}

export function setShippingAddress(host: string, customer: string, addressId: string): K6Response {
  return http.put(`${API}/cart/shipping-address`, JSON.stringify({ id: addressId }), {
    headers: headers({ host, customer }),
    tags: { name: "cart_set_shipping" },
  });
}

export function setBillingAddress(host: string, customer: string, addressId: string): K6Response {
  return http.put(`${API}/cart/billing-address`, JSON.stringify({ id: addressId }), {
    headers: headers({ host, customer }),
    tags: { name: "cart_set_billing" },
  });
}

export function setPaymentMethod(
  host: string,
  customer: string,
  paymentMethodId: string,
): K6Response {
  return http.put(`${API}/cart/payment-method`, JSON.stringify({ id: paymentMethodId }), {
    headers: headers({ host, customer }),
    tags: { name: "cart_set_payment_method" },
  });
}

export function checkout(
  host: string,
  customer: string,
  idempotencyKey: string,
  tags?: Tags,
): K6Response {
  return http.post(`${API}/cart/checkout`, JSON.stringify({ paymentMetadata: {} }), {
    headers: headers({
      host,
      customer,
      extra: { "Idempotency-Key": idempotencyKey },
    }),
    tags: tags || { name: "checkout" },
  });
}

// ---------------------------------------------------------------------------
// One-time-per-customer setup (called from scenario setup())
// ---------------------------------------------------------------------------

interface EnvelopeWithId {
  data?: { id?: string };
  id?: string;
}

export function ensureAddress(host: string, customer: string, country?: string): string {
  const res = http.post(
    `${API}/customers/${customer}/addresses`,
    JSON.stringify({
      label: "shipping",
      country: country || "SA",
      city: "Riyadh",
      street: "Test St 1",
      postalCode: "12345",
      isDefault: true,
    }),
    { headers: headers({ host, customer }) },
  );
  const body = res.json() as EnvelopeWithId | null;
  const id = body?.data?.id ?? body?.id;
  if (!id) {
    throw new Error(`ensureAddress failed for ${customer}: status=${res.status} body=${res.body}`);
  }
  return id;
}

export function ensurePaymentMethod(host: string, customer: string): string {
  const res = http.post(
    `${API}/customers/${customer}/payment-methods`,
    JSON.stringify({
      gatewayName: "mock",
      token: `tok_${uuid().slice(0, 8)}`,
      brand: "visa",
      lastFour: "4242",
      isDefault: true,
    }),
    { headers: headers({ host, customer }) },
  );
  const body = res.json() as EnvelopeWithId | null;
  const id = body?.data?.id;
  if (!id) {
    throw new Error(
      `ensurePaymentMethod failed for ${customer}: status=${res.status} body=${res.body}`,
    );
  }
  return id;
}

// Prime the cart for a customer: one item + bound addresses + payment method.
// Returns { addressId, paymentMethodId } so callers can re-bind in subsequent
// iterations after a checkout converts the cart.
export interface CustomerSetup {
  addressId: string;
  paymentMethodId: string;
}

export function primeCart(
  host: string,
  customer: string,
  productId: string,
  quantity?: number,
): CustomerSetup {
  const addressId = ensureAddress(host, customer);
  const paymentMethodId = ensurePaymentMethod(host, customer);
  addToCart(host, customer, productId, quantity || 1);
  setShippingAddress(host, customer, addressId);
  setBillingAddress(host, customer, addressId);
  setPaymentMethod(host, customer, paymentMethodId);
  return { addressId, paymentMethodId };
}
