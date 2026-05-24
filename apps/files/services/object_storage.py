"""Thin wrapper over django-storages.

Centralises the `storages[alias].save(key, ContentFile(...))` pattern that
otherwise repeats across every file-storage call site, and gives a single
home for future cross-cutting concerns (metrics, structured logging,
presigned-URL generation, virus scanning).

Backends and bucket aliases are configured in `config/settings/base.py`
under `STORAGES`. This module is intentionally backend-agnostic -- the
same calls work against local filesystem storage, MinIO, or real AWS S3.

Domain consumers (invoices, product images, future avatars / B2B PO
attachments / export bundles) live in their owning app and call into
this module; the key-template convention and any per-resource policy
stay with the consumer.
"""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.core.files.storage import storages


def _basename(key: str) -> str:
    return key.rsplit("/", 1)[-1]


def save_bytes(
    *,
    alias: str,
    key: str,
    data: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    """Write `data` to bucket `alias` under `key`. Returns the actual key written.

    `filename` is the display name attached to the ContentFile -- some
    storages (and downstream tools) infer Content-Type from it. Defaults
    to the basename of `key`, which is what every existing caller wants.

    `content_type` overrides MIME-type detection. Without it, S3-style
    backends fall back to `mimetypes.guess_type(name)` which is correct
    for the common extensions (.pdf, .png, .jpg, .webp). Pass it
    explicitly when uploading blobs whose extension doesn't carry the
    type (e.g. opaque `.bin` exports).
    """
    name = filename or _basename(key)
    content = ContentFile(data, name=name)
    if content_type:
        content.content_type = content_type
    return storages[alias].save(key, content)


def save_uploaded_file(
    *,
    alias: str,
    key: str,
    uploaded_file,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    """Write a Django UploadedFile (multipart) to bucket `alias` under `key`.

    The upload is materialised in memory via `.read()`: Django's
    UploadedFile is a stream that the S3 backend can't always re-seek.
    For very large uploads, swap in a streaming helper -- not needed for
    the image / PDF / small-attachment shapes the system handles today.

    We `seek(0)` before `.read()` so a caller that already consumed the
    stream (content-type sniff, virus scan, magic-byte check) still gets
    a complete upload — without the seek, a previously-read stream would
    silently write zero bytes.

    Pass `content_type` to override the multipart-parsed Content-Type.
    """
    name = filename or _basename(key)
    uploaded_file.seek(0)
    content = ContentFile(uploaded_file.read(), name=name)
    if content_type:
        content.content_type = content_type
    elif getattr(uploaded_file, "content_type", None):
        # Carry the multipart-parsed Content-Type onto the ContentFile so
        # S3-backed storages persist it instead of guessing from filename.
        content.content_type = uploaded_file.content_type
    return storages[alias].save(key, content)


def url_for(*, alias: str, key: str) -> str:
    """Public or presigned URL for `key`, per the backend's config.

    Whether the URL is signed is controlled by `AWS_QUERYSTRING_AUTH` on
    the backend (False in dev → stable public URL, True in prod → signed
    link). Callers don't need to know which mode is active.
    """
    return storages[alias].url(key)


def delete(*, alias: str, key: str) -> bool:
    """Best-effort delete. Returns True if a delete was issued, False if missing.

    Idempotent by design -- callers can re-issue a delete on retry
    without worrying about whether the previous attempt landed.
    """
    if not key:
        return False
    storage = storages[alias]
    if not storage.exists(key):
        return False
    storage.delete(key)
    return True


def exists(*, alias: str, key: str) -> bool:
    return storages[alias].exists(key)
