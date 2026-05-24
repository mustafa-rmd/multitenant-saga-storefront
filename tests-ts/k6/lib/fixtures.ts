// Loads tests-ts/.fixtures.json at init time. k6's open() is only available
// at module init context, so we read it once here and re-export the values.
//
// Run `make provision-fixtures` before any k6 scenario — the file is gitignored
// and recreated every run by tests-ts/provision_fixtures.ts.

export interface TenantRef {
  id: string;
  subdomain: string;
  host: string;
}

export interface Fixtures {
  generatedAt: string;
  tenants: {
    a: { id: string; subdomain: string };
    b: { id: string; subdomain: string };
  };
  customers: {
    alice: string;
    bob: string;
    charlie: string;
    diana: string;
  };
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  price: string;
  currency: string;
  stockQuantity: number;
  availableQuantity: number;
  isActive: boolean;
}

const raw = open("../../.fixtures.json");
const fx = JSON.parse(raw) as Fixtures;

export const TENANT_A: TenantRef = {
  id: fx.tenants.a.id,
  subdomain: fx.tenants.a.subdomain,
  host: `${fx.tenants.a.subdomain}.acme.test`,
};

export const TENANT_B: TenantRef = {
  id: fx.tenants.b.id,
  subdomain: fx.tenants.b.subdomain,
  host: `${fx.tenants.b.subdomain}.acme.test`,
};

export const CUSTOMERS = fx.customers;
export const CUSTOMER_LIST: string[] = Object.values(fx.customers);

// Stable SKUs from tests-ts/fixtures.ts. Kept in sync manually because k6
// can't import .ts files from tests-ts (different runtime); if you rename in
// provision_fixtures.ts, rename here too.
export const SKUS = {
  widget: "SA-WIDGET-01",
  gizmo: "SA-GIZMO-01",
  scarce: "SA-SCARCE-01",
} as const;

export function findProductBySku(products: Product[], sku: string): Product {
  const p = products.find((x) => x.sku === sku);
  if (!p) throw new Error(`Product not found in catalogue: ${sku}`);
  return p;
}
