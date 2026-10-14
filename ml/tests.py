"""
Unit and integration tests for ML Demand Forecasting and Reorder Suggestions (§10).
"""

import csv
import math
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import Inventory, Product
from ml.services import (
    FORECAST_CSV,
    LEAD_TIMES_CSV,
    SALES_HISTORY_CSV,
    get_sales_sigmas,
    load_forecast_map,
    load_lead_times,
)


class ForecastArtifactTestCase(TestCase):
    """
    Validates Task 1: ml/forecast.csv file compliance with assignment requirements.
    """

    def setUp(self):
        self.expected_weeks = ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]

    def test_forecast_file_exists_and_headers(self):
        self.assertTrue(FORECAST_CSV.exists(), "ml/forecast.csv must exist")
        with open(FORECAST_CSV, mode="r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(
                header[:3],
                ["sku", "week_start", "forecast_units"],
                "Headers must be sku,week_start,forecast_units"
            )

    def test_forecast_rows_and_skus_and_values(self):
        with open(FORECAST_CSV, mode="r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        # Exactly 160 rows
        self.assertEqual(len(rows), 160, "ml/forecast.csv must contain exactly 160 rows")

        # 40 distinct SKUs matching lead_times.csv
        lead_skus = {lt["sku"] for lt in load_lead_times()}
        self.assertEqual(len(lead_skus), 40, "lead_times.csv must have 40 SKUs")

        forecast_skus = {r["sku"] for r in rows}
        self.assertEqual(forecast_skus, lead_skus, "Forecast SKUs must match lead_times.csv SKUs")

        # Exactly 4 required week starts per SKU
        for sku in lead_skus:
            sku_rows = [r for r in rows if r["sku"] == sku]
            self.assertEqual(len(sku_rows), 4, f"SKU {sku} must have exactly 4 rows")
            sku_weeks = sorted([r["week_start"] for r in sku_rows])
            self.assertEqual(sku_weeks, self.expected_weeks, f"SKU {sku} must have exact 4 week starts")

        # Non-negative forecast units
        for r in rows:
            units = float(r["forecast_units"])
            self.assertGreaterEqual(units, 0.0, f"Forecast units must be non-negative, got {units}")


class ForecastAPITestCase(TestCase):
    """
    Validates Task 2: GET /api/forecast/{sku}/
    """

    def setUp(self):
        self.client = APIClient()
        self.lead_times = load_lead_times()
        self.sample_sku = self.lead_times[0]["sku"]
        self.expected_weeks = ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]

    def test_valid_sku_forecast(self):
        url = f"/api/forecast/{self.sample_sku}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["sku"], self.sample_sku)
        forecast = data["forecast"]
        self.assertEqual(len(forecast), 4)

        weeks = [entry["week_start"] for entry in forecast]
        self.assertEqual(weeks, self.expected_weeks)

        for entry in forecast:
            self.assertIn("week_start", entry)
            self.assertIn("forecast_units", entry)
            self.assertGreaterEqual(entry["forecast_units"], 0.0)

    def test_unknown_sku_forecast_returns_404(self):
        url = "/api/forecast/NON-EXISTENT-SKU-9999/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "NOT_FOUND")

    def test_non_forecast_catalogue_sku_returns_404(self):
        # Create a product in database that is not in the 40 forecast SKUs
        product = Product.objects.create(
            sku="NON-FC-001",
            name="Non Forecast Part",
            price="500.00",
            category="Accessories",
        )
        url = f"/api/forecast/{product.sku}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        data = response.json()
        self.assertEqual(data["error"]["code"], "NOT_FOUND")


class ReorderSuggestionsAPITestCase(TestCase):
    """
    Validates Task 3: GET /api/reorder-suggestions/
    """

    def setUp(self):
        self.client = APIClient()
        self.lead_times = load_lead_times()

        # Ensure database has products and inventory for the test
        for lt in self.lead_times:
            sku = lt["sku"]
            prod, _ = Product.objects.get_or_create(
                sku=sku,
                defaults={"name": f"Part {sku}", "price": "100.00"}
            )
            Inventory.objects.get_or_create(
                product=prod,
                defaults={"quantity": 50}
            )

    def test_reorder_suggestions_shape_and_count(self):
        response = self.client.get("/api/reorder-suggestions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertIn("results", data)
        results = data["results"]
        self.assertEqual(len(results), 40, "Must return suggestions for all 40 forecast SKUs")

        required_keys = {
            "sku",
            "current_stock",
            "lead_time_weeks",
            "lead_time_demand",
            "safety_stock",
            "reorder_point",
            "reorder_qty",
        }
        for entry in results:
            self.assertEqual(set(entry.keys()), required_keys)
            self.assertIsInstance(entry["sku"], str)
            self.assertIsInstance(entry["current_stock"], int)
            self.assertIsInstance(entry["lead_time_weeks"], int)
            self.assertIsInstance(entry["lead_time_demand"], (int, float))
            self.assertIsInstance(entry["safety_stock"], int)
            self.assertIsInstance(entry["reorder_point"], (int, float))
            self.assertIsInstance(entry["reorder_qty"], int)

    def test_reorder_formulas_accuracy(self):
        response = self.client.get("/api/reorder-suggestions/")
        data = response.json()
        results = {r["sku"]: r for r in data["results"]}

        forecast_map = load_forecast_map()
        sigmas = get_sales_sigmas()

        for lt in self.lead_times:
            sku = lt["sku"]
            entry = results[sku]
            L = lt["lead_time_weeks"]

            # 1. Lead time demand == sum of forecast_units for first L weeks
            expected_ltd = round(sum(f["forecast_units"] for f in forecast_map[sku][:L]), 2)
            self.assertAlmostEqual(entry["lead_time_demand"], expected_ltd, places=2)

            # 2. Safety stock == ceil(1.65 * sigma * sqrt(L))
            sigma = sigmas.get(sku, 0.0)
            expected_ss = int(math.ceil(1.65 * sigma * math.sqrt(L)))
            self.assertEqual(entry["safety_stock"], expected_ss)

            # 3. Reorder point == lead_time_demand + safety_stock
            expected_rp = round(expected_ltd + expected_ss, 2)
            self.assertAlmostEqual(entry["reorder_point"], expected_rp, places=2)

            # 4. Reorder qty == max(0, ceil(reorder_point - current_stock))
            expected_rq = max(0, int(math.ceil(expected_rp - entry["current_stock"])))
            self.assertEqual(entry["reorder_qty"], expected_rq)

    def test_reorder_live_stock_reflects_inventory_change(self):
        target_sku = self.lead_times[0]["sku"]
        prod = Product.objects.get(sku=target_sku)
        inv = Inventory.objects.get(product=prod)

        # Set stock very high -> reorder_qty should become 0
        inv.quantity = 99999
        inv.save()

        response = self.client.get("/api/reorder-suggestions/")
        results = {r["sku"]: r for r in response.json()["results"]}
        self.assertEqual(results[target_sku]["current_stock"], 99999)
        self.assertEqual(results[target_sku]["reorder_qty"], 0)

        # Set stock to 0 -> reorder_qty should equal ceil(reorder_point)
        inv.quantity = 0
        inv.save()

        response2 = self.client.get("/api/reorder-suggestions/")
        results2 = {r["sku"]: r for r in response2.json()["results"]}
        self.assertEqual(results2[target_sku]["current_stock"], 0)
        self.assertEqual(results2[target_sku]["reorder_qty"], int(math.ceil(results2[target_sku]["reorder_point"])))
