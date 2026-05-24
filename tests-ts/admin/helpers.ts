// Admin-specific helpers. Builds on the storefront `call()` and adds a
// token-aware variant for the admin REST surface. Two-rail auth: storefront
// uses X-Customer-Id, admin uses `Authorization: Token <key>`.

import {
  API,
  type CallOptions,
  type Envelope,
  type Response as RpcResponse,
  TENANT_A_HOST,
  TENANT_B_HOST,
} from "../helpers";

export const ADMIN_HOST = process.env.ECOM_ADMIN_HOST ?? "admin.acme.test";
export { TENANT_A_HOST, TENANT_B_HOST };

export const PLATFORM_EMAIL = process.env.ECOM_PLATFORM_EMAIL ?? "platform@acme.test";
export const PLATFORM_PASSWORD = process.env.ECOM_PLATFORM_PASSWORD ?? "platform-pass";
export const OWNER_A_EMAIL = process.env.ECOM_OWNER_A_EMAIL ?? "owner-a@store-a.test";
export const OWNER_A_PASSWORD = process.env.ECOM_OWNER_A_PASSWORD ?? "owner-a-pass";
export const OWNER_B_EMAIL = process.env.ECOM_OWNER_B_EMAIL ?? "owner-b@store-b.test";
export const OWNER_B_PASSWORD = process.env.ECOM_OWNER_B_PASSWORD ?? "owner-b-pass";

export type AdminCallOptions = Omit<CallOptions, "customer"> & {
  token?: string;
  body?: unknown;
};

/** Issue an HTTP call to an admin endpoint. Sends `Authorization: Token <k>`
 *  when `token` is provided; never sends `X-Customer-Id`. */
export async function adminCall<T = unknown>(
  path: string,
  opts: AdminCallOptions = {},
): Promise<RpcResponse<T>> {
  const method = opts.method ?? "GET";
  const host = opts.host ?? ADMIN_HOST;
  const headers: Record<string, string> = {
    Host: host,
    Accept: "application/json",
    ...opts.headers,
  };
  if (opts.token) headers.Authorization = `Token ${opts.token}`;
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

export type LoginUser = {
  id: number;
  email: string;
  isSuperuser: boolean;
  memberships: Array<{ tenantId: string; tenantSubdomain: string; role: string }>;
};

export type LoginData = { token: string; expiresAt: string | null; user: LoginUser };

/** Log in and return the issued admin token + user payload. Throws if 4xx. */
export async function adminLogin(
  email: string,
  password: string,
  host: string = ADMIN_HOST,
): Promise<LoginData> {
  const r = await adminCall<LoginData>("/admin/auth/login", {
    method: "POST",
    host,
    body: { email, password },
  });
  if (r.status !== 200 || !r.body.data) {
    throw new Error(`login failed for ${email}: ${r.status} ${JSON.stringify(r.body)}`);
  }
  return r.body.data;
}
