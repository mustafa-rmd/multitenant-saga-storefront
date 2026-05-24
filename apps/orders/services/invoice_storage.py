"""Upload an invoice PDF to the configured object store and return its URL.

Domain shim over `apps.files.services.object_storage`. Holds the
invoice key-template convention and the choice to return the URL
(callers store it on the Invoice row and serve it back to customers
without a second storage hit).

Backend selection is driven by Django's `STORAGES['invoices']` config
(see `config/settings/base.py`). In local dev that points at MinIO via
`AWS_S3_ENDPOINT_URL`; in production the same code works against real
AWS S3 by clearing that env var and pointing the AWS region + creds at
the prod account.

URL semantics: when `AWS_QUERYSTRING_AUTH=False` (the dev default), the
bucket is public-read and `.url(key)` returns a stable, unsigned URL the
customer's browser can fetch directly. Flip it to `True` for prod and
URLs become short-lived presigned links.
"""

from __future__ import annotations

from apps.files.services import save_bytes, url_for

_INVOICE_STORAGE_ALIAS = "invoices"
_OBJECT_KEY_TEMPLATE = "tenants/{tenant_id}/invoices/{invoice_id}.pdf"


def upload_invoice_pdf(*, tenant_id, invoice_id, pdf_bytes: bytes) -> str:
    """Write `pdf_bytes` to the `invoices` bucket and return its URL."""
    key = _OBJECT_KEY_TEMPLATE.format(tenant_id=tenant_id, invoice_id=invoice_id)
    saved_key = save_bytes(alias=_INVOICE_STORAGE_ALIAS, key=key, data=pdf_bytes)
    return url_for(alias=_INVOICE_STORAGE_ALIAS, key=saved_key)
