"""Admin (writable) serializers for the catalog.

Kept separate from `serializers.py` (read-only) so the storefront
serializer can never accidentally accept a write field, and so admin
clients see the full field set including `tenant`-internal fields when
relevant.
"""

from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.catalog.models import Product

# ISO 4217: three uppercase letters. Enforced at the serializer boundary
# (model field is unconstrained for migration-stability reasons; revisit
# if anything ever bypasses serializers to insert products).
_CURRENCY_VALIDATOR = RegexValidator(
    regex=r"^[A-Z]{3}$",
    message="Currency must be a three-letter uppercase ISO 4217 code (e.g. SAR, USD).",
)


class AdminProductSerializer(serializers.ModelSerializer):
    available_quantity = serializers.IntegerField(read_only=True)
    image_url = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "description",
            "price",
            "currency",
            "stock_quantity",
            "reserved_quantity",
            "available_quantity",
            "is_active",
            "image_key",
            "image_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reserved_quantity",
            "available_quantity",
            "image_key",
            "image_url",
            "created_at",
            "updated_at",
        ]


class AdminProductCreateSerializer(serializers.ModelSerializer):
    """Write serializer for create: tenant is implicit (from request context).

    `sku` uniqueness is validated explicitly here so a duplicate surfaces
    as a clean 422 instead of an IntegrityError 500 from the DB-level
    `uniq_product_sku_per_tenant` constraint. The DB constraint remains
    the source of truth under concurrent creates.
    """

    currency = serializers.CharField(max_length=3, validators=[_CURRENCY_VALIDATOR])

    class Meta:
        model = Product
        fields = ["sku", "name", "description", "price", "currency", "stock_quantity", "is_active"]

    def validate_sku(self, value: str) -> str:
        if Product.objects.filter(sku=value).exists():
            raise serializers.ValidationError(f"SKU {value!r} already exists on this tenant.")
        return value


class AdminProductUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for PATCH. `sku` is intentionally excluded — SKUs are
    stable client-facing references and renames break receipts, search history,
    and analytics. Currency-change and stock-decrement guards live in the view
    (they need the locked-row state)."""

    currency = serializers.CharField(max_length=3, required=False, validators=[_CURRENCY_VALIDATOR])

    class Meta:
        model = Product
        fields = ["name", "description", "price", "currency", "stock_quantity", "is_active"]
