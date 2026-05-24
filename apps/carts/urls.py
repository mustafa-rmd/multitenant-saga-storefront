from django.urls import path

from apps.carts import views

# All cart endpoints operate on the authenticated customer's single active
# cart (resolved via X-Customer-Id + status=ACTIVE). There is no cart_id in
# the URL because customer_id already determines the cart uniquely.
urlpatterns = [
    path("cart", views.CartDetailView.as_view(), name="cart-detail"),
    path("cart/items", views.CartItemsView.as_view(), name="cart-items"),
    path(
        "cart/items/<uuid:item_id>",
        views.CartItemDetailView.as_view(),
        name="cart-item-detail",
    ),
    path("cart/coupons", views.CartCouponsView.as_view(), name="cart-coupons"),
    path(
        "cart/coupons/preview",
        views.CartCouponPreviewView.as_view(),
        name="cart-coupon-preview",
    ),
    path(
        "cart/coupons/<str:code>",
        views.CartCouponDetailView.as_view(),
        name="cart-coupon-detail",
    ),
    path(
        "cart/shipping-address",
        views.CartShippingAddressView.as_view(),
        name="cart-shipping-address",
    ),
    path(
        "cart/billing-address",
        views.CartBillingAddressView.as_view(),
        name="cart-billing-address",
    ),
    path(
        "cart/payment-method",
        views.CartPaymentMethodView.as_view(),
        name="cart-payment-method",
    ),
    path("cart/checkout", views.CartCheckoutView.as_view(), name="cart-checkout"),
]
