"""
Core model machinery for tenant isolation.

Exports:
- `TenantScopedModel` — abstract base. UUID PK, FK to Tenant, timestamps,
  auto-sets `tenant_id` from the contextvar on save.
- `TenantManager` — default `objects` manager on every TenantScopedModel.
  Auto-filters by the current tenant; fail-closed (`.none()`) when no
  tenant context is set.
- `UnscopedManager` — opt-in escape hatch surfaced as `all_objects`.
  Grep for usage to audit every cross-tenant query.

The two-manager pattern is deliberate: defaults are safe, the escape
hatch is explicit and named for searchability.
"""

from apps.core.models.tenant_manager import TenantManager
from apps.core.models.tenant_scoped_model import TenantScopedModel
from apps.core.models.unscoped_manager import UnscopedManager

__all__ = ["TenantManager", "UnscopedManager", "TenantScopedModel"]
