"""
Base Django settings. Local and test settings inherit from this.

Reads config from environment variables (12-factor style) so the same
image can run in any environment. In local dev, a .env file at the repo
root is auto-loaded; in deployed environments, real env vars take
precedence (environ.Env.read_env never overrides existing keys).
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env()

_env_file = BASE_DIR / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file))

# === Core ===
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

# === Applications ===
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "django_filters",
    "django_celery_beat",
    "storages",
]

LOCAL_APPS = [
    "apps.core",
    "apps.files",
    "apps.tenants",
    "apps.catalog",
    "apps.customers",
    "apps.coupons",
    "apps.payments",
    "apps.carts",
    "apps.orders",
    "apps.iam",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# === Middleware ===
# Order matters! See apps/core/middleware/__init__.py for the rationale.
MIDDLEWARE = [
    # First: stamp a request id on the contextvar before anything can log.
    # Tenant/auth middleware that errors out still produces log lines tagged
    # with the same id the client sees in `X-Request-ID`/`meta.request_id`.
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves collected static files directly from gunicorn/uvicorn,
    # so the prod container does not need a separate nginx in front for /static/.
    # Must sit immediately after SecurityMiddleware per WhiteNoise docs.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Translate JSON keys at the wire boundary: camelCase outside, snake_case
    # inside. Placed near the top so it sees the final rendered response on
    # the way out and transforms the raw body before tenant/auth see it on
    # the way in (those only read headers, so order is for clarity).
    "apps.core.middleware.CamelCaseMiddleware",
    # 1. Resolve tenant from subdomain into ContextVar.
    # 2. Open the DB session GUC (SET LOCAL app.current_tenant) so all downstream
    #    queries on the RLS-forced app_user connection can see rows for this tenant.
    # 3. Resolve the Customer row from X-Customer-Id (RLS-scoped, so cross-tenant
    #    customer IDs return 404, not the wrong row).
    "apps.core.middleware.TenantResolverMiddleware",
    "apps.core.middleware.TenantDBSessionMiddleware",
    "apps.core.middleware.CustomerAuthMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# === Databases ===
# Two configurations against the same physical Postgres:
#   default -- uses app_user, RLS is enforced
#   admin   -- uses app_admin, BYPASSRLS, used by Celery and admin commands
#
# ATOMIC_REQUESTS wraps every view in a transaction; that's what makes
# `SET LOCAL app.current_tenant` work for the duration of a request.
DATABASES = {
    "default": {
        **env.db("DATABASE_URL"),
        "ATOMIC_REQUESTS": True,
        "CONN_MAX_AGE": 60,
    },
    "admin": {
        **env.db("DATABASE_ADMIN_URL"),
        "ATOMIC_REQUESTS": False,
        "CONN_MAX_AGE": 60,
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# === Internationalization ===
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# === Static files ===
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# === DRF ===
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # CustomerAuthMiddleware resolves the Customer from X-Customer-Id;
        # this class just bridges the middleware-set user into DRF's lazy
        # request.user property so permissions see it.
        "apps.core.authentication.MiddlewareCustomerAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.core.permissions.IsAuthenticatedCustomer",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.EnvelopePagination",
    "PAGE_SIZE": 20,
    # django-filter wired in globally. Views opt in by declaring `filterset_class`
    # or `filterset_fields`; views without either are unaffected.
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Acme Cart API",
    "DESCRIPTION": (
        "Multi-tenant cart and checkout system. Proof-of-concept for the Acme "
        "coding assignment.\n\n"
        "## Authentication\n\n"
        "Every authenticated request carries `X-Customer-Id` (a Customer UUID). "
        "In production an upstream identity-aware proxy (Cloudflare Access, an "
        "API gateway with JWT validation, an OIDC sidecar) validates the user "
        "and injects this header; in local/QA you paste a UUID directly via the "
        "**Authorize** button.\n\n"
        "Customers are created via the tenant-admin endpoint "
        "`POST /api/v1/admin/customers`. The Bun test fixtures provisioned "
        "by `tests-ts/provision_fixtures.ts` include Alice + Charlie on "
        "store-a and Bob on store-b; their UUIDs are written to "
        "`tests-ts/.fixtures.json`. The customer must belong to the "
        "resolved tenant; using Alice's UUID against store-b returns "
        "`401 customer_not_found`.\n\n"
        "## Tenant routing\n\n"
        "The tenant is resolved from the request's subdomain. Pick a tenant "
        "from the **Servers** dropdown above. For local development without "
        "editing your hosts file, the plain `http://localhost:8000` entry "
        "falls back to `DEV_DEFAULT_TENANT_SUBDOMAIN` (default `store-a`) when "
        "`DJANGO_DEBUG=True`. The fallback is silently ignored in production.\n\n"
        "Two endpoints are exempt from tenant resolution:\n"
        "- `GET /api/v1/health` — liveness check\n"
        "- `POST /api/v1/webhooks/payments/{gateway}` — tenant resolved from "
        "`gateway_transaction_id` instead\n\n"
        "## Response envelope\n\n"
        'Success: `{ "data": {...}, "meta": { "request_id", "version" } }`\n\n'
        'Error: `{ "errors": [{ "code", "detail", "meta" }], "meta": {...} }`\n\n'
        "A few endpoints (single-instance `RetrieveAPIView` / `CreateAPIView`) "
        "currently return the bare model. Clients should accept both shapes: "
        "`id = body.data?.id ?? body.id`.\n\n"
        "## Idempotency\n\n"
        "`POST /cart/checkout` **requires** an `Idempotency-Key` header. "
        "Retries with the same key return the same order without re-charging "
        "the payment method. Defense is layered at three levels: app "
        "short-circuit, a unique DB constraint on `Order.idempotency_key`, and "
        "the gateway's native idempotency cache.\n\n"
        "## Optimistic concurrency\n\n"
        "Cart mutations are pragmatic (concurrent `+` clicks serialize via "
        "`SELECT FOR UPDATE` and yield the expected quantity). Checkout is "
        "strict: pass `If-Match: <cart.version>` to fail fast on a stale view "
        "with `409 cart_version_conflict`.\n\n"
        "## Cart model\n\n"
        "One cart per customer, persistent, lazy-created on first item add. "
        "There is no `cart_id` in any URL — the cart is implicit, resolved "
        "from `X-Customer-Id` + the tenant. The cart's currency locks in on "
        "first add; cross-currency baskets are rejected with "
        "`409 currency_mismatch`.\n\n"
        "## Errors\n\n"
        "Common error codes you'll see while exploring: `tenant_required`, "
        "`tenant_not_found`, `customer_not_found`, `idempotency_key_required`, "
        "`currency_mismatch`, `insufficient_stock`, `cart_not_checkout_ready`, "
        "`cart_version_conflict`, `coupon_min_not_met`, `coupon_expired`, "
        "`payment_failed`. See `README.md` for the full table with HTTP "
        "statuses."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # CamelCaseMiddleware rewrites bodies on the wire; this hook makes the
    # OpenAPI schema (and therefore Swagger) match. The enums hook is the
    # drf-spectacular default and must be re-listed when overriding.
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "apps.core.spectacular_hooks.camelize_schema_properties",
    ],
    # Tenant selector in Swagger UI. Requires hosts file entries:
    #   127.0.0.1 store-a.acme.test store-b.acme.test acme.acme.test
    # The plain localhost entry falls back to DEV_DEFAULT_TENANT_SUBDOMAIN.
    "SERVERS": [
        {"url": "http://localhost:8000", "description": "localhost (fallback tenant)"},
        {"url": "http://store-a.acme.test:8000", "description": "Tenant: store-a"},
        {"url": "http://store-b.acme.test:8000", "description": "Tenant: store-b"},
        {"url": "http://acme.acme.test:8000", "description": "Tenant: acme"},
        {"url": "http://admin.acme.test:8000", "description": "Platform admin (no tenant)"},
    ],
    # Exposes X-Customer-Id as an "Authorize" field in Swagger UI for storefront
    # endpoints; TokenAuth for the admin REST surface. Storefront and admin run
    # on separate auth rails — they don't share credentials and don't impersonate.
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "CustomerId": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Customer-Id",
                "description": (
                    "Customer UUID. Set by the upstream identity proxy in "
                    "production; in dev/QA, paste a Customer UUID."
                ),
            },
            "TokenAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": (
                    "Admin API token issued by `POST /api/v1/admin/auth/login`. "
                    "Send as `Token <key>` (note the leading `Token ` prefix). "
                    "Used by tenant-admin and platform-admin endpoints under "
                    "`/api/v1/admin/`; not accepted by storefront endpoints."
                ),
            },
        }
    },
    "SECURITY": [{"CustomerId": []}, {"TokenAuth": []}],
}

# === Celery ===
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
# Acks-late + reject-on-worker-lost is the durable choice for financial work
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
# Periodic tasks (coupon expiry sweeps, invoice retries, etc.) are configured
# from the Django admin via django-celery-beat instead of a static
# CELERY_BEAT_SCHEDULE dict — schedules can be paused/edited without redeploys.
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# === Stripe (gateway points to mock server in local/test) ===
STRIPE_API_BASE = env("STRIPE_API_BASE", default="")
STRIPE_UPLOAD_API_BASE = env("STRIPE_UPLOAD_API_BASE", default="")

# === Cache ===
# Backed by Redis so rate-limit + throttle state survives across (a) multiple
# gunicorn / uvicorn workers in production, and (b) Django's autoreloader in
# dev -- which on Windows tends to clear LocMem caches more aggressively than
# you'd expect, making the login throttle look broken when it isn't.
CACHES = {
    "default": {
        # django-redis exposes pipelines, distributed locks, and SCAN-based
        # pattern deletes (`cache.delete_pattern("throttle:*")`), which the
        # vanilla Django backend does not. Same Redis instance / LOCATION.
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}

# === Admin auth ===
# Token TTL: how long an issued admin token is valid before
# `ExpiringTokenAuthentication` starts rejecting it as expired. The login
# endpoint rotates the token (deletes the old, mints a new one), so a leaked
# older token also becomes invalid as soon as the legitimate user re-auths.
# Set to 0 to disable expiry entirely (not recommended outside tests).
ADMIN_TOKEN_TTL_SECONDS = env.int("ADMIN_TOKEN_TTL_SECONDS", default=8 * 60 * 60)

# Login rate limits, applied at `POST /admin/auth/login`. Defaults are
# deliberately liberal because the Bun test suite makes ~30-50 admin logins
# from 127.0.0.1 per run across 14+ parallel test files, all sharing the same
# IP bucket. The auth-throttle test deliberately bursts >100 to trip the
# limit on a unique email, demonstrating the feature still works.
#
# Production MUST override both in env -- recommended tight values are
# "10/min" (IP) and "5/min" (email). The defaults here protect against
# nothing useful at the chosen ceilings; they exist so the throttling code
# path is always exercised and Redis state is populated, not as a real
# defence in dev.
ADMIN_LOGIN_THROTTLE_RATE_IP = env("ADMIN_LOGIN_THROTTLE_RATE_IP", default="200/min")
ADMIN_LOGIN_THROTTLE_RATE_EMAIL = env("ADMIN_LOGIN_THROTTLE_RATE_EMAIL", default="100/min")

# === Payments — feature gates ===
# The `mock` gateway is a fully-functional PaymentGateway implementation used by
# the dev seed and the Bun test suite. It must never be reachable in production:
# a tenant with a leftover `mock` config could otherwise complete checkouts
# without any real funds moving. This flag defaults to DEBUG so it's on in dev
# / CI and off in any environment that runs with DJANGO_DEBUG=False, while
# still being explicitly overridable from the env if needed.
PAYMENTS_ALLOW_MOCK_GATEWAY = env.bool("PAYMENTS_ALLOW_MOCK_GATEWAY", default=DEBUG)

# === Object storage (invoice PDFs) ===
# Backed by MinIO in local dev (S3-compatible). Same django-storages config
# works against real AWS S3 in prod -- just clear AWS_S3_ENDPOINT_URL and
# point AWS_S3_REGION_NAME at the prod region.
#
# The bucket is provisioned by docker-compose (MINIO_DEFAULT_BUCKETS) with a
# "download" anonymous policy so the invoice URL returned to the customer is
# directly fetchable without signing. For production use a private bucket +
# presigned URLs by flipping AWS_QUERYSTRING_AUTH=True and dropping the
# `download` policy on the bucket.
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="path")
AWS_QUERYSTRING_AUTH = env.bool("AWS_QUERYSTRING_AUTH", default=False)

INVOICE_BUCKET = env("INVOICE_BUCKET", default="invoices")
MEDIA_BUCKET = env("MEDIA_BUCKET", default="media")

# Common S3-compatible options shared by every bucket — kept in one dict
# so adding a third bucket later is one OPTIONS merge.
_S3_COMMON = {
    "endpoint_url": AWS_S3_ENDPOINT_URL or None,
    "access_key": AWS_ACCESS_KEY_ID or None,
    "secret_key": AWS_SECRET_ACCESS_KEY or None,
    "region_name": AWS_S3_REGION_NAME,
    "addressing_style": AWS_S3_ADDRESSING_STYLE,
    "querystring_auth": AWS_QUERYSTRING_AUTH,
    "file_overwrite": True,
    "default_acl": None,
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "invoices": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **_S3_COMMON,
            "bucket_name": INVOICE_BUCKET,
            # Every object in this bucket is a PDF.
            "object_parameters": {"ContentType": "application/pdf"},
        },
    },
    "media": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **_S3_COMMON,
            "bucket_name": MEDIA_BUCKET,
            # Mixed image formats; let django-storages infer ContentType
            # from the filename extension (.png / .jpg / .webp).
        },
    },
}

# === Tenant routing ===
# Subdomains that should NOT be treated as tenant slugs
TENANT_RESERVED_SUBDOMAINS = {"www", "api", "admin", "static", "media"}

# Domain suffix that gets stripped to find the subdomain. For "store-a.acme.test"
# with suffix "acme.test", the subdomain is "store-a".
TENANT_DOMAIN_SUFFIX = env("TENANT_DOMAIN_SUFFIX", default="acme.test")

# Local-dev convenience: when set AND DEBUG is True, requests whose hostname has
# no resolvable tenant subdomain (e.g. plain `localhost`) fall back to this tenant.
# Silently ignored when DEBUG is False so it cannot accidentally ship.
# Never overrides a real subdomain.
DEV_DEFAULT_TENANT_SUBDOMAIN = env("DEV_DEFAULT_TENANT_SUBDOMAIN", default="")
if DEV_DEFAULT_TENANT_SUBDOMAIN and DEBUG:
    import logging

    logging.getLogger("apps.core").warning(
        "DEV_DEFAULT_TENANT_SUBDOMAIN=%r is active. Requests without a tenant "
        "subdomain will be resolved to this tenant. Local dev only.",
        DEV_DEFAULT_TENANT_SUBDOMAIN,
    )

# === Logging ===
# Two formatters; pick at process start via LOG_FORMAT=json|text. JSON for
# production (so Loki/Datadog can index `request_id` and `tenant_id` as
# first-class fields); text for dev terminals where humans read the output.
# Both formatters get those fields injected by RequestContextFilter, which
# reads the contextvars set by RequestIdMiddleware (HTTP) and the Celery
# signal handlers in config/celery.py (async work).
LOG_FORMAT = env("LOG_FORMAT", default="text")  # "text" | "json"
APPS_LOG_LEVEL = env("APPS_LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "apps.core.logging_filters.RequestContextFilter",
        },
    },
    "formatters": {
        "text": {
            "format": (
                "{levelname} {asctime} [req={request_id} tenant={tenant_id}] {name} {message}"
            ),
            "style": "{",
        },
        "json": {
            "()": "apps.core.logging_filters.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT if LOG_FORMAT in ("text", "json") else "text",
            "filters": ["request_context"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        # Declared here (not just in local.py) so prod has a known baseline
        # even if no environment-specific settings file ever runs.
        "apps": {
            "handlers": ["console"],
            "level": APPS_LOG_LEVEL,
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
