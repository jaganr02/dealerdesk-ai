from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from inventory.models import Dealer, Inventory, Order, OrderItem, Product

User = get_user_model()


class DealerModelAndPortalTests(TestCase):
    """
    Tests for Dealer profile model relationships, role enforcement,
    and Dealer Portal UI views.
    """

    def setUp(self):
        self.dealer_user = User.objects.create_user(
            username="dealer_user_1",
            email="dealer1@example.com",
            password="SecurePass123!",
            role=User.Role.DEALER,
        )
        self.supplier_user = User.objects.create_user(
            username="supplier_user_1",
            email="supplier1@example.com",
            password="SecurePass123!",
            role=User.Role.SUPPLIER,
        )

    def test_create_valid_dealer_profile(self):
        dealer = Dealer.objects.create(
            user=self.dealer_user,
            dealer_code="DLR-KA-0099",
            business_name="Karnataka Spares Hub",
            contact_person="Sunil Gowda",
            email="sunil@karnatakaspares.in",
            phone="9876543211",
            city="Bengaluru",
            state="Karnataka",
            address="Peenya Industrial Area",
            pincode="560058",
            credit_limit=Decimal("500000.00"),
        )
        dealer.full_clean()  # should not raise
        self.assertEqual(dealer.user, self.dealer_user)
        self.assertEqual(dealer.name, "Karnataka Spares Hub")
        self.assertEqual(self.dealer_user.dealer_profile, dealer)

    def test_create_standalone_dealer_without_user(self):
        """API_CONTRACT.md specifies dealers do not require authentication or linked users."""
        dealer = Dealer.objects.create(
            dealer_code="DLR-001",
            name="ABC Motors",
            city="Kochi",
            phone="9310247930",
            email="orders@abcmotors.in",
            gstin="27AABP5506A1Z6",
            credit_limit=Decimal("50000.00"),
        )
        dealer.full_clean()
        self.assertIsNone(dealer.user)
        self.assertEqual(dealer.name, "ABC Motors")
        self.assertEqual(dealer.business_name, "ABC Motors")
        self.assertEqual(dealer.credit_limit, Decimal("50000.00"))

    def test_reject_supplier_user_on_dealer_profile(self):
        dealer = Dealer(
            user=self.supplier_user,
            dealer_code="DLR-KA-9999",
            business_name="Invalid Supplier Dealer",
            email="invalid@example.com",
            phone="9876543210",
            city="Bengaluru",
            state="Karnataka",
        )
        with self.assertRaises(ValidationError):
            dealer.full_clean()

    def test_dealer_code_unique_constraint(self):
        Dealer.objects.create(
            dealer_code="DLR-001",
            name="First Dealership",
        )
        with self.assertRaises(IntegrityError):
            Dealer.objects.create(
                dealer_code="DLR-001",
                name="Second Dealership With Same Code",
            )

    def test_dealer_portal_views_render_successfully(self):
        response_root = self.client.get(reverse("dealer-portal"))
        self.assertEqual(response_root.status_code, 200)
        self.assertTemplateUsed(response_root, "dealer/index.html")
        self.assertContains(response_root, "DealerDesk")
        self.assertContains(response_root, "Automotive Spare Parts Catalogue")

        response_alias = self.client.get(reverse("dealer-portal-alias"))
        self.assertEqual(response_alias.status_code, 200)
        self.assertTemplateUsed(response_alias, "dealer/index.html")


class ProductAndInventoryModelTests(TestCase):
    """
    Tests for Product catalogue, brand, vehicle fitment, pricing,
    and 1:1 warehouse inventory relationships.
    """

    def test_create_product_with_all_contract_fields(self):
        product = Product.objects.create(
            sku="BRK-1044",
            name="Brake Pad Set - Bajaj Pulsar 150",
            category="Brakes",
            brand="Endurance",
            vehicle_fitment="Bajaj Pulsar 150",
            price=Decimal("1459.50"),
            description="Endurance brake pad set for Bajaj Pulsar 150.",
        )
        product.full_clean()
        self.assertEqual(product.brand, "Endurance")
        self.assertEqual(product.vehicle_fitment, "Bajaj Pulsar 150")
        self.assertEqual(product.price, Decimal("1459.50"))
        # Inventory not created yet -> stock property returns 0
        self.assertEqual(product.stock, 0)

    def test_product_unique_sku_constraint(self):
        Product.objects.create(
            sku="BRK-1044",
            name="Brake Pad Set",
            price=Decimal("1459.50"),
        )
        with self.assertRaises(IntegrityError):
            Product.objects.create(
                sku="BRK-1044",
                name="Duplicate Brake Pad Set",
                price=Decimal("1200.00"),
            )

    def test_product_stock_via_inventory_relationship(self):
        product = Product.objects.create(
            sku="FIL-1012",
            name="Oil Filter - Yamaha FZ",
            category="Filters",
            brand="Bosch",
            vehicle_fitment="Yamaha FZ",
            price=Decimal("250.00"),
        )
        inventory = Inventory.objects.create(
            product=product,
            quantity=85,
            reserved_quantity=10,
        )
        inventory.full_clean()
        self.assertEqual(product.stock, 85)
        self.assertEqual(inventory.available_for_order, 75)

    def test_inventory_non_negative_constraint(self):
        product = Product.objects.create(
            sku="CHN-1001",
            name="Drive Chain",
            price=Decimal("950.00"),
        )
        inventory = Inventory(
            product=product,
            quantity=-5,
        )
        with self.assertRaises(ValidationError):
            inventory.full_clean()


class OrderAndOrderItemModelTests(TestCase):
    """
    Tests for Order lifecycle, calculations, monetary snapshots,
    and line item referential integrity.
    """

    def setUp(self):
        self.dealer = Dealer.objects.create(
            dealer_code="DLR-007",
            name="Wheels & Deals",
            city="Hyderabad",
            credit_limit=Decimal("250000.00"),
        )
        self.product1 = Product.objects.create(
            sku="BRK-1044",
            name="Brake Pad Set",
            price=Decimal("1459.50"),
        )
        self.product2 = Product.objects.create(
            sku="FIL-1012",
            name="Oil Filter",
            price=Decimal("250.00"),
        )

    def test_create_draft_order_with_items_and_snapshots(self):
        # 3 units of product1 (1459.50 ea): subtotal = 4378.50, tax = 788.13, total = 5166.63
        order = Order.objects.create(
            order_number="ORD-20261012-0007",
            dealer=self.dealer,
            status=Order.Status.DRAFT,
            subtotal=Decimal("4378.50"),
            tax_total=Decimal("788.13"),
            grand_total=Decimal("5166.63"),
        )
        order.full_clean()

        item = OrderItem.objects.create(
            order=order,
            product=self.product1,
            quantity=3,
            unit_price=Decimal("1459.50"),
            line_subtotal=Decimal("4378.50"),
            line_tax=Decimal("788.13"),
            line_total=Decimal("5166.63"),
        )
        item.full_clean()

        # Check order items relationship
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(item.sku, "BRK-1044")
        self.assertEqual(item.name, "Brake Pad Set")
        self.assertEqual(item.line_subtotal, Decimal("4378.50"))
        self.assertEqual(item.line_tax, Decimal("788.13"))
        self.assertEqual(item.line_total, Decimal("5166.63"))

        # Verify historical price snapshot remains intact if product price changes
        self.product1.price = Decimal("1800.00")
        self.product1.save()

        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal("1459.50"))  # snapshot preserved

    def test_unique_product_per_order_constraint(self):
        order = Order.objects.create(
            order_number="ORD-20261012-0008",
            dealer=self.dealer,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            quantity=2,
            unit_price=Decimal("1459.50"),
        )
        # Attempting to add same product twice to same order violates constraint
        with self.assertRaises(IntegrityError):
            OrderItem.objects.create(
                order=order,
                product=self.product1,
                quantity=1,
                unit_price=Decimal("1459.50"),
            )

    def test_product_deletion_protected_when_ordered(self):
        order = Order.objects.create(
            order_number="ORD-20261012-0009",
            dealer=self.dealer,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            quantity=1,
            unit_price=Decimal("1459.50"),
        )
        # Deleting product that has historical orders must be prevented
        with self.assertRaises(IntegrityError):
            self.product1.delete()


class SeedDataCommandTests(TestCase):
    """
    Tests for `python manage.py seed_data` management command.
    Covers CSV parsing, idempotency, updating existing records,
    optional field handling, and error handling.
    """

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_csv(self, filename: str, content: str) -> str:
        from pathlib import Path
        path = Path(self.temp_dir.name) / filename
        path.write_text(content, encoding="utf-8")
        return str(path)

    def test_successful_seeding_and_idempotency(self):
        from io import StringIO
        from django.core.management import call_command

        catalogue_csv = self._write_csv(
            "test_catalogue.csv",
            "sku,name,category,brand,vehicle_fitment,price,stock,description\n"
            "TEST-001,Test Brake Pad,Brakes,Endurance,Bajaj Pulsar,1200.00,50,High quality pad.\n"
            "TEST-002,Test Spark Plug,Electrical,NGK,Royal Enfield,350.00,100,Iridium plug.\n"
        )
        dealers_csv = self._write_csv(
            "test_dealers.csv",
            "dealer_code,name,city,phone,email,gstin,credit_limit\n"
            "DLR-T01,Alpha Motors,Bengaluru,9876543210,alpha@test.in,29AABPA1111A1Z1,200000.00\n"
            "DLR-T02,Beta Spares,Chennai,9876543211,beta@test.in,33AABPB2222B1Z2,150000.00\n"
        )

        out = StringIO()
        # First execution
        call_command("seed_data", catalogue=catalogue_csv, dealers=dealers_csv, stdout=out)
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(Inventory.objects.count(), 2)
        self.assertEqual(Dealer.objects.count(), 2)

        p1 = Product.objects.get(sku="TEST-001")
        self.assertEqual(p1.stock, 50)
        self.assertEqual(p1.price, Decimal("1200.00"))

        d1 = Dealer.objects.get(dealer_code="DLR-T01")
        self.assertEqual(d1.name, "Alpha Motors")
        self.assertEqual(d1.credit_limit, Decimal("200000.00"))

        # Second execution (Idempotency verification)
        call_command("seed_data", catalogue=catalogue_csv, dealers=dealers_csv, stdout=out)
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(Inventory.objects.count(), 2)
        self.assertEqual(Dealer.objects.count(), 2)

    def test_updating_existing_records_when_source_changes(self):
        from io import StringIO
        from django.core.management import call_command

        catalogue_v1 = self._write_csv(
            "cat_v1.csv",
            "sku,name,category,brand,vehicle_fitment,price,stock,description\n"
            "TEST-001,Test Part,Brakes,Endurance,Pulsar,1200.00,50,Original\n"
        )
        dealers_v1 = self._write_csv(
            "dlr_v1.csv",
            "dealer_code,name,city,phone,email,gstin,credit_limit\n"
            "DLR-T01,Alpha Motors,Bengaluru,9876543210,alpha@test.in,,100000.00\n"
        )
        call_command("seed_data", catalogue=catalogue_v1, dealers=dealers_v1, stdout=StringIO())

        # Update CSV with new price, stock, and credit limit
        catalogue_v2 = self._write_csv(
            "cat_v2.csv",
            "sku,name,category,brand,vehicle_fitment,price,stock,description\n"
            "TEST-001,Test Part Updated,Brakes,Endurance,Pulsar,1350.00,75,Updated\n"
        )
        dealers_v2 = self._write_csv(
            "dlr_v2.csv",
            "dealer_code,name,city,phone,email,gstin,credit_limit\n"
            "DLR-T01,Alpha Motors New,Bengaluru,9876543210,alpha@test.in,,250000.00\n"
        )
        call_command("seed_data", catalogue=catalogue_v2, dealers=dealers_v2, stdout=StringIO())

        # Still 1 record each, but values updated
        self.assertEqual(Product.objects.count(), 1)
        p = Product.objects.get(sku="TEST-001")
        self.assertEqual(p.name, "Test Part Updated")
        self.assertEqual(p.price, Decimal("1350.00"))
        self.assertEqual(p.stock, 75)

        d = Dealer.objects.get(dealer_code="DLR-T01")
        self.assertEqual(d.name, "Alpha Motors New")
        self.assertEqual(d.credit_limit, Decimal("250000.00"))

    def test_handling_blank_optional_fields(self):
        from io import StringIO
        from django.core.management import call_command

        catalogue_csv = self._write_csv(
            "cat_blank.csv",
            "sku,name,category,brand,vehicle_fitment,price,stock,description\n"
            "TEST-BLANK,Blank Optional Part,,,,500.00,10,\n"
        )
        dealers_csv = self._write_csv(
            "dlr_blank.csv",
            "dealer_code,name,city,phone,email,gstin,credit_limit\n"
            "DLR-BLANK,Blank Optional Dealer,,,,,\n"
        )
        call_command("seed_data", catalogue=catalogue_csv, dealers=dealers_csv, stdout=StringIO())

        p = Product.objects.get(sku="TEST-BLANK")
        self.assertEqual(p.brand, "")
        self.assertEqual(p.category, "")
        self.assertEqual(p.description, "")

        d = Dealer.objects.get(dealer_code="DLR-BLANK")
        self.assertIsNone(d.gstin)
        self.assertEqual(d.email, "")
        self.assertEqual(d.credit_limit, Decimal("0.00"))

    def test_missing_file_raises_command_error(self):
        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command("seed_data", catalogue="nonexistent_catalogue.csv", dealers="nonexistent_dealers.csv")

    def test_missing_required_column_raises_command_error(self):
        from django.core.management import CommandError, call_command

        bad_catalogue = self._write_csv("bad_cat.csv", "name,price,stock\nPart,100,5\n")
        dealers_csv = self._write_csv("good_dlr.csv", "dealer_code,name\nD-1,Name\n")

        with self.assertRaises(CommandError):
            call_command("seed_data", catalogue=bad_catalogue, dealers=dealers_csv)


class CoreApiIntegrationTests(TestCase):
    """
    Tests for Core APIs matching API_CONTRACT.md:
    Products (§4), Inventory (§5), Dealers (§6), and Orders (§7).
    """

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

        # Seed sample product with inventory
        self.product = Product.objects.create(
            sku="BRK-1044",
            name="Brake Pad Set - Bajaj Pulsar 150",
            category="Brakes",
            brand="Endurance",
            vehicle_fitment="Bajaj Pulsar 150",
            price=Decimal("1459.50"),
            description="High performance brake pad",
        )
        self.inventory = Inventory.objects.create(
            product=self.product,
            quantity=136,
        )

        # Seed sample dealer
        self.dealer = Dealer.objects.create(
            dealer_code="DLR-007",
            name="Wheels & Deals",
            city="Hyderabad",
            phone="9214159864",
            email="orders@wheelsdeals.in",
            gstin="29AABH2853G1Z8",
            credit_limit=Decimal("100000.00"),
        )

    # Products tests (§4)
    def test_get_products_list_pagination_and_filters(self):
        res = self.client.get("/api/products/?page_size=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertEqual(data["count"], 1)
        p = data["results"][0]
        self.assertEqual(p["sku"], "BRK-1044")
        self.assertEqual(p["price"], "1459.50")
        self.assertEqual(p["stock"], 136)

        # Filter by search
        res_search = self.client.get("/api/products/?search=Endurance")
        self.assertEqual(res_search.json()["count"], 1)

        # Filter by vehicle
        res_veh = self.client.get("/api/products/?vehicle=Pulsar")
        self.assertEqual(res_veh.json()["count"], 1)

        # Filter by non-matching category
        res_cat = self.client.get("/api/products/?category=Engine")
        self.assertEqual(res_cat.json()["count"], 0)

    def test_create_product_success_and_duplicate(self):
        body = {
            "sku": "IGN-2001",
            "name": "Ignition Coil",
            "category": "Electrical",
            "brand": "Bosch",
            "vehicle_fitment": "Universal",
            "price": "850.00",
            "description": "Ignition coil",
        }
        res = self.client.post("/api/products/", body, format="json")
        self.assertEqual(res.status_code, 201)
        p = res.json()
        self.assertEqual(p["sku"], "IGN-2001")
        self.assertEqual(p["stock"], 0)
        self.assertEqual(p["price"], "850.00")

        # Duplicate SKU -> 409 DUPLICATE
        dup = self.client.post("/api/products/", body, format="json")
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(dup.json()["error"]["code"], "DUPLICATE")

    def test_product_detail_and_404(self):
        res = self.client.get("/api/products/BRK-1044/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["sku"], "BRK-1044")

        res_404 = self.client.get("/api/products/UNKNOWN-0000/")
        self.assertEqual(res_404.status_code, 404)
        self.assertEqual(res_404.json()["error"]["code"], "NOT_FOUND")

    def test_product_patch(self):
        res = self.client.patch("/api/products/BRK-1044/", {"price": "1499.00"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["price"], "1499.00")

    # Inventory tests (§5)
    def test_inventory_update(self):
        res = self.client.put("/api/inventory/BRK-1044/", {"quantity": 50, "reason": "stock check"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"sku": "BRK-1044", "quantity": 50})

        # Product stock reflects immediately
        p_res = self.client.get("/api/products/BRK-1044/")
        self.assertEqual(p_res.json()["stock"], 50)

    def test_inventory_negative_quantity_validation(self):
        res = self.client.put("/api/inventory/BRK-1044/", {"quantity": -10}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "VALIDATION_ERROR")

    # Dealers tests (§6)
    def test_dealers_list_and_create(self):
        res = self.client.get("/api/dealers/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["count"], 1)

        # Create dealer
        d_body = {"dealer_code": "DLR-999", "name": "New City Motors"}
        res_create = self.client.post("/api/dealers/", d_body, format="json")
        self.assertEqual(res_create.status_code, 201)
        self.assertEqual(res_create.json()["dealer_code"], "DLR-999")
        self.assertEqual(res_create.json()["credit_limit"], "0.00")

        # Duplicate dealer_code -> 409
        res_dup = self.client.post("/api/dealers/", d_body, format="json")
        self.assertEqual(res_dup.status_code, 409)
        self.assertEqual(res_dup.json()["error"]["code"], "DUPLICATE")

    def test_dealer_detail_and_404(self):
        res = self.client.get(f"/api/dealers/{self.dealer.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["name"], "Wheels & Deals")

        res_404 = self.client.get("/api/dealers/999999/")
        self.assertEqual(res_404.status_code, 404)
        self.assertEqual(res_404.json()["error"]["code"], "NOT_FOUND")

    # Orders tests (§7)
    def test_create_draft_order_and_calculations(self):
        body = {
            "dealer_id": self.dealer.id,
            "items": [{"sku": "BRK-1044", "quantity": 3}],
        }
        res = self.client.post("/api/orders/", body, format="json")
        self.assertEqual(res.status_code, 201)
        o = res.json()
        self.assertTrue(o["order_number"].startswith("ORD-"))
        self.assertEqual(o["status"], "DRAFT")
        self.assertEqual(o["dealer_id"], self.dealer.id)
        # Unit price = 1459.50, qty = 3: subtotal = 4378.50, tax = 788.13, total = 5166.63
        self.assertEqual(o["subtotal"], "4378.50")
        self.assertEqual(o["tax_total"], "788.13")
        self.assertEqual(o["grand_total"], "5166.63")
        self.assertEqual(len(o["items"]), 1)
        it = o["items"][0]
        self.assertEqual(it["sku"], "BRK-1044")
        self.assertEqual(it["quantity"], 3)
        self.assertEqual(it["unit_price"], "1459.50")
        self.assertEqual(it["line_subtotal"], "4378.50")
        self.assertEqual(it["line_tax"], "788.13")
        self.assertEqual(it["line_total"], "5166.63")

    def test_order_validation_errors(self):
        # Empty items
        r1 = self.client.post("/api/orders/", {"dealer_id": self.dealer.id, "items": []}, format="json")
        self.assertEqual(r1.status_code, 400)
        self.assertEqual(r1.json()["error"]["code"], "VALIDATION_ERROR")

        # Unknown dealer
        r2 = self.client.post("/api/orders/", {"dealer_id": 9999, "items": [{"sku": "BRK-1044", "quantity": 1}]}, format="json")
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r2.json()["error"]["code"], "VALIDATION_ERROR")

        # Unknown SKU
        r3 = self.client.post("/api/orders/", {"dealer_id": self.dealer.id, "items": [{"sku": "NOPE", "quantity": 1}]}, format="json")
        self.assertEqual(r3.status_code, 400)
        self.assertEqual(r3.json()["error"]["code"], "VALIDATION_ERROR")

        # Duplicate SKU
        r4 = self.client.post(
            "/api/orders/",
            {"dealer_id": self.dealer.id, "items": [{"sku": "BRK-1044", "quantity": 1}, {"sku": "BRK-1044", "quantity": 2}]},
            format="json",
        )
        self.assertEqual(r4.status_code, 400)
        self.assertEqual(r4.json()["error"]["code"], "VALIDATION_ERROR")

    def test_edit_draft_order_and_locked_on_non_draft(self):
        # Create draft order
        res = self.client.post(
            "/api/orders/",
            {"dealer_id": self.dealer.id, "items": [{"sku": "BRK-1044", "quantity": 1}]},
            format="json",
        )
        order_no = res.json()["order_number"]

        # Edit order items (PUT replaces items)
        put_res = self.client.put(
            f"/api/orders/{order_no}/",
            {"items": [{"sku": "BRK-1044", "quantity": 2}]},
            format="json",
        )
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["subtotal"], "2919.00")

        # Confirm order (DRAFT -> CONFIRMED)
        conf_res = self.client.post(f"/api/orders/{order_no}/confirm/")
        self.assertEqual(conf_res.status_code, 200)
        self.assertEqual(conf_res.json()["status"], "CONFIRMED")

        # Attempting PUT on confirmed order -> 409 ORDER_LOCKED
        locked_res = self.client.put(
            f"/api/orders/{order_no}/",
            {"items": [{"sku": "BRK-1044", "quantity": 5}]},
            format="json",
        )
        self.assertEqual(locked_res.status_code, 409)
        self.assertEqual(locked_res.json()["error"]["code"], "ORDER_LOCKED")

    def test_order_idempotency_key(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "test-key-123"}
        body = {
            "dealer_id": self.dealer.id,
            "items": [{"sku": "BRK-1044", "quantity": 1}],
        }
        r1 = self.client.post("/api/orders/", body, format="json", **headers)
        self.assertEqual(r1.status_code, 201)
        order_no1 = r1.json()["order_number"]

        # Same key with same body -> returns original order
        r2 = self.client.post("/api/orders/", body, format="json", **headers)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["order_number"], order_no1)

        # Same key with different body -> 409 IDEMPOTENCY_CONFLICT
        diff_body = {
            "dealer_id": self.dealer.id,
            "items": [{"sku": "BRK-1044", "quantity": 2}],
        }
        r3 = self.client.post("/api/orders/", diff_body, format="json", **headers)
        self.assertEqual(r3.status_code, 409)
        self.assertEqual(r3.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")
