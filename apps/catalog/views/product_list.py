from decimal import Decimal, InvalidOperation

from django.db.models import F, Q
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import generics, serializers

from apps.catalog.models import Product
from apps.catalog.serializers import ProductSerializer

_TRUE_VALUES = frozenset({"true", "1", "yes"})
_FALSE_VALUES = frozenset({"false", "0", "no"})


def _parse_decimal(value: str, field: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise serializers.ValidationError(
            {field: f"Must be a decimal number, got {value!r}."}
        ) from exc


def _parse_bool(value: str, field: str) -> bool:
    lowered = value.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise serializers.ValidationError(
        {field: f"Must be true/false (or 1/0, yes/no), got {value!r}."}
    )


@extend_schema_view(
    get=extend_schema(
        summary="List active products",
        parameters=[
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description="Case-insensitive substring match on `sku`, `name`, or `description`.",
            ),
            OpenApiParameter(
                "sku",
                OpenApiTypes.STR,
                description="Exact SKU match (still tenant-scoped).",
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description="Filter to a single currency (e.g. `SAR`, `USD`). Three-letter ISO 4217.",
            ),
            OpenApiParameter(
                "minPrice",
                OpenApiTypes.DECIMAL,
                description="Minimum unit price, inclusive.",
            ),
            OpenApiParameter(
                "maxPrice",
                OpenApiTypes.DECIMAL,
                description="Maximum unit price, inclusive.",
            ),
            OpenApiParameter(
                "inStock",
                OpenApiTypes.BOOL,
                description=(
                    "`true` → only products with `availableQuantity > 0`. "
                    "`false` → only out-of-stock products. Snapshot value — concurrent "
                    "checkouts may consume stock between this read and your add. "
                    "Invalid values return 422."
                ),
            ),
            OpenApiParameter(
                "page",
                OpenApiTypes.INT,
                description="Page number for pagination. Defaults to 1.",
            ),
            OpenApiParameter(
                "page_size",
                OpenApiTypes.INT,
                description="Page size. Defaults to 20, max 100.",
            ),
        ],
    )
)
class ProductListView(generics.ListAPIView):
    """List active products for the resolved tenant, with optional filtering.

    Tenant scoping is enforced by the `TenantScopedModel` manager and
    reinforced by Postgres row-level security — products from another
    tenant cannot leak through this endpoint even if a bug bypassed the
    manager filter. Results are ordered by SKU for stable pagination.

    Supported filters (all optional, all `AND`-combined):

    - `search`: case-insensitive substring across `sku`, `name`, `description`.
    - `sku`: exact SKU (case-sensitive).
    - `currency`: ISO 4217 three-letter code (`SAR`, `USD`, ...).
    - `minPrice` / `maxPrice`: inclusive price bounds.
    - `inStock=true|false`: filter to in-stock (`availableQuantity > 0`) or
      out-of-stock products. Invalid values return 422.

    Pagination uses standard `page` + `page_size` query params (envelope
    includes a `meta.pagination` block with cursors). This endpoint is
    read-only; products are managed via the tenant-admin REST surface
    (`/api/v1/admin/products`) or the Django admin.
    """

    serializer_class = ProductSerializer

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True)
        params = self.request.query_params

        if search := params.get("search"):
            qs = qs.filter(
                Q(sku__icontains=search)
                | Q(name__icontains=search)
                | Q(description__icontains=search)
            )

        if sku := params.get("sku"):
            qs = qs.filter(sku=sku)

        if currency := params.get("currency"):
            qs = qs.filter(currency=currency.upper())

        if min_price := params.get("minPrice"):
            qs = qs.filter(price__gte=_parse_decimal(min_price, "minPrice"))

        if max_price := params.get("maxPrice"):
            qs = qs.filter(price__lte=_parse_decimal(max_price, "maxPrice"))

        if (in_stock := params.get("inStock")) is not None and in_stock != "":
            if _parse_bool(in_stock, "inStock"):
                qs = qs.filter(stock_quantity__gt=F("reserved_quantity"))
            else:
                qs = qs.filter(stock_quantity__lte=F("reserved_quantity"))

        return qs.order_by("sku")
