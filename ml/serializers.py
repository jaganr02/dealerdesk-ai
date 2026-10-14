"""
Serializers for ML Demand Forecasting and Reorder Suggestions.
"""

from rest_framework import serializers


class ForecastWeekSerializer(serializers.Serializer):
    week_start = serializers.CharField(help_text="Starting date of forecast week (YYYY-MM-DD)")
    forecast_units = serializers.FloatField(help_text="Predicted unit demand (non-negative)")


class ForecastResponseSerializer(serializers.Serializer):
    sku = serializers.CharField(help_text="Product SKU")
    forecast = ForecastWeekSerializer(many=True, help_text="4-week demand predictions")


class ReorderSuggestionItemSerializer(serializers.Serializer):
    sku = serializers.CharField(help_text="Product SKU")
    current_stock = serializers.IntegerField(help_text="Live physical inventory in warehouse")
    lead_time_weeks = serializers.IntegerField(help_text="Supplier lead time in weeks (L)")
    lead_time_demand = serializers.FloatField(help_text="Cumulative forecast demand across lead time")
    safety_stock = serializers.IntegerField(help_text="Buffer stock = ceil(1.65 * sigma * sqrt(L))")
    reorder_point = serializers.FloatField(help_text="Inventory threshold = lead_time_demand + safety_stock")
    reorder_qty = serializers.IntegerField(help_text="Suggested order size = max(0, ceil(reorder_point - current_stock))")


class ReorderSuggestionsResponseSerializer(serializers.Serializer):
    results = ReorderSuggestionItemSerializer(many=True, help_text="Reorder calculations for 40 forecast SKUs")
