from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.authentication import ExpiringTokenAuthentication


@extend_schema(
    summary="Admin logout (revoke token)",
    responses={204: None},
)
class AdminLogoutView(APIView):
    """Delete the caller's API token. Subsequent requests with that token 401."""

    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
