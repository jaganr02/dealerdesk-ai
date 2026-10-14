"""
Database models for DealerDesk inventory, products, dealers, and orders.
Fully reconciled with VIKMO DealerDesk API_CONTRACT.md.
"""

from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import CheckConstraint, Index, Q, UniqueConstraint


class Product(models.Model):
    """
    Represents an automotive spare part in the distributor's catalogue (~600 products).
    Supplies 25 dealers across South India from a central Bengaluru warehouse.
    Reconciled with API_CONTRACT.md section 4.
    """
    sku = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Distributor SKU / Part number (unique identifier across catalogue)."
    )
    name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Standard trade / part name."
    )
    category = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Part category (e.g., Brake Systems, Engine Components, Suspension, Electrical)."
    )
    brand = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Part manufacturer / brand (e.g., Endurance, Brembo, NGK, Bosch)."
    )
    vehicle_fitment = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Compatible vehicle make and model (e.g., Bajaj Pulsar 150, Royal Enfield Classic 350)."
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Current distributor catalogue unit price in INR (excluding GST). Must be > 0."
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Detailed part description, fitment details, and vehicle compatibility."
    )
    supplier_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="External supplier / OEM identifier for catalogue synchronization."
    )
    supplier_sku = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Supplier-specific part number used during sync and reordering."
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this part is available for dealer orders."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the product was added to catalogue."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp of latest product update."
    )

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["sku"]
        constraints = [
            CheckConstraint(
                condition=Q(price__gt=Decimal("0.00")),
                name="product_price_positive"
            )
        ]

    @property
    def stock(self) -> int:
        """Expose current available quantity from associated Inventory record."""
        inv = getattr(self, "inventory", None)
        return inv.quantity if inv else 0

    def __str__(self):
        return f"{self.sku} - {self.name} (₹{self.price})"


class Inventory(models.Model):
    """
    Represents warehouse stock availability for a product at the central Bengaluru facility.
    Relationship cardinality: 1:1 with Product for the centralized distributor model.
    Reconciled with API_CONTRACT.md section 5.
    """
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name="inventory",
        help_text="Associated product in catalogue."
    )
    quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Available stock physical quantity in warehouse."
    )
    reserved_quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Quantity allocated to confirmed orders awaiting dispatch."
    )
    reorder_threshold = models.PositiveIntegerField(
        default=10,
        help_text="Threshold stock count triggering replenishment alerts."
    )
    last_restocked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of latest stock arrival/restock."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp of latest inventory update."
    )

    class Meta:
        verbose_name = "Inventory"
        verbose_name_plural = "Inventories"
        constraints = [
            CheckConstraint(
                condition=Q(quantity__gte=0),
                name="inventory_quantity_non_negative"
            ),
            CheckConstraint(
                condition=Q(reserved_quantity__gte=0),
                name="inventory_reserved_quantity_non_negative"
            ),
        ]

    @property
    def available_for_order(self) -> int:
        """Net quantity available for new orders after subtracting reservations."""
        return max(0, self.quantity - self.reserved_quantity)

    def __str__(self):
        return f"Stock for {self.product.sku}: {self.quantity} on hand ({self.reserved_quantity} reserved)"


class Dealer(models.Model):
    """
    Represents an authorized B2B dealer customer across South India.
    Reconciled with API_CONTRACT.md section 6:
    Fields: id, dealer_code, name, city, phone, email, gstin, credit_limit.
    Authentication user is strictly optional.
    """
    dealer_code = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Unique dealer account code (e.g., DLR-001, DLR-KA-001)."
    )
    name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Registered dealership trade/legal business name."
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="City / District (e.g., Bengaluru, Chennai, Kochi, Hyderabad)."
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="Contact telephone / mobile number."
    )
    email = models.EmailField(
        blank=True,
        default="",
        db_index=True,
        help_text="Primary business email for communications and order notices."
    )
    gstin = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        default=None,
        help_text="15-character Goods and Services Tax Identification Number (GSTIN)."
    )
    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Approved credit limit in INR."
    )
    # Additional optional fields preserved for distributor operations
    contact_person = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Primary authorized contact person at dealership."
    )
    address = models.TextField(
        blank=True,
        default="",
        help_text="Dealership physical address for dispatch and billing."
    )
    state = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="State in South India (e.g., Karnataka, Tamil Nadu, Kerala)."
    )
    pincode = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Postal PIN code."
    )
    outstanding_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Current outstanding balance in INR."
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether dealer account is active and allowed to place orders."
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dealer_profile",
        help_text="Optional associated user account. Authentication is NOT required by API contract."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Registration timestamp."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Latest update timestamp."
    )

    class Meta:
        verbose_name = "Dealer"
        verbose_name_plural = "Dealers"
        ordering = ["name"]
        constraints = [
            CheckConstraint(
                condition=Q(credit_limit__gte=Decimal("0.00")),
                name="dealer_credit_limit_non_negative"
            )
        ]

    def __init__(self, *args, **kwargs):
        # Support business_name kwarg for backward compatibility
        if "business_name" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs.pop("business_name")
        super().__init__(*args, **kwargs)

    @property
    def business_name(self) -> str:
        """Alias for name for backward compatibility."""
        return self.name

    @business_name.setter
    def business_name(self, value: str):
        self.name = value

    def clean(self):
        super().clean()
        if self.user and hasattr(self.user, "role") and self.user.role != self.user.Role.DEALER:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                "A dealer profile can only be associated with a user account having the DEALER role."
            )

    def __str__(self):
        return f"{self.dealer_code} - {self.name} ({self.city})"


class Order(models.Model):
    """
    Represents an order placed by an authorized dealer.
    Reconciled with API_CONTRACT.md section 7:
    Fields: order_number, dealer_id, status, subtotal, tax_total, grand_total, created_at, updated_at.
    """
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        DISPATCHED = "DISPATCHED", "Dispatched"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    order_number = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Unique human-readable order number (e.g., ORD-20261012-0001)."
    )
    dealer = models.ForeignKey(
        Dealer,
        on_delete=models.PROTECT,
        related_name="orders",
        help_text="Dealer placing the order. PROTECT prevents deleting dealers with order history."
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        help_text="Lifecycle status of the order."
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Sum of line item amounts before taxes in INR."
    )
    tax_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Total GST calculated across order items in INR."
    )
    grand_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Grand total payable in INR (subtotal + tax_total)."
    )
    idempotency_key = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Unique client token ensuring duplicate-safe order submissions."
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Optional instructions, delivery notes, or dealer remarks."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Creation timestamp."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last modification timestamp."
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the order was locked and confirmed."
    )
    dispatched_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when shipment departed distributor warehouse."
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when shipment was received by dealer."
    )
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when order was cancelled."
    )

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ["-created_at"]
        indexes = [
            Index(fields=["dealer", "status"], name="idx_order_dealer_status"),
            Index(fields=["status", "created_at"], name="idx_order_status_created"),
        ]
        constraints = [
            CheckConstraint(
                condition=Q(subtotal__gte=Decimal("0.00")),
                name="order_subtotal_non_negative"
            ),
            CheckConstraint(
                condition=Q(tax_total__gte=Decimal("0.00")),
                name="order_tax_total_non_negative"
            ),
            CheckConstraint(
                condition=Q(grand_total__gte=Decimal("0.00")),
                name="order_grand_total_non_negative"
            ),
        ]

    def __init__(self, *args, **kwargs):
        # Backward compatibility aliases
        if "gst_amount" in kwargs and "tax_total" not in kwargs:
            kwargs["tax_total"] = kwargs.pop("gst_amount")
        if "total_amount" in kwargs and "grand_total" not in kwargs:
            kwargs["grand_total"] = kwargs.pop("total_amount")
        super().__init__(*args, **kwargs)

    @property
    def gst_amount(self) -> Decimal:
        """Alias for tax_total for backward compatibility."""
        return self.tax_total

    @gst_amount.setter
    def gst_amount(self, value: Decimal):
        self.tax_total = value

    @property
    def total_amount(self) -> Decimal:
        """Alias for grand_total for backward compatibility."""
        return self.grand_total

    @total_amount.setter
    def total_amount(self, value: Decimal):
        self.grand_total = value

    def __str__(self):
        return f"{self.order_number} - {self.dealer.name} ({self.status})"


class OrderItem(models.Model):
    """
    Represents an individual product line item within an order.
    Reconciled with API_CONTRACT.md section 7:
    Fields: sku, name, quantity, unit_price, line_subtotal, line_tax, line_total.
    Preserves historical unit prices and taxes as snapshots at order creation/confirmation.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        help_text="Parent order containing this line item. CASCADE deletes line items when order is removed."
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="order_items",
        help_text="Product ordered. PROTECT preserves audit trail and prevents deleting catalogue items that were ordered."
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Quantity ordered (must be an integer >= 1)."
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Snapshotted unit price (excluding GST) in INR at the time of order."
    )
    line_subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Snapshotted line subtotal: unit_price * quantity."
    )
    line_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Snapshotted line tax: 18% GST rounded to 2 decimals using ROUND_HALF_UP."
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Snapshotted line total: line_subtotal + line_tax."
    )
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("18.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text="Applicable GST percentage rate snapshot (default 18.00%)."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Line item creation timestamp."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Line item last update timestamp."
    )

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
        ordering = ["id"]
        constraints = [
            UniqueConstraint(
                fields=["order", "product"],
                name="unique_product_per_order"
            ),
            CheckConstraint(
                condition=Q(quantity__gte=1),
                name="orderitem_quantity_positive"
            ),
            CheckConstraint(
                condition=Q(unit_price__gte=Decimal("0.00")),
                name="orderitem_unit_price_non_negative"
            ),
            CheckConstraint(
                condition=Q(line_subtotal__gte=Decimal("0.00")),
                name="orderitem_line_subtotal_non_negative"
            ),
            CheckConstraint(
                condition=Q(line_tax__gte=Decimal("0.00")),
                name="orderitem_line_tax_non_negative"
            ),
            CheckConstraint(
                condition=Q(line_total__gte=Decimal("0.00")),
                name="orderitem_line_total_non_negative"
            ),
        ]

    def __init__(self, *args, **kwargs):
        # Backward compatibility alias
        if "gst_amount" in kwargs and "line_tax" not in kwargs:
            kwargs["line_tax"] = kwargs.pop("gst_amount")
        super().__init__(*args, **kwargs)

    @property
    def gst_amount(self) -> Decimal:
        """Alias for line_tax for backward compatibility."""
        return self.line_tax

    @gst_amount.setter
    def gst_amount(self, value: Decimal):
        self.line_tax = value

    @property
    def sku(self) -> str:
        return self.product.sku

    @property
    def name(self) -> str:
        return self.product.name

    def __str__(self):
        return f"{self.quantity}x {self.product.sku} on {self.order.order_number}"
