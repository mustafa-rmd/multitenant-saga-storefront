from rest_framework import serializers


class CheckoutResultSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_number = serializers.IntegerField()
    status = serializers.CharField()
    payment_status = serializers.CharField()
    grand_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    next_action = serializers.DictField(allow_null=True, required=False)
