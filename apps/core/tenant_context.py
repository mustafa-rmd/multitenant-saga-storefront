"""
Tenant context. Stored in a ContextVar so it propagates correctly across
async boundaries (asyncio tasks, Django async views, Celery's async modes).

Using threading.local would also work for sync code but breaks under
asyncio. ContextVars are the modern correct choice.
"""

from contextvars import ContextVar
from uuid import UUID

_current_tenant: ContextVar[UUID | None] = ContextVar("current_tenant", default=None)


def get_current_tenant_id() -> UUID | None:
    """Return the tenant_id for the current request/task, or None if unset."""
    return _current_tenant.get()


def set_current_tenant_id(tenant_id: UUID | None):
    """Set the tenant and return a token that can be passed to reset()."""
    return _current_tenant.set(tenant_id)


def reset_current_tenant_id(token) -> None:
    """Restore the previous tenant context. Always call this in a `finally`."""
    _current_tenant.reset(token)


class tenant_context:
    """
    Context manager for explicitly setting tenant in non-request code
    (Celery tasks, management commands, tests).

        with tenant_context(tenant_id):
            ...do stuff...
    """

    def __init__(self, tenant_id: UUID | None):
        self.tenant_id = tenant_id
        self._token = None

    def __enter__(self):
        self._token = set_current_tenant_id(self.tenant_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        reset_current_tenant_id(self._token)
        return False
