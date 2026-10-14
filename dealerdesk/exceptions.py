"""
Centralized exception handling for DealerDesk API.
Enforces the exact contract error shape:
{"error": {"code": "...", "message": "...", "details": []}}
"""

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler


class ContractAPIException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "VALIDATION_ERROR"
    default_detail = "Validation error"

    def __init__(self, message=None, code=None, details=None, status_code=None):
        if status_code is not None:
            self.status_code = status_code
        self.code = code or self.default_code
        self.message = message or str(self.default_detail)
        self.details = details if details is not None else []
        super().__init__(detail=self.message, code=self.code)


class ValidationException(ContractAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "VALIDATION_ERROR"
    default_detail = "Bad or missing input"


class NotFoundException(ContractAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "NOT_FOUND"
    default_detail = "The resource in the URL does not exist"


class DuplicateException(ContractAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "DUPLICATE"
    default_detail = "Resource already exists"


class OrderLockedException(ContractAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "ORDER_LOCKED"
    default_detail = "Editing an order that is not DRAFT"


class InvalidTransitionException(ContractAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "INVALID_TRANSITION"
    default_detail = "Status change not allowed from the current status"


class InsufficientStockException(ContractAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "INSUFFICIENT_STOCK"
    default_detail = "Insufficient stock"


class IdempotencyConflictException(ContractAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "IDEMPOTENCY_CONFLICT"
    default_detail = "Same Idempotency-Key reused with a different request body"


class ServiceUnavailableException(ContractAPIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "SERVICE_UNAVAILABLE"
    default_detail = "Service temporarily unavailable"


def contract_exception_handler(exc, context):
    """
    Standard exception handler converting all API errors to contract shape:
    {"error": {"code": ..., "message": ..., "details": []}}
    """
    if isinstance(exc, Http404):
        return Response(
            {
                "error": {
                    "code": "NOT_FOUND",
                    "message": str(exc) or "The resource was not found.",
                    "details": [],
                }
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, ContractAPIException):
        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
            status=exc.status_code,
        )

    response = exception_handler(exc, context)
    if response is not None:
        code = "VALIDATION_ERROR"
        if response.status_code == 404:
            code = "NOT_FOUND"
        elif response.status_code == 409:
            code = "DUPLICATE"
        elif response.status_code == 400:
            code = "VALIDATION_ERROR"
        elif response.status_code == 502:
            code = "SUPPLIER_UNAVAILABLE"

        details = []
        message = "An error occurred."
        if isinstance(response.data, dict):
            if "detail" in response.data:
                message = str(response.data["detail"])
            else:
                messages = []
                for field, errs in response.data.items():
                    err_msg = ", ".join(
                        str(e) for e in (errs if isinstance(errs, list) else [errs])
                    )
                    messages.append(f"{field}: {err_msg}")
                    details.append({"field": field, "message": err_msg})
                if messages:
                    message = "; ".join(messages)
        elif isinstance(response.data, list):
            message = "; ".join(str(x) for x in response.data)

        response.data = {
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        }
        return response

    return response
