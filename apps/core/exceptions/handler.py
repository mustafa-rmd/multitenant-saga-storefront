"""Custom DRF exception handler that wraps errors in our envelope shape."""

from apps.core.exceptions.domain_error import DomainError


def custom_exception_handler(exc, context):
    """
    DRF exception handler that wraps responses in our error envelope.

    Handles:
    - Domain errors (mapped via .to_dict() and .http_status)
    - DRF validation errors (422 with field-level pointers)
    - Auth/permission errors
    - Falls through to default DRF handling for everything else
    """
    from rest_framework.exceptions import (
        AuthenticationFailed,
        NotAuthenticated,
        PermissionDenied,
        Throttled,
        ValidationError,
    )
    from rest_framework.response import Response
    from rest_framework.views import exception_handler

    from apps.core.responses import error_envelope

    request = context.get("request")

    if isinstance(exc, DomainError):
        return Response(
            error_envelope(exc.to_dict(), request=request),
            status=exc.http_status,
        )

    if isinstance(exc, ValidationError):
        errors = _flatten_drf_validation_error(exc.detail)
        return Response(
            error_envelope(*errors, request=request),
            status=422,
        )

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return Response(
            error_envelope(
                {"code": "unauthorized", "detail": str(exc)},
                request=request,
            ),
            status=401,
        )

    if isinstance(exc, PermissionDenied):
        return Response(
            error_envelope(
                {"code": "forbidden", "detail": str(exc)},
                request=request,
            ),
            status=403,
        )

    if isinstance(exc, Throttled):
        meta = {}
        if exc.wait is not None:
            meta["retry_after_seconds"] = int(exc.wait)
        return Response(
            error_envelope(
                {
                    "code": "rate_limited",
                    "detail": "Too many requests. Slow down and try again shortly.",
                    "meta": meta or None,
                },
                request=request,
            ),
            status=429,
            headers={"Retry-After": str(int(exc.wait))} if exc.wait is not None else {},
        )

    # Fall through to DRF's default handling
    response = exception_handler(exc, context)
    if response is not None:
        # Re-wrap the default response in our envelope
        response.data = error_envelope(
            {"code": "error", "detail": str(response.data)},
            request=request,
        )
    return response


def _flatten_drf_validation_error(detail, prefix=""):
    """Convert nested DRF validation errors into flat error objects with pointers."""
    errors = []
    if isinstance(detail, dict):
        for field, value in detail.items():
            pointer = f"{prefix}/{field}"
            errors.extend(_flatten_drf_validation_error(value, pointer))
    elif isinstance(detail, list):
        for item in detail:
            if isinstance(item, (dict, list)):
                errors.extend(_flatten_drf_validation_error(item, prefix))
            else:
                errors.append(
                    {
                        "code": "validation_error",
                        "detail": str(item),
                        "source": {"pointer": prefix} if prefix else None,
                    }
                )
    else:
        errors.append(
            {
                "code": "validation_error",
                "detail": str(detail),
                "source": {"pointer": prefix} if prefix else None,
            }
        )
    return errors
