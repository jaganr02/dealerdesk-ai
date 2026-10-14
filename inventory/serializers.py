"""
Serializers for DealerDesk inventory, products, dealers, and orders.
Fully reconciled with API_CONTRACT.md specifications.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from rest_framework import serializers

from dealerdesk.exceptions import ValidationException
from inventory.models import Dealer, Inventory, Order, OrderItem, Product


class ProductSerializer(serializers.ModelSerializer):
    """
    Contract Product Representation:
    {"sku": "...", "name": "...", "category": "...", "brand": "...",
     "vehicle_fitment": "...", "price": "1459.50", "stock": 136, "description": "..."}
    """
    price = serializers.SerializerMethodField()
    stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "sku",
            "name",
            "category",
            "brand",
            "vehicle_fitment",
            "price",
            "stock",
            "description",
        ]

    def get_price(self, obj) -> str:
        return f"{obj.price:.2f}"


class ProductCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new product. Creates product with stock 0.
    Price must be > 0 with at most 2 decimals.
    """
    price = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)

    class Meta:
        model = Product
        fields = [
            "sku",
            "name",
            "category",
            "brand",
            "vehicle_fitment",
            "price",
            "description",
        ]

    def validate_price(self, value):
        if value <= Decimal("0.00"):
            raise ValidationException("Price must be greater than 0.")
        # Ensure at most 2 decimal places
        if value.as_tuple().exponent < -2:
            raise ValidationException("Price must have at most 2 decimal places.")
        return value


class ProductUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for partial updates to a product (PATCH /api/products/{sku}/).
    SKU cannot change.
    """
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, coerce_to_string=False)

    class Meta:
        model = Product
        fields = [
            "name",
            "category",
            "brand",
            "vehicle_fitment",
            "price",
            "description",
        ]

    def validate_price(self, value):
        if value is not None:
            if value <= Decimal("0.00"):
                raise ValidationException("Price must be greater than 0.")
            if value.as_tuple().exponent < -2:
                raise ValidationException("Price must have at most 2 decimal places.")
        return value


class InventoryUpdateSerializer(serializers.Serializer):
    """
    Serializer for PUT /api/inventory/{sku}/
    Body: {"quantity": 25, "reason": "stock count correction"}
    """
    quantity = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_quantity(self, value):
        if value < 0:
            raise ValidationException("Quantity must be an integer >= 0.")
        return value


class DealerSerializer(serializers.ModelSerializer):
    """
    Contract Dealer Representation:
    {"id": 7, "dealer_code": "DLR-007", "name": "...", "city": "...",
     "phone": "...", "email": "...", "gstin": "...", "credit_limit": "100000.00"}
    """
    credit_limit = serializers.SerializerMethodField()

    class Meta:
        model = Dealer
        fields = [
            "id",
            "dealer_code",
            "name",
            "city",
            "phone",
            "email",
            "gstin",
            "credit_limit",
        ]

    def get_credit_limit(self, obj) -> str:
        return f"{obj.credit_limit:.2f}"


class DealerCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for POST /api/dealers/
    dealer_code and name required, other fields optional.
    """
    credit_limit = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        default=Decimal("0.00"),
        coerce_to_string=False,
    )

    class Meta:
        model = Dealer
        fields = [
            "dealer_code",
            "name",
            "city",
            "phone",
            "email",
            "gstin",
            "credit_limit",
        ]

    def validate_credit_limit(self, value):
        if value < Decimal("0.00"):
            raise ValidationException("Credit limit must be a positive number or zero.")
        return value


class OrderItemSerializer(serializers.ModelSerializer):
    """
    Contract OrderItem Representation:
    {"sku": "BRK-1044", "name": "...", "quantity": 3, "unit_price": "1459.50",
     "line_subtotal": "4378.50", "line_tax": "788.13", "line_total": "5166.63"}
    """
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    unit_price = serializers.SerializerMethodField()
    line_subtotal = serializers.SerializerMethodField()
    line_tax = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "sku",
            "name",
            "quantity",
            "unit_price",
            "line_subtotal",
            "line_tax",
            "line_total",
        ]

    def get_unit_price(self, obj) -> str:
        return f"{obj.unit_price:.2f}"

    def get_line_subtotal(self, obj) -> str:
        return f"{obj.line_subtotal:.2f}"

    def get_line_tax(self, obj) -> str:
        return f"{obj.line_tax:.2f}"

    def get_line_total(self, obj) -> str:
        return f"{obj.line_total:.2f}"


class OrderSerializer(serializers.ModelSerializer):
    """
    Contract Order Representation:
    {"order_number": "ORD-20261012-0007", "dealer_id": 7, "status": "DRAFT",
     "items": [...], "subtotal": "4378.50", "tax_total": "788.13", "grand_total": "5166.63",
     "created_at": "...", "updated_at": "..."}
    """
    dealer_id = serializers.IntegerField(source="dealer.id", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    tax_total = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z")
    updated_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z")

    class Meta:
        model = Order
        fields = [
            "order_number",
            "dealer_id",
            "status",
            "items",
            "subtotal",
            "tax_total",
            "grand_total",
            "created_at",
            "updated_at",
        ]

    def get_subtotal(self, obj) -> str:
        return f"{obj.subtotal:.2f}"

    def get_tax_total(self, obj) -> str:
        return f"{obj.tax_total:.2f}"

    def get_grand_total(self, obj) -> str:
        return f"{obj.grand_total:.2f}"


class OrderItemInputSerializer(serializers.Serializer):
    sku = serializers.CharField(required=True)
    quantity = serializers.IntegerField(required=True, min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    dealer_id = serializers.IntegerField(required=True)
    items = OrderItemInputSerializer(many=True, required=True)

    def validate_items(self, value):
        if not value:
            raise ValidationException("Order must contain at least one item.")
        # Check duplicate SKUs
        skus = [item["sku"].strip() for item in value]
        if len(skus) != len(set(skus)):
            raise ValidationException("The same SKU must not appear twice in an order.")
        return value


class OrderUpdateSerializer(serializers.Serializer):
    items = OrderItemInputSerializer(many=True, required=True)

    def validate_items(self, value):
        if not value:
            raise ValidationException("Order must contain at least one item.")
        skus = [item["sku"].strip() for item in value]
        if len(skus) != len(set(skus)):
            raise ValidationException("The same SKU must not appear twice in an order.")
        return value
