"""Upload / delete primary product images in the `media` S3-compatible bucket.

Domain shim over `apps.files.services` for the catalog app. Holds:

  - The per-product key template (`tenants/<t>/products/<p>/main.<ext>`)
  - The image-upload policy: allowed MIME types and the 5 MiB cap

The single "main" key per product means the upload endpoint is naturally
idempotent (re-upload overwrites in place), and replacing the format
(.png -> .webp) automatically supersedes the previous file.

Validation lives here (not in a serializer) because the upload comes in
as a single multipart `file` field rather than a JSON payload, and the
DRF ValidationError raised by the shared validator is the natural error
vehicle.
"""

from __future__ import annotations

from apps.files.services import (
    delete as _delete_object,
)
from apps.files.services import (
    save_uploaded_file,
    validate_upload,
)

MEDIA_STORAGE_ALIAS = "media"

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MiB

_KEY_TEMPLATE = "tenants/{tenant_id}/products/{product_id}/main.{ext}"


def upload_product_image(*, tenant_id, product_id, uploaded_file) -> str:
    """Validate, upload, return the object key (caller writes it to the DB)."""
    ext = validate_upload(
        uploaded_file,
        allowed_content_types=ALLOWED_CONTENT_TYPES,
        max_bytes=MAX_IMAGE_BYTES,
    )
    key = _KEY_TEMPLATE.format(tenant_id=tenant_id, product_id=product_id, ext=ext)
    return save_uploaded_file(alias=MEDIA_STORAGE_ALIAS, key=key, uploaded_file=uploaded_file)


def delete_product_image(key: str) -> None:
    """Best-effort delete; missing object is not an error."""
    _delete_object(alias=MEDIA_STORAGE_ALIAS, key=key)
