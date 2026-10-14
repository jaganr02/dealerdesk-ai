"""
Core views for DealerDesk project.
"""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """
    Contract Health Check endpoint:
    GET /api/health/ -> 200 {"status": "ok"}
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Service Health Check",
        description="Verify service availability and responsiveness.",
        responses={
            200: inline_serializer(
                name="HealthStatusResponse",
                fields={"status": serializers.CharField(default="ok")},
            )
        },
    )
    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)
