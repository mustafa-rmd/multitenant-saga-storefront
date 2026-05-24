from apps.core.exceptions.resource_not_found import ResourceNotFound


class CustomerNotFound(ResourceNotFound):
    code = "customer_not_found"
