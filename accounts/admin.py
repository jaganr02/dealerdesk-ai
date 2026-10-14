from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import SupplierProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "id",
        "username",
        "email",
        "role",
        "is_active",
        "is_staff",
        "date_joined",
    )
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "email")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("DealerDesk Role", {"fields": ("role",)}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("DealerDesk Role", {"fields": ("role",)}),
    )


@admin.register(SupplierProfile)
class SupplierProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "company_name",
        "supplier_code",
        "contact_person",
        "phone",
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "company_name",
        "supplier_code",
    )
