from django.urls import path

from apps.payments.views.admin import (
    AdminGatewayConfigDetailView,
    AdminGatewayConfigListCreateView,
)

urlpatterns = [
    path(
        "payment-gateways",
        AdminGatewayConfigListCreateView.as_view(),
        name="admin-gateway-list-create",
    ),
    path(
        "payment-gateways/<uuid:config_id>",
        AdminGatewayConfigDetailView.as_view(),
        name="admin-gateway-detail",
    ),
]
