"""
Serializers for Dealer Assistant API (§9).
"""

from rest_framework import serializers


class AssistantChatRequestSerializer(serializers.Serializer):
    session_id = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={"blank": "session_id cannot be blank.", "required": "session_id is required."},
    )
    dealer_id = serializers.IntegerField(
        required=True,
        error_messages={"required": "dealer_id is required.", "invalid": "dealer_id must be an integer."},
    )
    message = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={"blank": "message cannot be blank.", "required": "message is required."},
    )


class AssistantChatResponseSerializer(serializers.Serializer):
    reply = serializers.CharField()
    cited_skus = serializers.ListField(child=serializers.CharField())
    tool_calls = serializers.ListField(child=serializers.DictField())
    actions = serializers.ListField(child=serializers.DictField())
