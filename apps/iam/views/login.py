from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.responses import envelope
from apps.iam.authentication import token_expires_at
from apps.iam.serializers import LoginRequestSerializer, LoginResponseSerializer
from apps.iam.throttles import LoginEmailThrottle, LoginIpThrottle
from apps.iam.views._user_payload import serialize_user

User = get_user_model()


@extend_schema(
    summary="Admin login (issue token)",
    request=LoginRequestSerializer,
    responses={200: LoginResponseSerializer},
    auth=[],
)
class AdminLoginView(APIView):
    """Exchange admin email + password for a time-limited API token.

    Two-rail authentication: this endpoint is the only way a Django User
    obtains a token. Customer (storefront) auth is unaffected -- those
    requests keep using `X-Customer-Id`. The returned `token` is sent on
    subsequent admin requests as `Authorization: Token <token>`.

    Always responds the same way for unknown email and wrong password:
    `401 invalid_credentials`. No user enumeration via timing or message.

    Throttled by both client IP and target email -- see `apps/iam/throttles.py`.
    Rate-limit exhaustion returns `429 rate_limited`.

    Token rotation: on every successful login the user's previous token
    (if any) is replaced with a new one. This way a leaked older token
    becomes invalid as soon as the legitimate user re-authenticates.
    Expiry is enforced by `ExpiringTokenAuthentication` against
    `ADMIN_TOKEN_TTL_SECONDS` (default 8 hours).
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginIpThrottle, LoginEmailThrottle]

    def post(self, request):
        s = LoginRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"]
        password = s.validated_data["password"]

        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            return self._invalid(request)

        if not user.check_password(password):
            return self._invalid(request)

        # Rotation: drop any existing token and mint a fresh one. The new
        # token's `created` timestamp restarts the TTL clock.
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)

        return Response(
            envelope(
                {
                    "token": token.key,
                    "expires_at": token_expires_at(token),
                    "user": serialize_user(user),
                },
                request=request,
            ),
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _invalid(request):
        from apps.core.responses import error_envelope

        return Response(
            error_envelope(
                {"code": "invalid_credentials", "detail": "Invalid email or password"},
                request=request,
            ),
            status=status.HTTP_401_UNAUTHORIZED,
        )
