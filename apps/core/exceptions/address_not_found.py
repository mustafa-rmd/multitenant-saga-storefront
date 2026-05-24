from apps.core.exceptions.resource_not_found import ResourceNotFound


class AddressNotFound(ResourceNotFound):
    code = "address_not_found"
