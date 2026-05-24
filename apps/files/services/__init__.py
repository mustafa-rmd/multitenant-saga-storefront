"""Public façade for the file-storage app.

Re-exports the object-storage primitives and the upload validator so
callers can write `from apps.files.services import save_bytes` instead
of reaching into the submodules. Matches the convention used by
`apps.orders.services`.
"""

from apps.files.services.object_storage import (
    delete,
    exists,
    save_bytes,
    save_uploaded_file,
    url_for,
)
from apps.files.services.upload_validation import validate_upload

__all__ = [
    "delete",
    "exists",
    "save_bytes",
    "save_uploaded_file",
    "url_for",
    "validate_upload",
]
