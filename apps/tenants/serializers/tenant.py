from rest_framework import serializers

from apps.iam.models import TenantMembership
from apps.tenants.models import Tenant


class TenantAdminInlineSerializer(serializers.ModelSerializer):
    """Slim membership row for embedding inside a Tenant payload."""

    user_id = serializers.UUIDField(read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = TenantMembership
        fields = ["id", "user_id", "user_email", "role", "created_at"]
        read_only_fields = fields


class TenantSerializer(serializers.ModelSerializer):
    tenant_admins = TenantAdminInlineSerializer(source="memberships", many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "subdomain",
            "default_currency",
            "is_active",
            "created_at",
            "updated_at",
            "tenant_admins",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "tenant_admins"]


class TenantCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["name", "subdomain", "default_currency", "is_active"]

    def validate_subdomain(self, value):
        from django.conf import settings

        if value in settings.TENANT_RESERVED_SUBDOMAINS:
            raise serializers.ValidationError(f"`{value}` is a reserved subdomain.")
        return value


class TenantUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        # subdomain is immutable: it's the routing identity. Changing it would
        # break in-flight URLs, cached customer bookmarks, and gateway webhook
        # callbacks that may have been registered against the old hostname.
        fields = ["name", "default_currency", "is_active"]
