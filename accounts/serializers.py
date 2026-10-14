from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import SupplierProfile, User


class UserSafeSerializer(serializers.ModelSerializer):
    """
    Serializer providing safe user information without exposing password hashes.
    Includes linked dealer profile details when applicable.
    """
    dealer_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "date_joined", "dealer_profile")
        read_only_fields = ("id", "username", "email", "role", "date_joined", "dealer_profile")

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_dealer_profile(self, obj):
        if obj.role == User.Role.DEALER and hasattr(obj, "dealer_profile") and obj.dealer_profile:
            d = obj.dealer_profile
            return {
                "id": d.id,
                "dealer_code": d.dealer_code,
                "business_name": d.business_name,
                "contact_person": d.contact_person,
                "phone": d.phone,
                "email": d.email,
                "gstin": d.gstin,
                "city": d.city,
                "state": d.state,
                "address": d.address,
                "pincode": d.pincode,
                "credit_limit": str(d.credit_limit),
                "outstanding_balance": str(d.outstanding_balance),
            }
        return None


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Validates and registers new DealerDesk users with DEALER or SUPPLIER role.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"}
    )
    email = serializers.EmailField(
        required=True,
        allow_blank=False
    )
    role = serializers.ChoiceField(
        choices=User.Role.choices,
        required=True
    )

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "role")
        read_only_fields = ("id",)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return normalized

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_role(self, value):
        if value not in (User.Role.DEALER, User.Role.SUPPLIER):
            raise serializers.ValidationError("Role must be either DEALER or SUPPLIER.")
        return value

    def create(self, validated_data):
        from decimal import Decimal
        password = validated_data.pop("password")
        role = validated_data.get("role")

        # Create user with properly hashed password
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=password,
            role=role,
            is_staff=False,
            is_superuser=False,
        )

        # Create corresponding profile if dealer
        if role == User.Role.DEALER:
            from inventory.models import Dealer
            Dealer.objects.create(
                user=user,
                dealer_code=f"DLR-KA-{user.id:04d}",
                business_name=f"{user.username.replace('_', ' ').title()} Dealership",
                contact_person=user.username,
                email=user.email,
                phone="9876543210",
                city="Bengaluru",
                state="Karnataka",
                address="Peenya Industrial Area, Phase II",
                pincode="560058",
                credit_limit=Decimal("500000.00"),
                outstanding_balance=Decimal("0.00"),
                is_active=True,
            )
        # Create corresponding profile if supplier
        elif role == User.Role.SUPPLIER:
            SupplierProfile.objects.create(
                user=user,
                company_name=f"{user.username.replace('_', ' ').title()} Auto Components",
                supplier_code=f"SUP-{user.id:04d}"
            )

        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Authenticates user using credentials (username and password only).
    Does NOT require or accept role from client request.
    """
    username = serializers.CharField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"}
    )

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")

        user = authenticate(username=username, password=password)
        if not user:
            raise serializers.ValidationError(
                {"detail": "Invalid username or password."}
            )

        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "This account is inactive. Please contact distributor support."}
            )

        # Generate tokens
        refresh = RefreshToken.for_user(user)

        # Custom claims on token
        refresh["role"] = user.role
        refresh["username"] = user.username

        return {
            "user": user,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
