"""
Cart views. Thin handlers that validate input, call services, serialize.

All mutation endpoints return the full cart state. All endpoints expect
the cart to belong to the authenticated customer (validated by the
service layer via customer_id).
"""

from apps.carts.views.cart_billing_address import CartBillingAddressView
from apps.carts.views.cart_checkout import CartCheckoutView
from apps.carts.views.cart_coupon_detail import CartCouponDetailView
from apps.carts.views.cart_coupon_preview import CartCouponPreviewView
from apps.carts.views.cart_coupons import CartCouponsView
from apps.carts.views.cart_detail import CartDetailView
from apps.carts.views.cart_item_detail import CartItemDetailView
from apps.carts.views.cart_items import CartItemsView
from apps.carts.views.cart_payment_method import CartPaymentMethodView
from apps.carts.views.cart_shipping_address import CartShippingAddressView

__all__ = [
    "CartDetailView",
    "CartItemsView",
    "CartItemDetailView",
    "CartCouponsView",
    "CartCouponDetailView",
    "CartCouponPreviewView",
    "CartShippingAddressView",
    "CartBillingAddressView",
    "CartPaymentMethodView",
    "CartCheckoutView",
]
