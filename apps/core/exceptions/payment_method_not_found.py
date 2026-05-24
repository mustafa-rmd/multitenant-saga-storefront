from apps.core.exceptions.resource_not_found import ResourceNotFound


class PaymentMethodNotFound(ResourceNotFound):
    code = "payment_method_not_found"
