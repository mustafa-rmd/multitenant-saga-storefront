"""Storefront serializers for the customers app.

The only public-facing serializer is `AddressSerializer` (saved-address
CRUD). The Customer row is read on the admin path -- the storefront
never returns the bare Customer; identity is established at the edge
via X-Customer-Id and the row's existence is implicit.

Admin and platform-admin serializers live in `serializers_admin.py` and
`serializers_platform.py` at this module's level.
"""

import re

from rest_framework import serializers

from apps.customers.models import Address

# ISO 3166-1 alpha-2 (two uppercase letters). Matches the same shape we
# enforce on Coupon.allowed_countries -- keeps country data consistent
# across the two apps that store it.
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


class AddressSerializer(serializers.ModelSerializer):
    customer_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Address
        fields = [
            "id",
            "customer_id",
            "label",
            "country",
            "city",
            "street",
            "postal_code",
            "is_default",
        ]
        read_only_fields = ["id", "customer_id"]

    def validate_country(self, value: str) -> str:
        # Normalize to uppercase so 'sa' and 'SA' both land as 'SA'.
        normalized = (value or "").strip().upper()
        if not _COUNTRY_RE.match(normalized):
            raise serializers.ValidationError(
                "Country must be an ISO 3166-1 alpha-2 code "
                f"(two letters, e.g. SA, AE), got {value!r}."
            )
        return normalized
