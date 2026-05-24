from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.catalog.serializers_admin import AdminProductSerializer
from apps.catalog.services.product_image_storage import (
    delete_product_image,
    upload_product_image,
)
from apps.catalog.views.admin._mixins import ProductLookupMixin
from apps.core.responses import envelope
from apps.iam.views._base import TenantAdminAPIView


@extend_schema_view(
    post=extend_schema(
        summary="Upload / replace the product's primary image",
        request={
            "multipart/form-data": inline_serializer(
                name="ProductImageUpload",
                fields={"file": serializers.FileField()},
            )
        },
        responses={200: AdminProductSerializer},
    ),
    delete=extend_schema(
        summary="Remove the product's primary image",
        responses={204: OpenApiTypes.NONE},
    ),
)
class AdminProductImageView(ProductLookupMixin, TenantAdminAPIView):
    """POST a multipart `file` field (png / jpg / webp, <= 5 MiB) to set
    the product's primary image; DELETE to clear it.

    Re-uploading overwrites the existing object in place. Changing format
    (e.g. png → webp) writes the new key and asynchronously removes the
    old one so the bucket doesn't accumulate stale variants.
    """

    parser_classes = [MultiPartParser]
    lookup_url_kwarg = "product_id"

    def post(self, request, product_id):
        product = self._get_product(product_id)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise serializers.ValidationError({"file": "Required."})

        old_key = product.image_key
        new_key = upload_product_image(
            tenant_id=product.tenant_id,
            product_id=product.id,
            uploaded_file=uploaded,
        )

        product.image_key = new_key
        product.save(update_fields=["image_key", "updated_at"])

        # If the new upload landed at a different key (different extension),
        # drop the old object so it doesn't linger.
        if old_key and old_key != new_key:
            delete_product_image(old_key)

        return Response(envelope(AdminProductSerializer(product).data, request=request))

    def delete(self, request, product_id):
        product = self._get_product(product_id)
        if product.image_key:
            delete_product_image(product.image_key)
            product.image_key = ""
            product.save(update_fields=["image_key", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
