from django.urls import path

from apps.orders import views

urlpatterns = [
    path("orders", views.OrderListView.as_view(), name="order-list"),
    path("orders/<uuid:order_id>", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<uuid:order_id>/invoice", views.OrderInvoiceView.as_view(), name="order-invoice"),
    path("orders/<uuid:order_id>/cancel", views.OrderCancelView.as_view(), name="order-cancel"),
]
