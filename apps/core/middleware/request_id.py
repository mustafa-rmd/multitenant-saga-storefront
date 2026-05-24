from uuid import uuid4

from apps.core.request_context import (
    reset_current_request_id,
    set_current_request_id,
)

_HEADER = "HTTP_X_REQUEST_ID"
_RESPONSE_HEADER = "X-Request-ID"


class RequestIdMiddleware:
    """Resolve (or mint) a request id for every request.

    Order matters: this is the first middleware so the id is set on the
    contextvar BEFORE tenant resolution, auth, or anything else that
    might log. The same id ends up in:

      * `request.request_id` -- available to views
      * the response envelope's `meta.request_id`
      * every log record (via RequestContextFilter)
      * the `X-Request-ID` response header so the client can correlate
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(_HEADER) or str(uuid4())
        request.request_id = request_id

        token = set_current_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_current_request_id(token)

        response.headers[_RESPONSE_HEADER] = request_id
        return response
