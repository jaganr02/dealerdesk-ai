from rest_framework.permissions import BasePermission
from .models import User


class IsDealer(BasePermission):
    """
    Allows access only to authenticated users registered with the DEALER role.
    """
    message = "Access restricted: this endpoint requires a Dealer account."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.DEALER
        )


class IsSupplier(BasePermission):
    """
    Allows access only to authenticated users registered with the SUPPLIER role.
    """
    message = "Access restricted: this endpoint requires a Supplier account."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.SUPPLIER
        )
