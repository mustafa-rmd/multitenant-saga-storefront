"""Admin (writable) serializers for coupons.

Validation lives at three levels:
- Field-level (`validate_<field>`): shape checks that don't need to look
  at other fields (currency format, country-code shape, code normalization).
- Object-level (`validate`): cross-field invariants (currency required
  for FIXED, percentage <= 100). On update these run against the
  *resulting* state by merging incoming partial data with the existing
  instance.
- View-level (under row lock): invariants that need locked DB state
  (max_uses >= uses_count, currency/discount_type changes blocked when
  active carts reference the coupon). See AdminCouponDetailView.patch.
"""

import re
from decimal import Decimal

from django.core.validators import RegexValidator
from rest_framework import serializers

from apps.coupons.models import Coupon
from apps.coupons.models.discount_type import DiscountType

# ISO 4217: three uppercase letters. Same shape as catalog's currency rule.
_CURRENCY_VALIDATOR = RegexValidator(
    regex=r"^[A-Z]{3}$",
    message="Currency must be a three-letter uppercase ISO 4217 code (e.g. SAR, USD).",
)

# ISO 3166-1 alpha-2: two uppercase letters.
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")

# Coupon code: 1-64 chars, alphanumerics and dash/underscore. Customer-facing
# strings need to be tolerable on the address bar and in email; we reject
# whitespace and punctuation early. Stored uppercase for case-insensitive
# UX with a case-sensitive backing column.
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,63}$")


def _validate_country_list(value):
    if not isinstance(value, list):
        raise serializers.ValidationError("Must be a list of ISO 3166-1 alpha-2 codes.")
    for i, item in enumerate(value):
        if not isinstance(item, str) or not _COUNTRY_RE.match(item):
            raise serializers.ValidationError(
                f"Item {i} ({item!r}) is not a valid ISO 3166-1 alpha-2 code "
                "(two uppercase letters, e.g. SA, AE)."
            )
    return value


def _normalize_and_validate_code(value: str) -> str:
    """Strip + uppercase, then validate shape. Customers type 'welcome10';
    we store 'WELCOME10' so lookups are case-insensitive without a citext
    column or a functional index."""
    if not isinstance(value, str):
        raise serializers.ValidationError("Code must be a string.")
    normalized = value.strip().upper()
    if not _CODE_RE.match(normalized):
        raise serializers.ValidationError(
            "Code must be 1–64 chars, alphanumerics + dash/underscore, "
            "starting with a letter or digit."
        )
    return normalized


def _validate_cross_fields(*, discount_type: str, discount_value, currency: str) -> None:
    """Shared cross-field checks. Raises serializers.ValidationError."""
    if discount_type == DiscountType.FIXED and not currency:
        raise serializers.ValidationError(
            {"currency": "Currency is required for fixed-amount coupons."}
        )
    if (
        discount_type == DiscountType.PERCENTAGE
        and discount_value is not None
        and Decimal(discount_value) > Decimal("100")
    ):
        raise serializers.ValidationError(
            {"discount_value": "Percentage discount cannot exceed 100."}
        )


class AdminCouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "discount_type",
            "discount_value",
            "currency",
            "min_cart_subtotal",
            "allowed_countries",
            "customer_type_restriction",
            "max_uses",
            "uses_count",
            "valid_from",
            "valid_until",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "uses_count", "created_at", "updated_at"]


class AdminCouponCreateSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(
        max_length=3,
        required=False,
        allow_blank=True,
        validators=[_CURRENCY_VALIDATOR],
    )
    discount_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    class Meta:
        model = Coupon
        fields = [
            "code",
            "discount_type",
            "discount_value",
            "currency",
            "min_cart_subtotal",
            "allowed_countries",
            "customer_type_restriction",
            "max_uses",
            # Writable on create so test/dev fixtures can birth a coupon
            # in an already-exhausted state. The view-level cross-check
            # (max_uses >= uses_count) still applies under row lock.
            "uses_count",
            "valid_from",
            "valid_until",
            "is_active",
        ]

    def validate_code(self, value: str) -> str:
        normalized = _normalize_and_validate_code(value)
        # Tenant scope is implicit via the manager. Pre-check turns the
        # DB-level uniq_coupon_code_per_tenant into a clean 422 instead of
        # a 500 IntegrityError.
        if Coupon.objects.filter(code=normalized).exists():
            raise serializers.ValidationError(f"Coupon code {normalized!r} already exists.")
        return normalized

    def validate_allowed_countries(self, value):
        return _validate_country_list(value)

    def validate(self, attrs):
        _validate_cross_fields(
            discount_type=attrs.get("discount_type"),
            discount_value=attrs.get("discount_value"),
            currency=attrs.get("currency", ""),
        )
        return attrs


class AdminCouponUpdateSerializer(serializers.ModelSerializer):
    """Code is immutable: existing carts and orders reference it. Activating
    a coupon for new orders or changing its expiry is fine; renaming would
    silently break references.

    Cross-field validation merges the incoming partial data with the existing
    instance so a PATCH that flips discount_type alone still triggers the
    "currency required for FIXED" check.
    """

    currency = serializers.CharField(
        max_length=3,
        required=False,
        allow_blank=True,
        validators=[_CURRENCY_VALIDATOR],
    )
    discount_value = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
    )

    class Meta:
        model = Coupon
        fields = [
            "discount_type",
            "discount_value",
            "currency",
            "min_cart_subtotal",
            "allowed_countries",
            "customer_type_restriction",
            "max_uses",
            # Writable on update too (matches the create serializer) so
            # operators can correct a wrong count, and test fixtures can
            # rehydrate an exhausted coupon without delete-and-recreate.
            "uses_count",
            "valid_from",
            "valid_until",
            "is_active",
        ]

    def validate_allowed_countries(self, value):
        return _validate_country_list(value)

    def validate(self, attrs):
        instance = self.instance
        _validate_cross_fields(
            discount_type=attrs.get("discount_type", instance.discount_type),
            discount_value=attrs.get("discount_value", instance.discount_value),
            currency=attrs.get("currency", instance.currency),
        )
        return attrs
