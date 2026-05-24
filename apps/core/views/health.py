"""Health endpoint -- checks the dependencies the app needs to function."""

import logging

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import AllowAny
from apps.core.responses import envelope

log = logging.getLogger(__name__)


class HealthView(APIView):
    """Liveness and dependency health probe.

    Exempt from both auth (`X-Customer-Id` not required) and tenant
    resolution — callable from a load balancer or uptime checker without
    setting up tenant subdomains. Pings each backing service and returns
    a structured report.

    Returns `200 ok` only when **all three** dependencies (Postgres,
    Redis, RabbitMQ) respond. If any one is down, the response is
    `503 degraded` with the per-service `ok` flag and error string so
    operators can tell which component is failing without grepping logs.
    Safe to point a Kubernetes readiness probe at.
    """

    permission_classes = [AllowAny]

    @extend_schema(summary="Health probe (database, Redis, RabbitMQ)")
    def get(self, request):
        checks = {
            "database": self._check_db(),
            "redis": self._check_redis(),
            "rabbitmq": self._check_rabbitmq(),
        }
        all_ok = all(c["ok"] for c in checks.values())
        return Response(
            envelope(
                {"status": "ok" if all_ok else "degraded", "checks": checks},
                request=request,
            ),
            status=200 if all_ok else 503,
        )

    @staticmethod
    def _check_db():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return {"ok": True}
        except Exception as e:
            log.exception("DB health check failed")
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _check_redis():
        try:
            import redis

            client = redis.from_url(settings.CELERY_RESULT_BACKEND)
            client.ping()
            return {"ok": True}
        except Exception as e:
            log.exception("Redis health check failed")
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _check_rabbitmq():
        try:
            from kombu import Connection

            with Connection(settings.CELERY_BROKER_URL) as conn:
                conn.connect()
            return {"ok": True}
        except Exception as e:
            log.exception("RabbitMQ health check failed")
            return {"ok": False, "error": str(e)}
