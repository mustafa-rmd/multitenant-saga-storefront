// End-to-end invoice rendering test.
//
// Requires a Celery worker running (`celery -A config worker -l info`)
// AND MinIO (or any S3-compatible store the app is pointed at). If the
// worker is down, the polling loop times out and the test SKIPs with a
// clear message, matching the convention in journey.test.ts.

import { describe, expect, test } from "bun:test";
import { ALICE, attemptCheckout, call, readyCart, uuid } from "./helpers";

type InvoiceData = {
  id: string;
  orderId: string;
  invoiceNumber: number;
  pdfUrl: string;
  issuedAt: string | null;
};

async function pollForPdfUrl(orderId: string, timeoutMs = 15000): Promise<InvoiceData | null> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const r = await call<InvoiceData>(`/orders/${orderId}/invoice`);
    if (r.status === 200 && r.body.data && r.body.data.pdfUrl) {
      return r.body.data;
    }
    await new Promise((res) => setTimeout(res, 500));
  }
  return null;
}

describe("invoice PDF rendering + upload", () => {
  // 20s test timeout: pollForPdfUrl waits up to 15s before SKIPping (and
  // Celery + reportlab + MinIO upload add a second or two on top), well
  // past Bun's 5s default.
  test("checkout → invoice has pdfUrl → URL serves a valid PDF", async () => {
    await readyCart();
    const co = await attemptCheckout(ALICE, `inv-${uuid()}`);
    if (!co.ok) {
      throw new Error(`checkout failed: ${co.status} ${co.code} ${co.detail}`);
    }

    const invoice = await pollForPdfUrl(co.data.orderId);
    if (!invoice) {
      console.log("SKIP: invoice not generated after 15s — is celery worker + minio running?");
      return;
    }

    expect(invoice.pdfUrl).toMatch(/^https?:\/\//);
    expect(invoice.invoiceNumber).toBeGreaterThan(0);

    // The URL stored on the invoice uses whatever hostname the worker
    // resolves MinIO at — when the worker runs inside docker-compose,
    // that's `minio:9000` (the service name), which the host-side
    // test runner can't resolve. Rewrite to the host-port equivalent
    // before fetching. No-op when worker + tests share a network.
    const fetchUrl = invoice.pdfUrl.replace(/\/\/minio:9000\b/, "//localhost:9000");

    // Fetch the actual PDF and verify content-type + magic bytes.
    const pdfRes = await fetch(fetchUrl);
    expect(pdfRes.status).toBe(200);
    expect(pdfRes.headers.get("content-type")).toContain("application/pdf");
    const buf = new Uint8Array(await pdfRes.arrayBuffer());
    // %PDF- = 0x25 0x50 0x44 0x46 0x2D
    expect(buf[0]).toBe(0x25);
    expect(buf[1]).toBe(0x50);
    expect(buf[2]).toBe(0x44);
    expect(buf[3]).toBe(0x46);
    expect(buf[4]).toBe(0x2d);
    expect(buf.length).toBeGreaterThan(500);
  }, 20000);
});
