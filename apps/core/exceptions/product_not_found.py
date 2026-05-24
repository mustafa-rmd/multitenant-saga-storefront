from apps.core.exceptions.resource_not_found import ResourceNotFound


class ProductNotFound(ResourceNotFound):
    code = "product_not_found"

    def __init__(self, *, product_id):
        super().__init__(
            f"Product {product_id} not found",
            meta={"product_id": str(product_id)},
        )
