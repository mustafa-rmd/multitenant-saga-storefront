from django.urls import path

from apps.orders.views.admin import (
    AdminOrderDetailView,
    AdminOrderListView,
    AdminOrderMarkPaidView,
    AdminOrderPaymentListView,
)

urlpatterns = [
    path("orders", AdminOrderListView.as_view(), name="admin-order-list"),
    path("orders/<uuid:order_id>", AdminOrderDetailView.as_view(), name="admin-order-detail"),
    path(
        "orders/<uuid:order_id>/payments",
        AdminOrderPaymentListView.as_view(),
        name="admin-order-payment-list",
    ),
    path(
        "orders/<uuid:order_id>/mark-paid",
        AdminOrderMarkPaidView.as_view(),
        name="admin-order-mark-paid",
    ),
]
