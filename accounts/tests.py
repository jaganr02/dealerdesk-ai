from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import SupplierProfile

User = get_user_model()


class AuthenticationAndRBACркаTests(APITestCase):
    """
    Comprehensive tests for DealerDesk authentication and role-based access control.
    """

    def setUp(self):
        self.register_url = reverse("auth-register")
        self.login_url = reverse("auth-login")
        self.me_url = reverse("auth-me")
        self.dealer_test_url = reverse("dealer-test")
        self.supplier_test_url = reverse("supplier-test")

        # Create sample dealer user
        self.dealer_user = User.objects.create_user(
            username="testdealer",
            email="dealer@dealerdesk.com",
            password="DealerSecurePass2026!",
            role=User.Role.DEALER,
        )

        # Create sample supplier user
        self.supplier_user = User.objects.create_user(
            username="testsupplier",
            email="supplier@dealerdesk.com",
            password="SupplierSecurePass2026!",
            role=User.Role.SUPPLIER,
        )
        SupplierProfile.objects.create(
            user=self.supplier_user,
            company_name="Apex Auto Parts Ltd",
            supplier_code="SUP-0001",
        )

    def test_successful_dealer_registration(self):
        payload = {
            "username": "newdealer",
            "email": "newdealer@example.com",
            "password": "SecurePassword123!",
            "role": "DEALER",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["username"], "newdealer")
        self.assertEqual(response.data["user"]["role"], "DEALER")
        self.assertIn("tokens", response.data)
        self.assertIn("access", response.data["tokens"])
        self.assertNotIn("password", response.data["user"])

        # Verify database persistence
        user = User.objects.get(username="newdealer")
        self.assertEqual(user.role, User.Role.DEALER)
        self.assertTrue(user.check_password("SecurePassword123!"))

    def test_successful_supplier_registration(self):
        payload = {
            "username": "newsupplier",
            "email": "newsupplier@example.com",
            "password": "SecurePassword123!",
            "role": "SUPPLIER",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["role"], "SUPPLIER")

        user = User.objects.get(username="newsupplier")
        self.assertEqual(user.role, User.Role.SUPPLIER)
        self.assertTrue(hasattr(user, "supplier_profile"))

    def test_duplicate_username_rejection(self):
        payload = {
            "username": "testdealer",  # already exists
            "email": "different@example.com",
            "password": "SecurePassword123!",
            "role": "DEALER",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_duplicate_email_rejection(self):
        payload = {
            "username": "uniquename",
            "email": "dealer@dealerdesk.com",  # already exists
            "password": "SecurePassword123!",
            "role": "DEALER",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_invalid_role_rejection(self):
        payload = {
            "username": "hackeruser",
            "email": "hacker@example.com",
            "password": "SecurePassword123!",
            "role": "SUPERADMIN",  # invalid role
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_password_hashing(self):
        raw_password = "SecurePassword123!"
        payload = {
            "username": "hashtestuser",
            "email": "hash@example.com",
            "password": raw_password,
            "role": "DEALER",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username="hashtestuser")
        self.assertNotEqual(user.password, raw_password)
        self.assertTrue(user.password.startswith("pbkdf2_") or user.password.startswith("argon2"))
        self.assertTrue(user.check_password(raw_password))

    def test_weak_password_rejection(self):
        payload = {
            "username": "weakuser",
            "email": "weak@example.com",
            "password": "123",  # too short / common
            "role": "DEALER",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_successful_login_with_valid_credentials(self):
        payload = {
            "username": "testdealer",
            "password": "DealerSecurePass2026!",
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("tokens", response.data)
        self.assertIn("access", response.data["tokens"])
        self.assertIn("refresh", response.data["tokens"])
        self.assertEqual(response.data["user"]["role"], "DEALER")
        self.assertNotIn("password", response.data["user"])

    def test_login_failure_with_invalid_credentials(self):
        payload = {
            "username": "testdealer",
            "password": "WrongPassword!",
        }
        response = self.client.post(self.login_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", response.data)

    def test_access_token_authentication_current_user(self):
        refresh = RefreshToken.for_user(self.dealer_user)
        access_token = str(refresh.access_token)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "testdealer")
        self.assertEqual(response.data["email"], "dealer@dealerdesk.com")
        self.assertEqual(response.data["role"], "DEALER")
        self.assertNotIn("password", response.data)

    def test_rejection_of_unauthenticated_protected_requests(self):
        # No credentials provided
        self.client.credentials()
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(self.dealer_test_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get(self.supplier_test_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dealer_access_to_dealer_endpoint(self):
        refresh = RefreshToken.for_user(self.dealer_user)
        access_token = str(refresh.access_token)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get(self.dealer_test_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], "DEALER")

    def test_supplier_access_to_supplier_endpoint(self):
        refresh = RefreshToken.for_user(self.supplier_user)
        access_token = str(refresh.access_token)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get(self.supplier_test_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], "SUPPLIER")

    def test_cross_role_access_rejection(self):
        # 1. Dealer trying to access Supplier endpoint
        dealer_token = str(RefreshToken.for_user(self.dealer_user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {dealer_token}")
        response = self.client.get(self.supplier_test_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Supplier trying to access Dealer endpoint
        supplier_token = str(RefreshToken.for_user(self.supplier_user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {supplier_token}")
        response = self.client.get(self.dealer_test_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_openapi_schema_generation(self):
        self.client.credentials()
        response = self.client.get(reverse("schema"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_swagger_ui_endpoint(self):
        self.client.credentials()
        response = self.client.get(reverse("swagger-ui"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_redoc_ui_endpoint(self):
        self.client.credentials()
        response = self.client.get(reverse("redoc"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

