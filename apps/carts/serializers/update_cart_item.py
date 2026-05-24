from rest_framework import serializers


class UpdateCartItemSerializer(serializers.Serializer):
    """Body for PATCH /cart/items/{item_id}. Replaces the line's quantity
    (does not increment — use POST /cart/items to add more)."""

    quantity = serializers.IntegerField(min_value=1, max_value=999)
