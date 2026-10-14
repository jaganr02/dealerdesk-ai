"""
Automated test suite for Dealer Assistant (§9).
Tests cover contract compliance, tool execution, session memory, guardrails,
SKU citation grounding, error shapes, and mock LLM tool calling.
"""

from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import Dealer, Inventory, Order, OrderItem, Product
from assistant.memory import session_memory
from assistant.provider import assistant_client
from assistant.service import extract_cited_skus
from assistant.tools import check_stock, create_draft_order, search_parts
from dealerdesk.exceptions import ServiceUnavailableException


class AssistantUnitToolsTestCase(TestCase):
    """Test tools in isolation: search_parts, check_stock, create_draft_order."""

    def setUp(self):
        self.dealer = Dealer.objects.create(
            dealer_code="DLR-TEST-01",
            name="Test Metro Motors",
            city="Bengaluru",
            state="Karnataka",
        )
        self.p1 = Product.objects.create(
            sku="BRK-1044",
            name="Brake Pad Set - Bajaj Pulsar 150",
            category="Brakes",
            brand="Endurance",
            vehicle_fitment="Bajaj Pulsar 150",
            price=Decimal("1459.50"),
            description="High-friction composite brake pads for Pulsar 150.",
        )
        Inventory.objects.create(product=self.p1, quantity=45)

        self.p2 = Product.objects.create(
            sku="FIL-1012",
            name="Oil Filter - Hero Splendor",
            category="Filters",
            brand="Elofic",
            vehicle_fitment="Hero Splendor Plus",
            price=Decimal("220.00"),
            description="Synthetic blend oil filter cartridge.",
        )
        Inventory.objects.create(product=self.p2, quantity=120)

    def test_search_parts_by_query_and_vehicle(self):
        # Search by keyword
        res = search_parts(query="brake pads")
        self.assertTrue(len(res) >= 1)
        self.assertEqual(res[0]["sku"], "BRK-1044")
        self.assertEqual(res[0]["stock"], 45)
        self.assertEqual(res[0]["price"], "1459.50")

        # Search with vehicle filter
        res_vehicle = search_parts(query="filter", vehicle="Hero Splendor")
        self.assertTrue(len(res_vehicle) >= 1)
        self.assertEqual(res_vehicle[0]["sku"], "FIL-1012")

    def test_search_parts_empty_or_no_match(self):
        self.assertEqual(search_parts(query=""), [])
        self.assertEqual(search_parts(query="   "), [])

    def test_check_stock_live_inventory(self):
        stock_info = check_stock(sku="BRK-1044")
        self.assertEqual(stock_info["sku"], "BRK-1044")
        self.assertEqual(stock_info["stock"], 45)
        self.assertEqual(stock_info["price"], "1459.50")
        self.assertTrue(stock_info["available"])

        # Check stock for non-existent SKU
        err_info = check_stock(sku="NON-EXISTENT")
        self.assertIn("error", err_info)

    def test_create_draft_order_success(self):
        actions = []
        result = create_draft_order(
            dealer_id=self.dealer.id,
            items=[{"sku": "BRK-1044", "quantity": 2}, {"sku": "FIL-1012", "quantity": 3}],
            authorized_dealer_id=self.dealer.id,
            actions_accumulator=actions,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "DRAFT")
        self.assertTrue(result["order_number"].startswith("ORD-"))
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "draft_order_created")
        self.assertEqual(actions[0]["order_number"], result["order_number"])

        # Verify DB order
        db_order = Order.objects.get(order_number=result["order_number"])
        self.assertEqual(db_order.status, "DRAFT")
        self.assertEqual(db_order.dealer, self.dealer)
        self.assertEqual(db_order.items.count(), 2)

    def test_create_draft_order_dealer_isolation(self):
        # If authorized dealer is self.dealer.id, but LLM passed a different ID,
        # authorized_dealer_id is enforced
        actions = []
        result = create_draft_order(
            dealer_id=99999,  # attacker or LLM hallucinated ID
            items=[{"sku": "BRK-1044", "quantity": 1}],
            authorized_dealer_id=self.dealer.id,
            actions_accumulator=actions,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["dealer_id"], self.dealer.id)

    def test_create_draft_order_invalid_inputs(self):
        # Empty items
        res1 = create_draft_order(self.dealer.id, [], authorized_dealer_id=self.dealer.id)
        self.assertIn("error", res1)

        # Negative quantity
        res2 = create_draft_order(
            self.dealer.id,
            [{"sku": "BRK-1044", "quantity": -5}],
            authorized_dealer_id=self.dealer.id,
        )
        self.assertIn("error", res2)

        # Duplicate SKU
        res3 = create_draft_order(
            self.dealer.id,
            [{"sku": "BRK-1044", "quantity": 1}, {"sku": "BRK-1044", "quantity": 2}],
            authorized_dealer_id=self.dealer.id,
        )
        self.assertIn("error", res3)


class AssistantSessionMemoryTestCase(TestCase):
    """Test bounded conversation memory and dealer/session isolation."""

    def setUp(self):
        session_memory.clear()

    def tearDown(self):
        session_memory.clear()

    def test_session_isolation(self):
        session_memory.append_message("sess-1", {"role": "user", "content": "Hello session 1"})
        session_memory.append_message("sess-2", {"role": "user", "content": "Hello session 2"})

        h1 = session_memory.validate_and_get_history("sess-1", dealer_id=1)
        h2 = session_memory.validate_and_get_history("sess-2", dealer_id=2)

        self.assertEqual(len(h1), 1)
        self.assertEqual(h1[0]["content"], "Hello session 1")
        self.assertEqual(len(h2), 1)
        self.assertEqual(h2[0]["content"], "Hello session 2")

    def test_session_bounded_turns(self):
        for i in range(30):
            session_memory.append_message("bounded-sess", {"role": "user", "content": f"msg {i}"})

        history = session_memory.validate_and_get_history("bounded-sess", dealer_id=1)
        self.assertLessEqual(len(history), session_memory.MAX_MESSAGES)


class AssistantChatEndpointTestCase(TestCase):
    """Integration tests for POST /api/assistant/chat/ endpoint."""

    def setUp(self):
        self.client = APIClient()
        session_memory.clear()
        self.dealer = Dealer.objects.create(
            dealer_code="DLR-TEST-02",
            name="Bangalore Auto Spares",
            city="Bengaluru",
            state="Karnataka",
        )
        self.product = Product.objects.create(
            sku="BRK-1044",
            name="Brake Pad Set - Bajaj Pulsar 150",
            category="Brakes",
            brand="Endurance",
            vehicle_fitment="Bajaj Pulsar 150",
            price=Decimal("1459.50"),
            description="Premium brake pads.",
        )
        Inventory.objects.create(product=self.product, quantity=50)

    def tearDown(self):
        session_memory.clear()
        assistant_client.set_mock_handler(None)

    def test_chat_contract_response_shape(self):
        # Mock LLM returning grounded recommendation and calling search_parts
        def mock_llm(system_prompt, history, user_message, authorized_dealer_id):
            tool_calls = [{"name": "search_parts", "arguments": {"query": "brake pads", "vehicle": "Pulsar 150"}}]
            actions = []
            reply = "Yes, Endurance Brake Pad Set (BRK-1044) fits Bajaj Pulsar 150 with 50 units in stock at 1459.50."
            new_msgs = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": reply},
            ]
            return reply, tool_calls, actions, new_msgs

        assistant_client.set_mock_handler(mock_llm)

        payload = {
            "session_id": "test-session-101",
            "dealer_id": self.dealer.id,
            "message": "Do you have brake pads for Pulsar 150?",
        }
        res = self.client.post("/api/assistant/chat/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        data = res.json()
        self.assertIn("reply", data)
        self.assertIn("cited_skus", data)
        self.assertIn("tool_calls", data)
        self.assertIn("actions", data)

        self.assertIsInstance(data["reply"], str)
        self.assertIsInstance(data["cited_skus"], list)
        self.assertIsInstance(data["tool_calls"], list)
        self.assertIsInstance(data["actions"], list)

        # Grounded citation test
        self.assertIn("BRK-1044", data["cited_skus"])
        self.assertEqual(data["tool_calls"][0]["name"], "search_parts")

    def test_chat_creates_draft_order_action(self):
        # Mock LLM calling create_draft_order
        def mock_order_llm(system_prompt, history, user_message, authorized_dealer_id):
            actions = []
            res_order = create_draft_order(
                dealer_id=authorized_dealer_id,
                items=[{"sku": "BRK-1044", "quantity": 2}],
                authorized_dealer_id=authorized_dealer_id,
                actions_accumulator=actions,
            )
            tool_calls = [{
                "name": "create_draft_order",
                "arguments": {"dealer_id": authorized_dealer_id, "items": [{"sku": "BRK-1044", "quantity": 2}]},
            }]
            reply = f"I have created draft order {res_order['order_number']} for 2 units of BRK-1044."
            new_msgs = [{"role": "user", "content": user_message}, {"role": "assistant", "content": reply}]
            return reply, tool_calls, actions, new_msgs

        assistant_client.set_mock_handler(mock_order_llm)

        payload = {
            "session_id": "test-session-order",
            "dealer_id": self.dealer.id,
            "message": "Please order 2 units of BRK-1044",
        }
        res = self.client.post("/api/assistant/chat/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        data = res.json()
        self.assertEqual(len(data["actions"]), 1)
        self.assertEqual(data["actions"][0]["type"], "draft_order_created")
        self.assertTrue(data["actions"][0]["order_number"].startswith("ORD-"))

        # Verify only DRAFT was created
        created_order = Order.objects.get(order_number=data["actions"][0]["order_number"])
        self.assertEqual(created_order.status, "DRAFT")

    def test_chat_validation_missing_dealer(self):
        payload = {
            "session_id": "sess-err",
            "dealer_id": 999999,  # Non-existent dealer
            "message": "Hello",
        }
        res = self.client.post("/api/assistant/chat/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        data = res.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")

    def test_chat_validation_missing_fields(self):
        # Missing message
        res1 = self.client.post("/api/assistant/chat/", {"session_id": "s1", "dealer_id": self.dealer.id}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res1.json()["error"]["code"], "VALIDATION_ERROR")

        # Empty session_id
        res2 = self.client.post(
            "/api/assistant/chat/",
            {"session_id": "   ", "dealer_id": self.dealer.id, "message": "Hi"},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res2.json()["error"]["code"], "VALIDATION_ERROR")

    def test_chat_service_unavailable_when_no_key(self):
        # When no mock and no key configured
        assistant_client.set_mock_handler(None)
        with patch.dict("os.environ", {}, clear=True):
            payload = {
                "session_id": "sess-no-key",
                "dealer_id": self.dealer.id,
                "message": "Hello",
            }
            res = self.client.post("/api/assistant/chat/", payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            data = res.json()
            self.assertEqual(data["error"]["code"], "SERVICE_UNAVAILABLE")

    def test_cited_skus_filters_out_fabricated_skus(self):
        # If reply mentions a fabricated SKU like "XYZ-9999", extract_cited_skus
        # must NOT include it because it doesn't exist in the database!
        reply = "Here is BRK-1044 which fits your bike, and maybe XYZ-9999 which is made up."
        cited = extract_cited_skus(reply, [])
        self.assertIn("BRK-1044", cited)
        self.assertNotIn("XYZ-9999", cited)
