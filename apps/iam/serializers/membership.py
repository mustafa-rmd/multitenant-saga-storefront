from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.iam.models import Role, TenantMembership

User = get_user_model()


class MembershipCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices, default=Role.TENANT_ADMIN)
    create_user_if_missing = serializers.BooleanField(default=False)
    initial_password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=False,
        min_length=8,
    )
    first_name = serializers.CharField(required=False, allow_blank=False, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=False, max_length=150)

    def validate(self, attrs):
        if attrs.get("create_user_if_missing"):
            missing = {
                field: "Required when createUserIfMissing=true."
                for field in ("initial_password", "first_name", "last_name")
                if not attrs.get(field)
            }
            if missing:
                raise serializers.ValidationError(missing)
        return attrs


class MembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    tenant_subdomain = serializers.CharField(source="tenant.subdomain", read_only=True)

    class Meta:
        model = TenantMembership
        fields = [
            "id",
            "user_id",
            "user_email",
            "tenant_id",
            "tenant_subdomain",
            "role",
            "created_at",
        ]
        read_only_fields = fields
