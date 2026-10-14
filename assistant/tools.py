"""
Tools for the VIKMO DealerDesk AI Assistant.

Exact tool names per API_CONTRACT.md (§9):
- search_parts
- check_stock
- create_draft_order
"""

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional
from django.db import transaction
from inventory.models import Dealer, Order, OrderItem, Product
from inventory.views import _calculate_lines, _generate_order_number


def search_parts(query: str, vehicle: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search the real product catalogue for vehicle parts by name, SKU, brand,
    category, or vehicle fitment.
    Returns database-backed product details with live stock and current price.
    """
    if not query or not isinstance(query, str):
        return []

    clean_query = query.strip()
    if not clean_query:
        return []

    # Stop words to ignore during token scoring
    stop_words = {"a", "an", "the", "for", "with", "of", "and", "in", "to", "at", "by", "from", "parts", "part"}
    tokens = [t.lower() for t in re.findall(r"\w+", clean_query) if t.lower() not in stop_words]

    vehicle_tokens = []
    if vehicle and isinstance(vehicle, str):
        vehicle_tokens = [t.lower() for t in re.findall(r"\w+", vehicle.strip()) if t.lower() not in stop_words]

    # Pre-filter query with Q objects to limit candidate set
    from django.db.models import Q
    candidate_q = (
        Q(sku__icontains=clean_query)
        | Q(name__icontains=clean_query)
        | Q(brand__icontains=clean_query)
        | Q(category__icontains=clean_query)
        | Q(vehicle_fitment__icontains=clean_query)
        | Q(description__icontains=clean_query)
    )
    for token in tokens:
        candidate_q |= (
            Q(sku__icontains=token)
            | Q(name__icontains=token)
            | Q(category__icontains=token)
            | Q(brand__icontains=token)
            | Q(vehicle_fitment__icontains=token)
        )
    if vehicle:
        candidate_q |= Q(vehicle_fitment__icontains=vehicle.strip())

    candidates = Product.objects.filter(candidate_q).select_related("inventory")[:100]
    if not candidates:
        # Fallback to general catalogue if query had no direct keyword hit
        candidates = Product.objects.all().select_related("inventory")[:100]

    scored = []
    query_lower = clean_query.lower()
    vehicle_lower = vehicle.strip().lower() if vehicle else ""

    for p in candidates:
        score = 0
        p_sku_lower = p.sku.lower()
        p_name_lower = p.name.lower()
        p_brand_lower = (p.brand or "").lower()
        p_cat_lower = (p.category or "").lower()
        p_fitment_lower = (p.vehicle_fitment or "").lower()
        p_desc_lower = (p.description or "").lower()

        # Exact SKU match
        if p_sku_lower == query_lower:
            score += 200
        elif p_sku_lower in query_lower or query_lower in p_sku_lower:
            score += 100

        # Exact phrase in name or fitment
        if query_lower in p_name_lower:
            score += 80
        if query_lower in p_fitment_lower:
            score += 60

        # Token overlap
        for t in tokens:
            if t == p_sku_lower:
                score += 50
            if t in p_name_lower:
                score += 25
            if t in p_fitment_lower:
                score += 20
            if t in p_cat_lower:
                score += 15
            if t in p_brand_lower:
                score += 15
            if t in p_desc_lower:
                score += 5

        # Vehicle fitment matching
        if vehicle_lower:
            if vehicle_lower in p_fitment_lower:
                score += 70
            for vt in vehicle_tokens:
                if vt in p_fitment_lower:
                    score += 15

        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_products = [p for _, p in scored[:8]]

    results = []
    for p in top_products:
        results.append({
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "brand": p.brand,
            "vehicle_fitment": p.vehicle_fitment,
            "price": f"{p.price:.2f}",
            "stock": p.stock,
            "description": p.description,
        })
    return results


def check_stock(sku: str) -> Dict[str, Any]:
    """
    Look up real-time available stock and details for a product from the live database.
    Never relies on stale conversation or LLM memory.
    """
    if not sku or not isinstance(sku, str):
        return {"error": "Invalid SKU provided."}

    clean_sku = sku.strip().upper()
    product = Product.objects.filter(sku=clean_sku).select_related("inventory").first()
    if not product:
        return {"error": f"Product with SKU '{sku}' not found in catalogue."}

    return {
        "sku": product.sku,
        "name": product.name,
        "brand": product.brand,
        "category": product.category,
        "vehicle_fitment": product.vehicle_fitment,
        "price": f"{product.price:.2f}",
        "stock": product.stock,
        "available": product.stock > 0,
    }


def create_draft_order(
    dealer_id: int,
    items: List[Dict[str, Any]],
    authorized_dealer_id: Optional[int] = None,
    actions_accumulator: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Create a DRAFT order for the dealer in the database.
    Enforces business rules:
    - Enforces dealer identity (must match authorized_dealer_id).
    - Validates dealer exists.
    - Validates non-empty items with positive integer quantities.
    - Uses authoritative catalogue prices and 18% GST calculation.
    - Creates only DRAFT orders.
    - Appends action: {"type": "draft_order_created", "order_number": "ORD-..."}
    """
    # Security: enforce dealer matching the active chat session context
    effective_dealer_id = authorized_dealer_id if authorized_dealer_id is not None else dealer_id

    dealer = Dealer.objects.filter(id=effective_dealer_id, is_active=True).first()
    if not dealer:
        return {"error": f"Dealer with ID {effective_dealer_id} does not exist or is inactive."}

    if not items or not isinstance(items, list):
        return {"error": "Order must contain at least one item."}

    # Validate item schema
    normalized_items = []
    seen_skus = set()
    for it in items:
        if not isinstance(it, dict) or "sku" not in it or "quantity" not in it:
            return {"error": "Each item must specify 'sku' and 'quantity'."}

        sku = str(it["sku"]).strip().upper()
        if not sku:
            return {"error": "SKU cannot be empty."}

        if sku in seen_skus:
            return {"error": f"Duplicate SKU in order items: '{sku}'."}
        seen_skus.add(sku)

        try:
            qty = int(it["quantity"])
        except (ValueError, TypeError):
            return {"error": f"Quantity for SKU '{sku}' must be an integer."}

        if qty < 1:
            return {"error": f"Quantity for SKU '{sku}' must be a positive integer (>= 1)."}

        normalized_items.append({"sku": sku, "quantity": qty})

    try:
        with transaction.atomic():
            line_results, subtotal, tax_total, grand_total = _calculate_lines(normalized_items)
            order_number = _generate_order_number()

            order = Order.objects.create(
                dealer=dealer,
                order_number=order_number,
                status="DRAFT",
                subtotal=subtotal,
                tax_total=tax_total,
                grand_total=grand_total,
            )

            for line in line_results:
                OrderItem.objects.create(
                    order=order,
                    product=line["product"],
                    quantity=line["quantity"],
                    unit_price=line["unit_price"],
                    line_subtotal=line["line_subtotal"],
                    line_tax=line["line_tax"],
                    line_total=line["line_total"],
                )

            # Record side effect in actions accumulator if supplied
            if actions_accumulator is not None:
                actions_accumulator.append({
                    "type": "draft_order_created",
                    "order_number": order.order_number,
                })

            return {
                "success": True,
                "order_number": order.order_number,
                "status": "DRAFT",
                "dealer_id": dealer.id,
                "dealer_name": dealer.name,
                "subtotal": f"{subtotal:.2f}",
                "tax_total": f"{tax_total:.2f}",
                "grand_total": f"{grand_total:.2f}",
                "items": [
                    {
                        "sku": line["product"].sku,
                        "name": line["product"].name,
                        "quantity": line["quantity"],
                        "unit_price": f"{line['unit_price']:.2f}",
                        "line_total": f"{line['line_total']:.2f}",
                    }
                    for line in line_results
                ],
            }

    except Exception as e:
        return {"error": str(e)}


# Schema definitions for LLM Function Calling (OpenAI / Groq format)
TOOLS_SCHEMA_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "search_parts",
            "description": "Search the product catalogue for vehicle parts by name, category, brand, SKU, or vehicle fitment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Part name or search terms (e.g. 'brake pads', 'oil filter', 'clutch cable')",
                    },
                    "vehicle": {
                        "type": "string",
                        "description": "Vehicle model if specified (e.g. 'Bajaj Pulsar 150', 'Honda Activa')",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_stock",
            "description": "Check real-time stock availability and details for a specific part SKU in the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "The exact product SKU (e.g. 'BRK-1044', 'FIL-1012')",
                    },
                },
                "required": ["sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft_order",
            "description": "Create a DRAFT order for the dealer when products and quantities are explicitly identified. Only creates DRAFT orders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dealer_id": {
                        "type": "integer",
                        "description": "The ID of the dealer creating the order",
                    },
                    "items": {
                        "type": "array",
                        "description": "List of items to order with SKU and positive quantity",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string", "description": "The product SKU"},
                                "quantity": {"type": "integer", "description": "Quantity to order (positive integer)"},
                            },
                            "required": ["sku", "quantity"],
                        },
                    },
                },
                "required": ["dealer_id", "items"],
            },
        },
    },
]
