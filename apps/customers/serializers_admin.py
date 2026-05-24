"""Admin (writable) serializers for the Customer model.

Kept separate from `serializers/` (read-only address serializer) so the
storefront never accidentally accepts an admin-write payload, and so
admin clients see fields the storefront serializer hides (is_active).
"""

from rest_framework import serializers

from apps.customers.models import Customer, CustomerType


class AdminCustomerSerializer(serializers.ModelSerializer):
    is_b2b = serializers.BooleanField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
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
        read_only_fields = ["id", "is_b2b", "created_at", "updated_at"]


def _validate_b2b_fields(attrs: dict) -> None:
    """B2B customers must carry both `tax_id` and `company_name` so
    orders snapshotted off them are invoiceable. The constraint is at
    the serializer layer (not the model) because the existing storefront
    auth flow can mint a B2B customer with empty B2B fields if the IdP
    sets that customer_type without context."""
    if attrs.get("customer_type") == CustomerType.B2B:
        missing = [f for f in ("tax_id", "company_name") if not attrs.get(f)]
        if missing:
            raise serializers.ValidationError({f: "Required for B2B customers." for f in missing})


class AdminCustomerCreateSerializer(serializers.ModelSerializer):
    """Tenant is implicit (from request context); never accepted in the body."""

    class Meta:
        model = Customer
        fields = [
            "email",
            "name",
            "phone",
            "customer_type",
            "tax_id",
            "company_name",
            "is_active",
        ]

    def validate_email(self, value):
        # Normalize to lowercase before storing so the case-sensitive
        # uniq_customer_email_per_tenant constraint behaves case-insensitively
        # in practice. (A small race window remains: two concurrent POSTs
        # with the same casing both pass the existence check before either
        # commits, and one hits IntegrityError 500. Proper fix needs a
        # functional unique index on lower(email) -- out of POC scope.)
        normalized = (value or "").strip().lower()
        if not normalized:
            raise serializers.ValidationError("Email is required.")
        if Customer.objects.filter(email=normalized).exists():
            raise serializers.ValidationError(
                f"A customer with email {normalized!r} already exists on this tenant."
            )
        return normalized

    def validate(self, attrs):
        _validate_b2b_fields(attrs)
        return attrs


class AdminCustomerUpdateSerializer(serializers.ModelSerializer):
    """Email is immutable: orders, addresses, and the upstream IdP key off
    it. Changing customer_type mid-life is allowed but pulls the B2B
    field-required check forward."""

    class Meta:
        model = Customer
        fields = [
            "name",
            "phone",
            "customer_type",
            "tax_id",
            "company_name",
            "is_active",
        ]

    def validate(self, attrs):
        # Merge incoming changes onto the existing row for the B2B check
        # so PATCHing only customer_type still validates correctly.
        merged = {
            "customer_type": attrs.get("customer_type", self.instance.customer_type),
            "tax_id": attrs.get("tax_id", self.instance.tax_id),
            "company_name": attrs.get("company_name", self.instance.company_name),
        }
        _validate_b2b_fields(merged)
        return attrs
