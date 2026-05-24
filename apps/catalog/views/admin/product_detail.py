from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.response import Response

from apps.carts.models import Cart, CartItem
from apps.catalog.models import Product
from apps.catalog.serializers_admin import AdminProductSerializer, AdminProductUpdateSerializer
from apps.catalog.views.admin._mixins import ProductLookupMixin
from apps.core.exceptions import ResourceNotFound
from apps.core.responses import envelope
from apps.iam.views._base import TenantAdminAPIView


@extend_schema_view(
    get=extend_schema(summary="Get a product (admin)", responses={200: AdminProductSerializer}),
    patch=extend_schema(
        summary="Update a product",
        request=AdminProductUpdateSerializer,
        responses={200: AdminProductSerializer},
    ),
    delete=extend_schema(
        summary="Soft-delete a product (sets isActive=false)", responses={204: None}
    ),
)
class AdminProductDetailView(ProductLookupMixin, TenantAdminAPIView):
    """Admin GET/PATCH/DELETE for a single product, tenant-scoped via RLS.

    `DELETE` is a soft delete: it flips `is_active=False` rather than
    removing the row, because Product is referenced by historical
    CartItem and OrderItem rows. Inactive products disappear from the
    storefront list but remain queryable for reporting and order
    detail rendering.

    `PATCH` takes a row lock so a stock decrement cannot race against a
    concurrent checkout's reservation -- without the lock, the DB-level
    `stock_gte_reserved` constraint would surface as a 500.
    """

    serializer_class = AdminProductSerializer
    lookup_url_kwarg = "product_id"

    def get(self, request, product_id):
        product = self._get_product(product_id)
        return Response(envelope(AdminProductSerializer(product).data, request=request))

    def patch(self, request, product_id):
        with transaction.atomic():
            try:
                product = Product.objects.select_for_update().get(id=product_id)
            except Product.DoesNotExist as exc:
                raise ResourceNotFound("Product not found") from exc

            s = AdminProductUpdateSerializer(product, data=request.data, partial=True)
            s.is_valid(raise_exception=True)
            validated = s.validated_data

            # Guard: cannot drop stock below currently reserved units.
            new_stock = validated.get("stock_quantity")
            if new_stock is not None and new_stock < product.reserved_quantity:
                raise serializers.ValidationError(
                    {
                        "stock_quantity": (
                            f"Cannot set stock_quantity ({new_stock}) below the "
                            f"currently reserved quantity ({product.reserved_quantity})."
                        )
                    }
                )

            # Guard: cannot change currency while the product sits in any
            # active or in-flight cart. Existing cart lines hold a snapshot
            # of the old currency; the cart's currency lock means the next
            # add would 409, so block the rename at the source.
            new_currency = validated.get("currency")
            if new_currency is not None and new_currency != product.currency:
                in_use = CartItem.objects.filter(
                    product_id=product.id,
                    cart__status__in=(Cart.Status.ACTIVE, Cart.Status.CHECKING_OUT),
                ).exists()
                if in_use:
                    raise serializers.ValidationError(
                        {
                            "currency": (
                                "Cannot change currency while the product is in any "
                                "active or in-flight cart."
                            )
                        }
                    )

            s.save()
            return Response(envelope(AdminProductSerializer(product).data, request=request))

    def delete(self, request, product_id):
        product = self._get_product(product_id)
        if product.is_active:
            product.is_active = False
            product.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
