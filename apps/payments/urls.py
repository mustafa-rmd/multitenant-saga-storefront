from django.urls import path

from apps.payments import views

urlpatterns = [
    path(
        "payment-gateways",
        views.PublicGatewayListView.as_view(),
        name="public-gateway-list",
    ),
    path(
        "payment-gateways/<str:gateway_name>",
        views.PublicGatewayDetailView.as_view(),
        name="public-gateway-detail",
    ),
    path(
        "customers/<uuid:customer_id>/payment-methods",
        views.CustomerPaymentMethodListCreateView.as_view(),
        name="customer-payment-method-list-create",
    ),
    path(
        "customers/<uuid:customer_id>/payment-methods/<uuid:method_id>",
        views.CustomerPaymentMethodDetailView.as_view(),
        name="customer-payment-method-detail",
    ),
    path(
        "customers/<uuid:customer_id>/payment-methods/<uuid:method_id>/default",
        views.CustomerPaymentMethodDefaultView.as_view(),
        name="customer-payment-method-default",
    ),
    path(
        "webhooks/payments/<str:gateway_name>",
        views.PaymentWebhookView.as_view(),
        name="payment-webhook",
    ),
]
