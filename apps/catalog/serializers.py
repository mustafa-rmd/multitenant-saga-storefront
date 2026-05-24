from rest_framework import serializers

from apps.catalog.models import Product


class ProductSerializer(serializers.ModelSerializer):
    """Storefront-facing product representation.

    Deliberately omits `reserved_quantity`: that's operational state
    (how many units are held by in-flight checkouts) and exposing it
    leaks contention info to scrapers. Clients should use
    `availableQuantity` for "can I add this to cart" decisions.
    """

    available_quantity = serializers.IntegerField(read_only=True)
    # URL to the primary image in the media bucket, or "" if none. Derived
    # from Product.image_key by Product.image_url at serialize time.
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
            "available_quantity",
            "is_active",
            "image_url",
        ]
        read_only_fields = fields
