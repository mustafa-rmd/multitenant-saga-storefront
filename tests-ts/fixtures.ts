// Generated-fixture identifiers.
//
// Customer UUIDs are minted by the admin REST API when
// `tests-ts/provision_fixtures.ts` runs, then captured into
// `tests-ts/.fixtures.json` (gitignored). The four customer constants
// below load from that JSON; if the file is missing, the tests fail
// with a clear pointer to run the provisioner.
//
// Product SKUs and coupon codes are stable strings (they're the lookup
// key against the API), so they don't need to be captured per-run.

import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const FIXTURES_PATH = resolve(import.meta.dir, ".fixtures.json");

type Fixtures = {
  generatedAt: string;
  tenants: {
    a: { id: string; subdomain: string };
    b: { id: string; subdomain: string };
  };
  customers: {
    alice: string;
    charlie: string;
    diana: string;
    bob: string;
  };
};

function loadFixtures(): Fixtures {
  if (!existsSync(FIXTURES_PATH)) {
    throw new Error(
      `Missing ${FIXTURES_PATH}. ` +
        "Run `make provision-fixtures` (or `bun run provision` from tests-ts/) " +
        "after `make bootstrap` to populate it via the admin REST API.",
    );
  }
  return JSON.parse(readFileSync(FIXTURES_PATH, "utf-8")) as Fixtures;
}

const fx = loadFixtures();

// Storefront customer IDs — sent as X-Customer-Id by tests.
export const ALICE = process.env.ECOM_ALICE ?? fx.customers.alice;
export const CHARLIE = process.env.ECOM_CHARLIE ?? fx.customers.charlie;
export const DIANA = process.env.ECOM_DIANA ?? fx.customers.diana;
export const BOB = process.env.ECOM_BOB ?? fx.customers.bob;

// Tenant IDs (mostly used for cross-tenant assertions).
export const TENANT_A_ID = fx.tenants.a.id;
export const TENANT_B_ID = fx.tenants.b.id;

export const SKUS = {
  widget: "SA-WIDGET-01",
  gizmo: "SA-GIZMO-01",
  scarce: "SA-SCARCE-01",
  usd: "SA-USD-01",
} as const;

export const COUPONS = {
  welcome10: "WELCOME10",
  flat5: "FLAT5",
  cap100: "CAP100",
  min100k: "MIN100K",
  expired: "EXPIRED",
  notyet: "NOTYET",
  exhausted: "EXHAUSTED",
  aeOnly: "AEONLY",
  b2bOnly: "B2BONLY",
  usdFixed: "USDFIXED",
} as const;
