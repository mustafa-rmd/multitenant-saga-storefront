# tests-ts/k6 — load & stress scenarios

Five k6 TypeScript scripts that drive the local server over HTTP. They live
under `tests-ts/` so the k6 suite and the Bun integration suite share one
`node_modules` (with `@types/k6` for editor + typecheck) and one fixtures
file (`tests-ts/.fixtures.json`).

The Bun suite proves correctness end-to-end; this suite proves the same
properties hold under load (no 5xx, bounded latency, idempotency holds in
the face of real parallelism).

Run `make provision-fixtures` before any scenario to populate
`tests-ts/.fixtures.json`.

## Prerequisites

1. **k6 installed**
   - Windows: `winget install k6 --source winget` (or download from [k6.io/docs/get-started/installation](https://k6.io/docs/get-started/installation/))
   - macOS: `brew install k6`
   - Linux: see the k6 install docs (apt repo / snap / binary)

2. **The server is running** — `make run-all`. The dev `runserver` is
   single-threaded; for representative numbers run gunicorn instead:

   ```
   .venv/Scripts/python.exe -m gunicorn config.wsgi --workers 4 --bind 0.0.0.0:8000
   ```

3. **Fixtures are provisioned** — `make provision-fixtures`. The k6 scripts
   read `tests-ts/.fixtures.json` for tenant/customer IDs.

4. **Hosts file maps the demo subdomains** (one-time per machine):
   ```
   127.0.0.1   store-a.acme.test store-b.acme.test acme.acme.test
   ```

## Running

Each scenario is a standalone k6 script. Pick one and run it directly:

```
k6 run tests-ts/k6/scenarios/smoke.ts
k6 run tests-ts/k6/scenarios/browse-load.ts
k6 run tests-ts/k6/scenarios/cart-contention.ts
k6 run tests-ts/k6/scenarios/checkout-stress.ts
k6 run tests-ts/k6/scenarios/idempotency-storm.ts
```

Or via the Makefile (same commands, shorter to type):

```
make k6-smoke
make k6-browse
make k6-cart
make k6-checkout
make k6-idempotency
```

## What each scenario tests

| Scenario | Shape | Tests | Pass criteria |
|---|---|---|---|
| `smoke.ts` | 1 VU × 20 s | Server is up, `/products` and `/cart` reachable | p95 < 500 ms, ≥ 99 % checks pass |
| `browse-load.ts` | Ramp to 50 VUs over 2 min, GET `/products` | Read path: tenant resolution + RLS + serializer hot path | p95 < 400 ms, < 1 % failures |
| `cart-contention.ts` | 20 VUs hammer **one** customer's cart for 30 s | Cart `SELECT FOR UPDATE` row-lock serialisation; no deadlock, no 5xx | p95 add < 2 s, ≥ 95 % checks pass |
| `checkout-stress.ts` | Ramp to 3 VUs running full add → checkout journey (one VU per provisioned customer) | The whole saga: stock reservation, idempotency lookup, mock-gateway capture, invoice enqueue | p95 checkout < 3 s, ≥ 90 % checks pass |
| `idempotency-storm.ts` | 10 VUs fire one checkout each, **same** `Idempotency-Key` | One order wins, the rest replay it — no double-charge, no 5xx | every successful response carries the same `orderId` |

## Tuning

Each scenario reads peak/concurrency from an env var so you can stretch the
load without editing the file:

```
K6_BROWSE_PEAK=100      k6 run tests-ts/k6/scenarios/browse-load.ts
K6_CART_VUS=40          k6 run tests-ts/k6/scenarios/cart-contention.ts
K6_CHECKOUT_PEAK=30     k6 run tests-ts/k6/scenarios/checkout-stress.ts
K6_IDEMP_CONCURRENT=50  k6 run tests-ts/k6/scenarios/idempotency-storm.ts
```

Override the target server (defaults to `http://localhost:8000`):

```
ECOM_BASE_URL=http://staging.internal:8000 k6 run tests-ts/k6/scenarios/smoke.ts
```

## Interpreting results

k6 prints a per-scenario summary at the end. The two columns to read first:

- **`http_req_failed`** — anything > 0 needs investigation. The thresholds set
  in each script will exit non-zero on breach.
- **`http_req_duration{name:<endpoint>}`** — p(95) / p(99) per endpoint, tagged
  by the helper in `lib/api.ts`. Use these to track regressions across runs.

For the idempotency storm specifically, `grep 'orderId=' <run-output>` —
every line should carry the same UUID. Two distinct UUIDs means an
idempotency leak.

## TypeScript

The scripts are `.ts` and run directly through k6's built-in transformer
(no bundler / build step). Types come from `@types/k6` installed in
`tests-ts/node_modules/` — `tests-ts/k6/tsconfig.json` extends
`tests-ts/tsconfig.json` (one directory up) and uses the shared
`node_modules`, so there is only one dependency tree.

Type-check both suites with `make typecheck` — it now runs `tsc` against
`tests-ts/tsconfig.json` and then `tests-ts/k6/tsconfig.json`.

## Caveats

- **Mock gateway only.** The scenarios use the mock payment gateway
  (`PAYMENTS_ALLOW_MOCK_GATEWAY=True` in `.env`). Pointing them at `stripe`
  or `stripe_live` would put real-ish traffic on stripe-mock / api.stripe.com
  and isn't the point of these tests.
- **Dev server caveat.** Numbers from `manage.py runserver` aren't meaningful
  — it's single-threaded. Run gunicorn for any non-smoke run.
- **Cart growth in contention test.** `cart-contention.ts` keeps adding to
  one customer's cart for the duration of the run; the cart accumulates rows.
  That's intentional (it stresses the lock + the merge path). Reset with
  `tests-ts/` `resetCart` or restart Postgres afterwards.
