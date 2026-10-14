"""
URL configuration for dealerdesk project.
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from accounts.views import DealerTestView, SupplierTestView
from dealerdesk.views import HealthCheckView
from inventory.views import DealerPortalView

urlpatterns = [
    # Required Health Check endpoint
    path("api/health/", HealthCheckView.as_view(), name="health-check"),

    # Core Inventory / Products / Dealers / Orders APIs
    path("api/", include("inventory.urls")),

    # Dealer Assistant API (§9)
    path("api/", include("assistant.urls")),

    # Demand Forecasting and Reorder Suggestions API (§10)
    path("api/", include("ml.urls")),

    # Dealer Portal UI
    path("", DealerPortalView.as_view(), name="dealer-portal"),
    path("dealer/", DealerPortalView.as_view(), name="dealer-portal-alias"),

    # Django Administration
    path("admin/", admin.site.urls),

    # OpenAPI Schema and Interactive Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Direct short routes for convenience
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema")),

    # Authentication endpoints
    path("api/auth/", include("accounts.urls")),

    # Role-based verification test endpoints
    path("api/dealer/test/", DealerTestView.as_view(), name="dealer-test"),
    path("api/supplier/test/", SupplierTestView.as_view(), name="supplier-test"),
]
