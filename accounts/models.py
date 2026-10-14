from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model for DealerDesk supporting unified authentication
    with role-based access for DEALER and SUPPLIER accounts.
    """
    class Role(models.TextChoices):
        DEALER = "DEALER", "Dealer"
        SUPPLIER = "SUPPLIER", "Supplier"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.DEALER,
        db_index=True,
        help_text="Designated account role for role-based authorization."
    )
    email = models.EmailField(
        unique=True,
        help_text="Unique email address for contact and account verification."
    )

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["id"]

    @property
    def is_dealer(self) -> bool:
        return self.role == self.Role.DEALER

    @property
    def is_supplier(self) -> bool:
        return self.role == self.Role.SUPPLIER

    def __str__(self):
        return f"{self.username} ({self.role})"


class SupplierProfile(models.Model):
    """
    Supplier-specific profile associated with a User having the SUPPLIER role.
    Maintains OEM/supplier contact and catalogue synchronization metadata.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supplier_profile",
        help_text="Associated user account."
    )
    company_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Supplier business or OEM entity name."
    )
    supplier_code = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Distributor-assigned supplier identifier code."
    )
    contact_person = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Primary sales/supply representative."
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Contact phone number."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Creation timestamp."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last modification timestamp."
    )

    class Meta:
        verbose_name = "Supplier Profile"
        verbose_name_plural = "Supplier Profiles"

    def __str__(self):
        return f"{self.company_name or self.user.username} (Supplier)"
