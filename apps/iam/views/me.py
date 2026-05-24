from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.responses import envelope
from apps.iam.authentication import ExpiringTokenAuthentication
from apps.iam.serializers import LoginResponseUserSerializer
from apps.iam.views._user_payload import serialize_user


@extend_schema(
    summary="Current admin profile + memberships",
    responses={200: LoginResponseUserSerializer},
)
class AdminMeView(APIView):
    """Return the current admin's id, email, superuser flag, and memberships."""

    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(envelope(serialize_user(request.user), request=request))
