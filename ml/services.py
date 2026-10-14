"""
ML Demand Forecasting and Reorder Suggestions Service.
Reconciled with VIKMO DealerDesk API_CONTRACT.md section 10.
"""

import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from django.conf import settings

from dealerdesk.exceptions import NotFoundException
from inventory.models import Inventory

BASE_DIR = Path(settings.BASE_DIR)
DATA_DIR = BASE_DIR / "data"
ML_DIR = BASE_DIR / "ml"
FORECAST_CSV = ML_DIR / "forecast.csv"
LEAD_TIMES_CSV = DATA_DIR / "lead_times.csv"
SALES_HISTORY_CSV = DATA_DIR / "sales_history.csv"

# In-memory cache for historical sigmas and lead times to ensure fast responses
_SIGMA_CACHE: Optional[Dict[str, float]] = None
_LEAD_TIMES_CACHE: Optional[List[Dict[str, Any]]] = None


def load_forecast_map() -> Dict[str, List[Dict[str, Any]]]:
    """
    Loads ml/forecast.csv and groups forecast records by SKU.
    Returns:
        Dict[str, List[Dict[str, Any]]]: {sku: [{"week_start": ..., "forecast_units": ...}, ...]}
    """
    if not FORECAST_CSV.exists():
        raise NotFoundException(message="ml/forecast.csv not found")

    forecast_map: Dict[str, List[Dict[str, Any]]] = {}
    with open(FORECAST_CSV, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sku = row["sku"].strip()
            week_start = row["week_start"].strip()
            forecast_units = float(row["forecast_units"])
            if sku not in forecast_map:
                forecast_map[sku] = []
            forecast_map[sku].append({
                "week_start": week_start,
                "forecast_units": forecast_units
            })

    # Sort each SKU's forecast by week_start ascending
    for sku in forecast_map:
        forecast_map[sku].sort(key=lambda x: x["week_start"])

    return forecast_map


def load_lead_times() -> List[Dict[str, Any]]:
    """
    Loads data/lead_times.csv to obtain the 40 forecast SKUs and their lead times.
    """
    global _LEAD_TIMES_CACHE
    if _LEAD_TIMES_CACHE is not None:
        return _LEAD_TIMES_CACHE

    if not LEAD_TIMES_CSV.exists():
        raise NotFoundException(message="data/lead_times.csv not found")

    lead_times = []
    with open(LEAD_TIMES_CSV, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lead_times.append({
                "sku": row["sku"].strip(),
                "lead_time_weeks": int(row["lead_time_weeks"].strip())
            })

    _LEAD_TIMES_CACHE = lead_times
    return _LEAD_TIMES_CACHE


def get_sales_sigmas() -> Dict[str, float]:
    """
    Calculates sample standard deviation (ddof=1) of units_sold over the most recent 12 weeks
    of sales_history.csv for each SKU (all available weeks if fewer than 12).
    """
    global _SIGMA_CACHE
    if _SIGMA_CACHE is not None:
        return _SIGMA_CACHE

    if not SALES_HISTORY_CSV.exists():
        return {}

    df_sales = pd.read_csv(SALES_HISTORY_CSV)
    sigmas: Dict[str, float] = {}

    for sku, grp in df_sales.groupby("sku"):
        sub = grp.sort_values("week_start").tail(12)
        units = sub["units_sold"]
        if len(units) > 1:
            sigmas[sku] = float(units.std(ddof=1))
        else:
            sigmas[sku] = 0.0

    _SIGMA_CACHE = sigmas
    return _SIGMA_CACHE


def get_forecast_for_sku(sku: str) -> Dict[str, Any]:
    """
    Retrieves the 4 forecast weeks for the given SKU.
    Raises NotFoundException if the SKU is unknown or not a forecast SKU.
    """
    forecast_map = load_forecast_map()
    clean_sku = sku.strip()
    if clean_sku not in forecast_map:
        raise NotFoundException(message=f"Forecast not found for SKU: {clean_sku}")

    return {
        "sku": clean_sku,
        "forecast": forecast_map[clean_sku]
    }


def compute_reorder_suggestions() -> List[Dict[str, Any]]:
    """
    Computes reorder suggestions for all 40 forecast SKUs according to API_CONTRACT.md section 10.2:
    - L = lead_time_weeks from data/lead_times.csv
    - lead_time_demand = sum of forecast_units for the first L forecast weeks
    - sigma = sample standard deviation (n - 1) of units_sold over the most recent 12 weeks of sales_history.csv
    - safety_stock = ceil(1.65 * sigma * sqrt(L))
    - reorder_point = lead_time_demand + safety_stock
    - reorder_qty = max(0, ceil(reorder_point - current_stock))
    - current_stock is the live available stock at the time of the request
    """
    lead_times = load_lead_times()
    forecast_map = load_forecast_map()
    sigmas = get_sales_sigmas()

    # Pre-fetch live inventory for all 40 SKUs in a single query
    skus = [lt["sku"] for lt in lead_times]
    inv_map = {
        inv.product.sku: inv.quantity
        for inv in Inventory.objects.filter(product__sku__in=skus).select_related("product")
    }

    suggestions = []
    for lt in lead_times:
        sku = lt["sku"]
        L = lt["lead_time_weeks"]

        # Live current stock
        current_stock = int(inv_map.get(sku, 0))

        # First L weeks of forecast
        sku_forecast = forecast_map.get(sku, [])
        first_l_weeks = sku_forecast[:L]
        lead_time_demand = round(sum(item["forecast_units"] for item in first_l_weeks), 2)

        # Sigma
        sigma = sigmas.get(sku, 0.0)

        # Safety stock: ceil(1.65 * sigma * sqrt(L))
        safety_stock = int(math.ceil(1.65 * sigma * math.sqrt(L)))

        # Reorder point: lead_time_demand + safety_stock
        reorder_point = round(lead_time_demand + safety_stock, 2)

        # Reorder quantity: max(0, ceil(reorder_point - current_stock))
        reorder_qty = max(0, int(math.ceil(reorder_point - current_stock)))

        suggestions.append({
            "sku": sku,
            "current_stock": current_stock,
            "lead_time_weeks": L,
            "lead_time_demand": lead_time_demand,
            "safety_stock": safety_stock,
            "reorder_point": reorder_point,
            "reorder_qty": reorder_qty
        })

    return suggestions
