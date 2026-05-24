// Coverage for the admin-login rate limits.
//
// `POST /admin/auth/login` is throttled per-IP (default 60/min) AND per-email
// (default 30/min). Either limit can trip first; this test only asserts that
// SOME 429 surfaces within a single fast burst -- the exact attempt count
// depends on which limit hits first and how much budget earlier tests used
// from 127.0.0.1.
//
// Uses a unique email so other tests' login counters aren't affected, and
// uses obviously-wrong credentials so successful auth never short-circuits.

import { describe, expect, test } from "bun:test";
import { firstErrorCode } from "../helpers";
import { adminCall } from "./helpers";

describe("POST /admin/auth/login rate limit", () => {
  test("returns 429 rate_limited with Retry-After when the limit is exceeded", async () => {
    const email = `throttle-${crypto.randomUUID()}@example.test`;

    let throttledStatus: number | undefined;
    let throttledBody:
      | { errors?: Array<{ code?: string; meta?: Record<string, unknown> }> }
      | undefined;
    let retryAfter: string | null = null;

    // 120 fast attempts is enough to exceed the dev-default 100/min email
    // rate on a unique address, even if some IP budget has been consumed by
    // earlier suites. Production deployments tighten both rates via env.
    for (let i = 0; i < 120; i++) {
      const r = await adminCall("/admin/auth/login", {
        method: "POST",
        body: { email, password: "definitely-wrong" },
      });
      if (r.status === 429) {
        throttledStatus = r.status;
        throttledBody = r.body;
        retryAfter = r.raw.headers.get("Retry-After");
        break;
      }
      // Bail loudly if anything other than 401 or 429 shows up -- means
      // the request shape itself is bad and the test would silently pass.
      expect([401, 429]).toContain(r.status);
    }

    expect(throttledStatus).toBe(429);
    expect(firstErrorCode({ body: throttledBody! } as never)).toBe("rate_limited");
    // Retry-After header is set when DRF's Throttled.wait is known.
    expect(retryAfter).toBeTruthy();
    // The error meta carries the same value for clients that don't parse headers.
    const meta = throttledBody!.errors?.[0]?.meta;
    expect(meta && typeof meta.retryAfterSeconds === "number").toBe(true);
  });
});
