"""Local development settings."""

from .base import *  # noqa: F403, F401

DEBUG = True

# Allow all CORS origins in dev. In prod this should be configured properly.
ALLOWED_HOSTS = ["*"]

# Bump `apps.*` to DEBUG in dev unless the developer pinned a level via env.
# The base file declares `apps` at APPS_LOG_LEVEL (env, default INFO); we
# only override when the env var wasn't set.
import os  # noqa: E402

if "APPS_LOG_LEVEL" not in os.environ:
    LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405

# === Dev productivity apps ===
# django-extensions adds shell_plus / runserver_plus / graph_models.
# django-debug-toolbar adds the SQL/cache/template inspection panel and is
# scoped to local.py so it can never load in production even if DEBUG is
# accidentally true (production uses base.py + a prod settings module).
INSTALLED_APPS += [  # noqa: F405
    "django_extensions",
    "debug_toolbar",
]

# DebugToolbarMiddleware should sit as early as possible so it sees the full
# request/response. Place it right after WhiteNoise (index 2).
MIDDLEWARE.insert(3, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

INTERNAL_IPS = ["127.0.0.1", "::1"]

# The default show-toolbar check requires REMOTE_ADDR to be in INTERNAL_IPS,
# which fails inside Docker (the container sees the bridge gateway IP, not
# 127.0.0.1). Override to gate on DEBUG only — safe because the app is
# scoped to local.py and never loaded in prod.
#
# Also skip the operator dashboard at /dashboard/: it's a token-authed SPA
# that doesn't authenticate against the Django session the toolbar relies
# on, so the toolbar's /__debug__/history_sidebar/ polling 401s in the
# browser console and looks like a real bug.
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG and not request.path.startswith("/dashboard/"),
}
