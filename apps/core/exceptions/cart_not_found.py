from apps.core.exceptions.resource_not_found import ResourceNotFound


class CartNotFound(ResourceNotFound):
    code = "cart_not_found"
