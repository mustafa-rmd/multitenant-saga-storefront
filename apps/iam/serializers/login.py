from rest_framework import serializers


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class MembershipReadSerializer(serializers.Serializer):
    tenant_id = serializers.UUIDField()
    tenant_subdomain = serializers.CharField()
    role = serializers.CharField()


class LoginResponseUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    is_superuser = serializers.BooleanField()
    memberships = MembershipReadSerializer(many=True)


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    # ISO-8601 UTC; null when ADMIN_TOKEN_TTL_SECONDS<=0 (TTL disabled).
    expires_at = serializers.CharField(allow_null=True)
    user = LoginResponseUserSerializer()
