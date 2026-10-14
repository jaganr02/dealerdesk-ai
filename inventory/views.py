"""
Views for DealerDesk Products, Inventory, Dealers, and Orders.
Fully aligned with API_CONTRACT.md.
"""

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from django.views.generic import TemplateView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from dealerdesk.exceptions import (
    DuplicateException,
    IdempotencyConflictException,
    InsufficientStockException,
    InvalidTransitionException,
    NotFoundException,
    OrderLockedException,
    ValidationException,
)
from dealerdesk.pagination import StandardPagination
from inventory.models import Dealer, Inventory, Order, OrderItem, Product
from inventory.serializers import (
    DealerCreateSerializer,
    DealerSerializer,
    InventoryUpdateSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    OrderUpdateSerializer,
    ProductCreateSerializer,
    ProductSerializer,
    ProductUpdateSerializer,
)


class DealerPortalView(TemplateView):
    """
    Serves the modern, responsive DealerDesk Dealer Portal UI.
    """
    template_name = "dealer/index.html"


# ============================================================================
# Products API (§4)
# ============================================================================

class ProductListCreateView(APIView):
    """
    GET /api/products/  - Paginated list with filters (search, category, vehicle).
    POST /api/products/ - Creates product with stock 0. Duplicate SKU -> 409 DUPLICATE.
    """
    permission_classes = [AllowAny]
    pagination_class = StandardPagination

    @extend_schema(
        summary="List products",
        parameters=[
            OpenApiParameter("search", str, description="Case-insensitive match on sku, name or brand"),
            OpenApiParameter("category", str, description="Exact category match"),
            OpenApiParameter("vehicle", str, description="Case-insensitive substring of vehicle_fitment"),
            OpenApiParameter("page", int, description="Page number (1-based)"),
            OpenApiParameter("page_size", int, description="Page size (default 20, max 100)"),
        ],
        responses={200: ProductSerializer(many=True)},
    )
    def get(self, request):
        queryset = Product.objects.select_related("inventory").filter(is_active=True).order_by("sku")

        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(sku__icontains=search) | Q(name__icontains=search) | Q(brand__icontains=search)
            )

        category = request.query_params.get("category", "").strip()
        if category:
            queryset = queryset.filter(category__iexact=category)

        vehicle = request.query_params.get("vehicle", "").strip()
        if vehicle:
            queryset = queryset.filter(vehicle_fitment__icontains=vehicle)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = ProductSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Create product",
        request=ProductCreateSerializer,
        responses={201: ProductSerializer},
    )
    def post(self, request):
        sku = request.data.get("sku", "").strip() if isinstance(request.data.get("sku"), str) else ""
        if Product.objects.filter(sku=sku).exists():
            raise DuplicateException(f"Product with SKU '{sku}' already exists.")

        serializer = ProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            product = serializer.save()
            Inventory.objects.create(product=product, quantity=0)

        response_serializer = ProductSerializer(product)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ProductDetailView(APIView):
    """
    GET /api/products/{sku}/   - Product detail, or 404 NOT_FOUND.
    PATCH /api/products/{sku}/ - Partial update. SKU cannot change.
    """
    permission_classes = [AllowAny]

    def get_object(self, sku):
        product = Product.objects.select_related("inventory").filter(sku=sku).first()
        if not product:
            raise NotFoundException(f"Product with SKU '{sku}' not found.")
        return product

    @extend_schema(summary="Get product by SKU", responses={200: ProductSerializer})
    def get(self, request, sku):
        product = self.get_object(sku)
        serializer = ProductSerializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Partial update product",
        request=ProductUpdateSerializer,
        responses={200: ProductSerializer},
    )
    def patch(self, request, sku):
        product = self.get_object(sku)

        # SKU cannot change
        if "sku" in request.data and request.data["sku"] != sku:
            raise ValidationException("Product SKU cannot be changed.")

        serializer = ProductUpdateSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        response_serializer = ProductSerializer(product)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


# ============================================================================
# Inventory API (§5)
# ============================================================================

class InventoryUpdateView(APIView):
    """
    PUT /api/inventory/{sku}/ - Set available stock. Quantity must be integer >= 0.
    Returns 200 {"sku": "...", "quantity": 25}.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Set inventory quantity",
        request=InventoryUpdateSerializer,
        responses={200: {"sku": "str", "quantity": "int"}},
    )
    def put(self, request, sku):
        product = Product.objects.filter(sku=sku).first()
        if not product:
            raise NotFoundException(f"Product with SKU '{sku}' not found.")

        serializer = InventoryUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        quantity = serializer.validated_data["quantity"]

        with transaction.atomic():
            inv, _ = Inventory.objects.get_or_create(product=product)
            inv.quantity = quantity
            inv.save()

        return Response({"sku": sku, "quantity": quantity}, status=status.HTTP_200_OK)


# ============================================================================
# Dealers API (§6)
# ============================================================================

class DealerListCreateView(APIView):
    """
    GET /api/dealers/  - Paginated list of dealers.
    POST /api/dealers/ - Creates dealer. Duplicate dealer_code -> 409 DUPLICATE.
    """
    permission_classes = [AllowAny]
    pagination_class = StandardPagination

    @extend_schema(summary="List dealers", responses={200: DealerSerializer(many=True)})
    def get(self, request):
        queryset = Dealer.objects.filter(is_active=True).order_by("id")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = DealerSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Create dealer",
        request=DealerCreateSerializer,
        responses={201: DealerSerializer},
    )
    def post(self, request):
        dealer_code = request.data.get("dealer_code", "").strip() if isinstance(request.data.get("dealer_code"), str) else ""
        if Dealer.objects.filter(dealer_code=dealer_code).exists():
            raise DuplicateException(f"Dealer with code '{dealer_code}' already exists.")

        serializer = DealerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dealer = serializer.save()

        response_serializer = DealerSerializer(dealer)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DealerDetailView(APIView):
    """
    GET /api/dealers/{id}/ - Dealer detail, or 404 NOT_FOUND.
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Get dealer by ID", responses={200: DealerSerializer})
    def get(self, request, id):
        dealer = Dealer.objects.filter(id=id).first()
        if not dealer:
            raise NotFoundException(f"Dealer with ID '{id}' not found.")
        serializer = DealerSerializer(dealer)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ============================================================================
# Orders API (§7)
# ============================================================================

def _generate_order_number() -> str:
    """Generate order number ORD-YYYYMMDD-NNNN in Asia/Kolkata timezone."""
    now = timezone.localtime(timezone.now())
    date_str = now.strftime("%Y%m%d")
    prefix = f"ORD-{date_str}-"

    # Find highest sequence today
    last_order = (
        Order.objects.filter(order_number__startswith=prefix)
        .order_by("-order_number")
        .first()
    )
    if last_order:
        try:
            seq_part = last_order.order_number.split("-")[-1]
            next_seq = int(seq_part) + 1
        except (ValueError, IndexError):
            next_seq = 1
    else:
        next_seq = 1

    return f"{prefix}{next_seq:04d}"


def _calculate_lines(items_data):
    """
    Validate SKUs and quantities, and calculate exact lines, taxes, and totals.
    line_subtotal = unit_price * quantity
    line_tax = (line_subtotal * 0.18).quantize(0.01, ROUND_HALF_UP)
    line_total = line_subtotal + line_tax
    """
    line_results = []
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")

    for item in items_data:
        sku = item["sku"].strip()
        quantity = item["quantity"]

        product = Product.objects.filter(sku=sku).first()
        if not product:
            raise ValidationException(f"Unknown SKU: '{sku}'")

        if quantity < 1:
            raise ValidationException(f"Quantity for SKU '{sku}' must be an integer >= 1.")

        unit_price = product.price
        line_sub = (unit_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line_tx = (line_sub * Decimal("0.18")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line_tot = line_sub + line_tx

        subtotal += line_sub
        tax_total += line_tx

        line_results.append({
            "product": product,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_subtotal": line_sub,
            "line_tax": line_tx,
            "line_total": line_tot,
        })

    grand_total = subtotal + tax_total
    return line_results, subtotal, tax_total, grand_total


class OrderListCreateView(APIView):
    """
    GET /api/orders/  - Paginated list. Filters: dealer_id, status.
    POST /api/orders/ - Creates a DRAFT order. Handles Idempotency-Key.
    """
    permission_classes = [AllowAny]
    pagination_class = StandardPagination

    @extend_schema(
        summary="List orders",
        parameters=[
            OpenApiParameter("dealer_id", int, description="Filter by dealer ID"),
            OpenApiParameter("status", str, description="Filter by status (e.g. DRAFT, CONFIRMED)"),
        ],
        responses={200: OrderSerializer(many=True)},
    )
    def get(self, request):
        queryset = (
            Order.objects.select_related("dealer")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )

        dealer_id = request.query_params.get("dealer_id")
        if dealer_id:
            try:
                queryset = queryset.filter(dealer_id=int(dealer_id))
            except ValueError:
                raise ValidationException("Invalid dealer_id query parameter.")

        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = OrderSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Create draft order",
        request=OrderCreateSerializer,
        responses={201: OrderSerializer},
    )
    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dealer_id = serializer.validated_data["dealer_id"]
        items_data = serializer.validated_data["items"]

        dealer = Dealer.objects.filter(id=dealer_id).first()
        if not dealer:
            raise ValidationException(f"Unknown dealer_id: '{dealer_id}'")

        # Idempotency check
        idempotency_key = request.headers.get("Idempotency-Key") or request.META.get("HTTP_IDEMPOTENCY_KEY")
        if idempotency_key:
            idempotency_key = idempotency_key.strip()
            # Normalize request payload for hash comparison
            body_repr = json.dumps(
                {"dealer_id": dealer_id, "items": sorted(items_data, key=lambda x: x["sku"])},
                sort_keys=True,
            )
            body_hash = hashlib.sha256(body_repr.encode("utf-8")).hexdigest()

            existing_order = Order.objects.filter(idempotency_key=idempotency_key).first()
            if existing_order:
                stored_hash = existing_order.notes.split("hash:")[-1].strip() if "hash:" in existing_order.notes else ""
                if stored_hash == body_hash:
                    # Same key with same body -> return original order
                    return Response(OrderSerializer(existing_order).data, status=status.HTTP_200_OK)
                else:
                    raise IdempotencyConflictException("Same Idempotency-Key reused with a different request body.")

        # Calculate line items
        lines, subtotal, tax_total, grand_total = _calculate_lines(items_data)

        # Retry loop for order number uniqueness
        with transaction.atomic():
            for _ in range(5):
                order_number = _generate_order_number()
                if not Order.objects.filter(order_number=order_number).exists():
                    break

            notes = f"hash:{body_hash}" if idempotency_key else ""
            order = Order.objects.create(
                order_number=order_number,
                dealer=dealer,
                status=Order.Status.DRAFT,
                subtotal=subtotal,
                tax_total=tax_total,
                grand_total=grand_total,
                idempotency_key=idempotency_key,
                notes=notes,
            )

            for line in lines:
                OrderItem.objects.create(
                    order=order,
                    product=line["product"],
                    quantity=line["quantity"],
                    unit_price=line["unit_price"],
                    line_subtotal=line["line_subtotal"],
                    line_tax=line["line_tax"],
                    line_total=line["line_total"],
                )

        response_serializer = OrderSerializer(order)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class OrderDetailUpdateView(APIView):
    """
    GET /api/orders/{order_number}/ - Order detail, or 404 NOT_FOUND.
    PUT /api/orders/{order_number}/ - Replaces all items. Only while DRAFT, else 409 ORDER_LOCKED.
    """
    permission_classes = [AllowAny]

    def get_object(self, order_number):
        order = (
            Order.objects.select_related("dealer")
            .prefetch_related("items__product")
            .filter(order_number=order_number)
            .first()
        )
        if not order:
            raise NotFoundException(f"Order '{order_number}' not found.")
        return order

    @extend_schema(summary="Get order by number", responses={200: OrderSerializer})
    def get(self, request, order_number):
        order = self.get_object(order_number)
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Replace order items (Draft only)",
        request=OrderUpdateSerializer,
        responses={200: OrderSerializer},
    )
    def put(self, request, order_number):
        order = self.get_object(order_number)

        if order.status != Order.Status.DRAFT:
            raise OrderLockedException(f"Editing an order that is not DRAFT (status is {order.status}).")

        serializer = OrderUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        items_data = serializer.validated_data["items"]
        lines, subtotal, tax_total, grand_total = _calculate_lines(items_data)

        with transaction.atomic():
            # Replace items
            order.items.all().delete()

            order.subtotal = subtotal
            order.tax_total = tax_total
            order.grand_total = grand_total
            order.save()

            for line in lines:
                OrderItem.objects.create(
                    order=order,
                    product=line["product"],
                    quantity=line["quantity"],
                    unit_price=line["unit_price"],
                    line_subtotal=line["line_subtotal"],
                    line_tax=line["line_tax"],
                    line_total=line["line_total"],
                )

        response_serializer = OrderSerializer(order)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


# ============================================================================
# Order Lifecycle Transitions (§7.2, §7.3)
# ============================================================================

class OrderConfirmView(APIView):
    """
    POST /api/orders/{order_number}/confirm/
    DRAFT -> CONFIRMED. Validates stock, deducts stock, locks unit prices.
    Short stock -> 409 INSUFFICIENT_STOCK.
    Invalid transition -> 409 INVALID_TRANSITION.
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Confirm order", responses={200: OrderSerializer})
    def post(self, request, order_number):
        order = (
            Order.objects.select_related("dealer")
            .prefetch_related("items__product__inventory")
            .filter(order_number=order_number)
            .first()
        )
        if not order:
            raise NotFoundException(f"Order '{order_number}' not found.")

        if order.status != Order.Status.DRAFT:
            raise InvalidTransitionException(
                f"Cannot confirm order from status '{order.status}'. Only DRAFT orders can be confirmed."
            )

        with transaction.atomic():
            # Stock check
            short_lines = []
            message_sentences = []

            for item in order.items.all():
                inv = getattr(item.product, "inventory", None)
                avail = inv.quantity if inv else 0
                if item.quantity > avail:
                    short_lines.append({
                        "sku": item.product.sku,
                        "requested": item.quantity,
                        "available": avail,
                    })
                    message_sentences.append(
                        f"Insufficient stock for {item.product.name}. Available: {avail}, Requested: {item.quantity}"
                    )

            if short_lines:
                raise InsufficientStockException(
                    message=". ".join(message_sentences),
                    details=short_lines,
                )

            # Deduct stock
            for item in order.items.all():
                inv = item.product.inventory
                inv.quantity -= item.quantity
                inv.save()

            order.status = Order.Status.CONFIRMED
            order.confirmed_at = timezone.now()
            order.save()

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class OrderCancelView(APIView):
    """
    POST /api/orders/{order_number}/cancel/
    DRAFT -> CANCELLED, or CONFIRMED -> CANCELLED (restores stock).
    DISPATCHED/DELIVERED cannot be cancelled -> 409 INVALID_TRANSITION.
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Cancel order", responses={200: OrderSerializer})
    def post(self, request, order_number):
        order = (
            Order.objects.select_related("dealer")
            .prefetch_related("items__product__inventory")
            .filter(order_number=order_number)
            .first()
        )
        if not order:
            raise NotFoundException(f"Order '{order_number}' not found.")

        if order.status not in (Order.Status.DRAFT, Order.Status.CONFIRMED):
            raise InvalidTransitionException(
                f"Cannot cancel order from status '{order.status}'."
            )

        with transaction.atomic():
            if order.status == Order.Status.CONFIRMED:
                # Restore stock
                for item in order.items.all():
                    inv = item.product.inventory
                    inv.quantity += item.quantity
                    inv.save()

            order.status = Order.Status.CANCELLED
            order.cancelled_at = timezone.now()
            order.save()

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class OrderDispatchView(APIView):
    """
    POST /api/orders/{order_number}/dispatch/
    CONFIRMED -> DISPATCHED.
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Dispatch order", responses={200: OrderSerializer})
    def post(self, request, order_number):
        order = Order.objects.filter(order_number=order_number).first()
        if not order:
            raise NotFoundException(f"Order '{order_number}' not found.")

        if order.status != Order.Status.CONFIRMED:
            raise InvalidTransitionException(
                f"Cannot dispatch order from status '{order.status}'. Only CONFIRMED orders can be dispatched."
            )

        order.status = Order.Status.DISPATCHED
        order.dispatched_at = timezone.now()
        order.save()

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class OrderDeliverView(APIView):
    """
    POST /api/orders/{order_number}/deliver/
    DISPATCHED -> DELIVERED.
    """
    permission_classes = [AllowAny]

    @extend_schema(summary="Deliver order", responses={200: OrderSerializer})
    def post(self, request, order_number):
        order = Order.objects.filter(order_number=order_number).first()
        if not order:
            raise NotFoundException(f"Order '{order_number}' not found.")

        if order.status != Order.Status.DISPATCHED:
            raise InvalidTransitionException(
                f"Cannot deliver order from status '{order.status}'. Only DISPATCHED orders can be delivered."
            )

        order.status = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.save()

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)
