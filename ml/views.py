"""
API Views for Demand Forecasting and Reorder Suggestions (§10).
"""

from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ml.serializers import (
    ForecastResponseSerializer,
    ReorderSuggestionsResponseSerializer,
)
from ml.services import (
    compute_reorder_suggestions,
    get_forecast_for_sku,
)


class ForecastDetailView(APIView):
    """
    GET /api/forecast/{sku}/
    Returns 4-week demand forecast for a valid forecast SKU.
    Returns 404 for unknown or non-forecast SKUs.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Get SKU demand forecast",
        description="Returns 4-week forecasted demand units for a specified forecast SKU.",
        responses={
            200: ForecastResponseSerializer,
            404: OpenApiResponse(description="Unknown SKU or not a forecast SKU"),
        },
        tags=["Forecasting & ML"],
    )
    def get(self, request, sku: str):
        data = get_forecast_for_sku(sku)
        return Response(data, status=status.HTTP_200_OK)


class ReorderSuggestionsView(APIView):
    """
    GET /api/reorder-suggestions/
    Returns reorder suggestions for all 40 forecast SKUs based on live stock,
    lead times, forecasted demand, and demand volatility (sigma).
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Get reorder suggestions",
        description="Returns safety stock, reorder point, and suggested reorder quantities for all 40 forecast SKUs.",
        responses={
            200: ReorderSuggestionsResponseSerializer,
        },
        tags=["Forecasting & ML"],
    )
    def get(self, request):
        results = compute_reorder_suggestions()
        return Response({"results": results}, status=status.HTTP_200_OK)
