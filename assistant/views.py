"""
API View for Dealer Assistant Chat (§9).
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from dealerdesk.exceptions import ValidationException
from inventory.models import Dealer
from assistant.serializers import (
    AssistantChatRequestSerializer,
    AssistantChatResponseSerializer,
)
from assistant.service import assistant_service


class AssistantChatView(APIView):
    """
    POST /api/assistant/chat/
    Takes session_id, dealer_id, and message.
    Returns reply, cited_skus, tool_calls, and actions.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Dealer Assistant Chat",
        description="Interact with the GenAI-powered Dealer Assistant with database tool calling.",
        request=AssistantChatRequestSerializer,
        responses={200: AssistantChatResponseSerializer},
    )
    def post(self, request):
        serializer = AssistantChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            # Format DRF serializer errors into clean contract message
            first_err = "Validation error"
            for field, errs in serializer.errors.items():
                first_err = f"{field}: {errs[0]}"
                break
            raise ValidationException(first_err)

        session_id = serializer.validated_data["session_id"].strip()
        dealer_id = serializer.validated_data["dealer_id"]
        message = serializer.validated_data["message"].strip()

        if not session_id:
            raise ValidationException("session_id cannot be empty.")
        if not message:
            raise ValidationException("message cannot be empty.")

        dealer = Dealer.objects.filter(id=dealer_id, is_active=True).first()
        if not dealer:
            raise ValidationException(f"Dealer with ID '{dealer_id}' does not exist or is inactive.")

        result = assistant_service.handle_chat(
            session_id=session_id,
            dealer=dealer,
            user_message=message,
        )

        return Response(result, status=status.HTTP_200_OK)
