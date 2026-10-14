"""
URL configuration for inventory app Core APIs.
Fully aligned with API_CONTRACT.md endpoints.
"""

from django.urls import path
from inventory.views import (
    DealerDetailView,
    DealerListCreateView,
    InventoryUpdateView,
    OrderCancelView,
    OrderConfirmView,
    OrderDeliverView,
    OrderDetailUpdateView,
    OrderDispatchView,
    OrderListCreateView,
    ProductDetailView,
    ProductListCreateView,
)

urlpatterns = [
    # Products API (§4)
    path("products/", ProductListCreateView.as_view(), name="product-list-create"),
    path("products/<str:sku>/", ProductDetailView.as_view(), name="product-detail"),

    # Inventory API (§5)
    path("inventory/<str:sku>/", InventoryUpdateView.as_view(), name="inventory-update"),

    # Dealers API (§6)
    path("dealers/", DealerListCreateView.as_view(), name="dealer-list-create"),
    path("dealers/<int:id>/", DealerDetailView.as_view(), name="dealer-detail"),

    # Orders API (§7)
    path("orders/", OrderListCreateView.as_view(), name="order-list-create"),
    path("orders/<str:order_number>/", OrderDetailUpdateView.as_view(), name="order-detail-update"),
    path("orders/<str:order_number>/confirm/", OrderConfirmView.as_view(), name="order-confirm"),
    path("orders/<str:order_number>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
    path("orders/<str:order_number>/dispatch/", OrderDispatchView.as_view(), name="order-dispatch"),
    path("orders/<str:order_number>/deliver/", OrderDeliverView.as_view(), name="order-deliver"),
]
