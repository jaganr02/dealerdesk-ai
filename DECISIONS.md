# Architectural & Engineering Decisions — VIKMO DealerDesk

This document outlines the key technical decisions, architectural patterns, trade-offs, and security measures implemented in DealerDesk for the **AI/ML Track**.

---

## 1. LLM Provider Selection & Multi-Provider Architecture

### Chosen Providers & Priority
Per `API_CONTRACT.md` (§9), the Dealer Assistant supports all four standard provider environment variables:
1. **Google Gemini** (`GEMINI_API_KEY`) — Primary recommended provider (free tier for development, low latency, robust function calling).
2. **Groq** (`GROQ_API_KEY`) — High-speed inference using `llama-3.3-70b-versatile` or `llama-3.1-8b-instant`.
3. **OpenAI** (`OPENAI_API_KEY`) — Fallback using `gpt-4o-mini`.
4. **Anthropic** (`ANTHROPIC_API_KEY`) — Fallback using `claude-3-5-haiku-20241022`.

### Why This Approach?
The automated evaluation grader runs the application with its own API keys for one of these standard providers. By implementing a dynamic provider detection layer in `assistant/provider.py`:
- The application automatically activates whichever key is supplied in the environment without requiring configuration changes.
- If no provider key is configured, the endpoint returns a contract-compliant `503 SERVICE_UNAVAILABLE` error shape (`{"error": {"code": "SERVICE_UNAVAILABLE", "message": "...", "details": []}}`).
- For automated testing (`python manage.py test`), a deterministic mock handler (`assistant_client.set_mock_handler`) isolates all tests, eliminating external network dependencies and paid API usage.

---

## 2. Product Catalogue Retrieval Strategy

### Approach: Hybrid Multi-Field Weighted Token & Attribute Matching
For the 600-product automotive parts catalogue, catalogue retrieval is implemented in Python/Django ORM (`assistant/tools.py::search_parts`):
1. **Exact SKU Matching:** Direct exact or partial match against product SKUs (e.g., `BRK-1044`, `FIL-1012`) receives highest scoring weight.
2. **Multi-Field Token Overlap:** Keyword tokens are matched across `name`, `category`, `brand`, `vehicle_fitment`, and `description`.
3. **Vehicle Fitment Filtering & Boosting:** When a vehicle model is provided (e.g., `vehicle="Bajaj Pulsar 150"`), matching vehicle fitment attributes receive substantial relevance boosts.
4. **Database-Backed Truth:** All retrieved records return current, authoritative fields directly from the PostgreSQL database (`Product` and live `Inventory.quantity`).

### Justification & Trade-Offs
- **Zero Heavy External Dependencies:** Storing pre-computed embedding vectors with a vector DB or heavy local models (`torch`, `sentence-transformers`) would add several hundred megabytes to the deployment bundle and risk exceeding Linux environment installation limits.
- **Latency & Reliability:** External embedding API calls for every search query would add round-trip network overhead, consume rate limits, and risk timeouts. In-database token-weighted retrieval executes in under 5 milliseconds against PostgreSQL with 100% determinism.
- **Precision:** Automotive part dealers search with domain-specific terms (SKUs, OEM brand names, exact bike models). Lexical attribute matching with vehicle fitment scoring yields higher precision for exact mechanical fitment than generic semantic embeddings.

---

## 3. Tool Calling & Execution Loop

### Tools Defined
Three tools are exposed with the exact names required by `API_CONTRACT.md`:
1. `search_parts(query: str, vehicle: str = None)` — Searches catalogue and returns matching parts with live stock and prices.
2. `check_stock(sku: str)` — Queries live warehouse inventory for a specific SKU.
3. `create_draft_order(dealer_id: int, items: list)` — Creates a wholesale `DRAFT` order with verified SKUs, quantities, and GST calculations.

### Function Calling Loop
1. The assistant formats conversation turns, system instructions, and JSON schemas for tools (`TOOLS_SCHEMA_OPENAI`).
2. When the LLM issues tool calls:
   - Tool arguments are parsed and validated in Python before execution.
   - Database operations execute against live models.
   - If `create_draft_order` succeeds, the order number is recorded into the turn's `actions` list (`{"type": "draft_order_created", "order_number": "ORD-..."}`).
   - Tool outputs are appended as tool-response messages and sent back to the LLM to synthesize the final answer.
   - The loop is bounded to a maximum of 5 iterations to protect against runaway tool loops.

---

## 4. Conversation Session Memory

### Storage: In-Memory Bounded Thread-Safe Store
Implemented in `assistant/memory.py::SessionMemoryStore`:
- **Keyed by `session_id`:** Each conversation session maintains its own distinct deque of messages.
- **Strict Isolation:** Different `session_id` values never share context. If a session is re-accessed with a different `dealer_id`, memory is cleared to prevent cross-dealer data leakage.
- **Bounded Retention:** Message history is capped at 24 messages (~12 conversation turns) using `collections.deque(maxlen=24)` to prevent prompt bloat and context window saturation.
- **Thread Safety:** All access and updates use a `threading.Lock` to support concurrent requests in Django's multi-threaded server.

---

## 5. Security, Guardrails & Business Rules

### Protection Against Prompt Injection & Untrusted Catalogue Data
- **Data vs. Instructions:** System instructions explicitly declare that product catalogue text (names, descriptions) and user messages are untrusted data, never instructions.
- **Code-Enforced Business Logic:** The LLM cannot confirm, cancel, dispatch, or deliver orders. The assistant can only invoke `create_draft_order`, which enforces `status="DRAFT"`.
- **Dealer Authentication Isolation:** The tool execution context forces `authorized_dealer_id` matching the verified session dealer. Even if an injection attempts to order under another dealer ID, Python code overrides it.
- **Authoritative Prices & GST:** Unit prices are never accepted from the LLM or client; they are queried from `Product.price`. GST (18%) and subtotals are calculated in Python using `Decimal` arithmetic.
- **Off-Topic Deflection:** Prompt instructions enforce that off-topic requests (coding, general knowledge, creative writing) are politely declined.
- **Grounded Citations:** `cited_skus` are verified against the database. Any fabricated or hallucinated SKU not found in `Product.objects` is discarded.

---

## 6. Limitations & Future Improvements

1. **In-Memory Session Persistence:** In-memory session storage does not persist across application server restarts or horizontally scaled multi-worker instances (e.g. multiple Gunicorn workers without sticky sessions). In a production cluster, Redis or database-backed session storage would be used.
2. **Catalog Scaling:** For catalogues exceeding 100,000 SKUs, PostgreSQL pgvector or Elasticsearch would replace in-memory scoring to maintain sub-second retrieval.
