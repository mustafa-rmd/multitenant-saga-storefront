"""Validation rules for multipart uploads (size cap + content-type allowlist).

Raises DRF `serializers.ValidationError` so the standard exception
handler turns it into the `validation_error` HTTP response envelope.

Callers pass their own `allowed_content_types` mapping so each consumer
keeps its own policy (images vs PDFs vs ZIPs) -- this module owns the
*mechanism*, not the *policy*. That keeps the file-storage app
domain-agnostic.
"""

from __future__ import annotations

from rest_framework import serializers


def validate_upload(
    uploaded_file,
    *,
    allowed_content_types: dict[str, str],
    max_bytes: int,
) -> str:
    """Validate size + content-type. Returns the extension for the content-type.

    `allowed_content_types` maps MIME type -> file extension, e.g.
    `{"image/png": "png", "image/jpeg": "jpg"}`. Returning the extension
    means the caller doesn't have to keep a second copy of the same map
    to build its storage key.

    Raises `serializers.ValidationError({"file": ...})` on any failure so
    DRF surfaces the right field pointer in the error envelope.
    """
    if uploaded_file.size > max_bytes:
        raise serializers.ValidationError(
            {"file": f"Upload exceeds the {max_bytes // (1024 * 1024)} MiB limit."}
        )
    content_type = (uploaded_file.content_type or "").lower()
    if content_type not in allowed_content_types:
        raise serializers.ValidationError(
            {
                "file": (
                    f"Unsupported content type {content_type!r}. "
                    f"Allowed: {', '.join(sorted(allowed_content_types))}."
                )
            }
        )
    return allowed_content_types[content_type]
