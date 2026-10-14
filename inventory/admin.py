from django.contrib import admin
from .models import Dealer, Inventory, Order, OrderItem, Product


class InventoryInline(admin.StackedInline):
    model = Inventory
    can_delete = False
    verbose_name = "Warehouse Stock"
    verbose_name_plural = "Warehouse Stock"
    fields = ("quantity", "reserved_quantity", "reorder_threshold", "last_restocked_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "name",
        "brand",
        "category",
        "vehicle_fitment",
        "price",
        "stock",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "category", "brand")
    search_fields = ("sku", "name", "brand", "vehicle_fitment", "supplier_sku")
    readonly_fields = ("created_at", "updated_at")
    inlines = [InventoryInline]


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "quantity",
        "reserved_quantity",
        "available_for_order",
        "reorder_threshold",
        "last_restocked_at",
        "updated_at",
    )
    search_fields = ("product__sku", "product__name")
    list_filter = ("reorder_threshold",)
    readonly_fields = ("updated_at",)


@admin.register(Dealer)
class DealerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "dealer_code",
        "name",
        "city",
        "phone",
        "email",
        "gstin",
        "credit_limit",
        "is_active",
    )
    list_filter = ("is_active", "state", "city")
    search_fields = (
        "dealer_code",
        "name",
        "email",
        "phone",
        "gstin",
    )
    readonly_fields = ("created_at", "updated_at")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = (
        "product",
        "quantity",
        "unit_price",
        "line_subtotal",
        "line_tax",
        "line_total",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "dealer",
        "status",
        "subtotal",
        "tax_total",
        "grand_total",
        "created_at",
        "confirmed_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "order_number",
        "dealer__name",
        "dealer__dealer_code",
        "idempotency_key",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "confirmed_at",
        "dispatched_at",
        "delivered_at",
        "cancelled_at",
    )
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "product",
        "quantity",
        "unit_price",
        "line_subtotal",
        "line_tax",
        "line_total",
    )
    search_fields = ("order__order_number", "product__sku", "product__name")
    readonly_fields = ("created_at", "updated_at")
