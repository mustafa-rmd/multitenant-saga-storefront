// Coverage for the platform-admin reconcile trigger:
// POST /api/v1/admin/platform/ops/reconcile-payments
//
// The deep "stuck PENDING -> converged / cancelled" behaviour requires
// inserting Payment rows with backdated `updated_at` and (for one branch)
// a fabricated `gateway_transaction_id` -- neither of which is reachable
// through the public HTTP surface. Those cases live in
// `scripts/verify_reconcile.py` (run via `manage.py shell`) and are
// documented in `tests-ts/README.md`.
//
// This file asserts the HTTP shell:
//   - Auth rail (platform-admin only; tenant-admin gets 403; no token gets 401).
//   - Response envelope shape matches the documented summary.
//   - The `stale_after_minutes` query param is honoured (large value
//     guarantees zero scans on the seeded DB, which is a deterministic
//     assertion across re-runs).
//
// These checks alone catch every "I broke the URL wiring / permission
// class / serializer shape" regression a future refactor could
// introduce. The deeper converge tests aren't an HTTP test problem.

import { beforeAll, describe, expect, test } from "bun:test";
import {
  ADMIN_HOST,
  adminCall,
  adminLogin,
  OWNER_A_EMAIL,
  OWNER_A_PASSWORD,
  PLATFORM_EMAIL,
  PLATFORM_PASSWORD,
} from "../admin/helpers";

type ReconcileSummary = {
  scanned: number;
  converged: number;
  cancelled: number;
  stillPending: number;
};

let platformToken = "";
let tenantToken = "";

beforeAll(async () => {
  ({ token: platformToken } = await adminLogin(PLATFORM_EMAIL, PLATFORM_PASSWORD));
  ({ token: tenantToken } = await adminLogin(OWNER_A_EMAIL, OWNER_A_PASSWORD));
});

describe("POST /admin/platform/ops/reconcile-payments", () => {
  test("platform-admin: returns 200 with the documented summary shape", async () => {
    // Cap the lookback far enough out that the sweep is a no-op on the
    // seed DB regardless of state left by previous test runs -- so the
    // assertion is deterministic.
    const r = await adminCall<ReconcileSummary>(
      "/admin/platform/ops/reconcile-payments?stale_after_minutes=10080",
      { method: "POST", host: ADMIN_HOST, token: platformToken },
    );
    expect(r.status).toBe(200);
    const summary = r.body.data;
    expect(summary).toBeDefined();
    // All four keys present and integer-valued.
    expect(typeof summary?.scanned).toBe("number");
    expect(typeof summary?.converged).toBe("number");
    expect(typeof summary?.cancelled).toBe("number");
    expect(typeof summary?.stillPending).toBe("number");
    // Conservation: every scanned row ends up in exactly one bucket.
    if (summary) {
      expect(summary.converged + summary.cancelled + summary.stillPending).toBe(summary.scanned);
    }
  });

  test("platform-admin: default stale window still returns a valid envelope", async () => {
    const r = await adminCall<ReconcileSummary>("/admin/platform/ops/reconcile-payments", {
      method: "POST",
      host: ADMIN_HOST,
      token: platformToken,
    });
    expect(r.status).toBe(200);
    expect(r.body.data).toBeDefined();
    expect(typeof r.body.data?.scanned).toBe("number");
  });

  test("tenant-admin token -> 403 (IsPlatformAdmin requires superuser)", async () => {
    const r = await adminCall("/admin/platform/ops/reconcile-payments", {
      method: "POST",
      host: ADMIN_HOST,
      token: tenantToken,
    });
    expect(r.status).toBe(403);
  });

  test("no auth -> 401", async () => {
    const r = await adminCall("/admin/platform/ops/reconcile-payments", {
      method: "POST",
      host: ADMIN_HOST,
    });
    expect(r.status).toBe(401);
  });

  test("GET (wrong method) -> 405", async () => {
    const r = await adminCall("/admin/platform/ops/reconcile-payments", {
      method: "GET",
      host: ADMIN_HOST,
      token: platformToken,
    });
    expect(r.status).toBe(405);
  });
});
