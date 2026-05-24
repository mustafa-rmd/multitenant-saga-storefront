from django.urls import path

from apps.coupons.views.admin import AdminCouponDetailView, AdminCouponListCreateView

urlpatterns = [
    path("coupons", AdminCouponListCreateView.as_view(), name="admin-coupon-list-create"),
    path("coupons/<uuid:coupon_id>", AdminCouponDetailView.as_view(), name="admin-coupon-detail"),
]
