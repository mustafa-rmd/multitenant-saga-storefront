from rest_framework import serializers

from apps.customers.models import Customer


class PlatformCustomerSerializer(serializers.ModelSerializer):
    """Same shape as AdminCustomerSerializer plus the tenant subdomain --
    when a platform admin searches cross-tenant, knowing which store the
    row belongs to is the whole point."""

    tenant_subdomain = serializers.CharField(source="tenant.subdomain", read_only=True)
    is_b2b = serializers.BooleanField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "tenant_id",
            "tenant_subdomain",
            "email",
            "name",
            "phone",
            "customer_type",
            "tax_id",
            "company_name",
            "is_b2b",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
