# VIKMO DealerDesk — B2B Dealer Ordering & AI/ML Platform

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/jaganr02/dealerdesk-ai)
[![Assignment Track](https://img.shields.io/badge/Assignment%20Track-AI%2FML%20(aiml)-emerald)](https://github.com/jaganr02/dealerdesk-ai)
[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.1+-green)](https://www.djangoproject.com/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%20Only-336791?logo=postgresql)](https://www.postgresql.org/)
[![LLM](https://img.shields.io/badge/LLM-Google%20Gemini%202.5%20Flash-orange?logo=google)](https://ai.google.dev/)

Repository: [https://github.com/jaganr02/dealerdesk-ai](https://github.com/jaganr02/dealerdesk-ai)

---

## 1. Project Overview & Assignment Track

**VIKMO DealerDesk** is a production-grade B2B ordering and intelligence platform for an automotive spare parts distributor headquartered in Bengaluru, Karnataka. The distributor serves 25 authorized dealerships across South India (Karnataka, Tamil Nadu, Kerala, Andhra Pradesh, and Telangana) managing an active catalogue of 600 automotive spare parts.

### Selected Track: `aiml` (AI / ML Track)

This repository is built and submitted for the **AI / ML Track (`aiml`)** of the VIKMO DealerDesk Take-Home Assignment. Per the official `API_CONTRACT.md`, this track delivers:
1. **Core Domain APIs**: Fully functional Product Catalogue (§4), Inventory (§5), Dealer Accounts (§6), and DRAFT Orders (§7.1).
2. **GenAI Dealer Assistant (§9)**: Intelligent assistant with automated tool calling (`search_parts`, `check_stock`, `create_draft_order`), conversation memory isolation, database-grounded pricing, and verified SKU citations.
3. **ML Demand Forecasting & Reorder System (§10)**: 160-record weekly demand forecast artifact (`ml/forecast.csv`), single-SKU 4-week forecast API, and inventory safety stock & reorder recommendations API.
4. **Interactive B2B Dealer Portal Frontend**: Modern responsive web application supporting live catalogue browsing, cart checkout with 18% GST calculation, AI chat assistant, and forecasting analytics.

---

## 2. Video Walkthrough

> [!NOTE]
> Below is the submission placeholder for the final video walkthrough demonstrating the application, live database operations, Gemini tool-calling assistant, and ML forecasting dashboard.

- **Demo Video URL**: `[Insert Unlisted YouTube / Loom / Shareable Google Drive Link Here]`
- **Video Coverage**:
  - Environment setup and PostgreSQL migration on Windows/Linux.
  - Idempotent database seeding (`python manage.py seed_data`).
  - Running automated unit tests and official `smoke_test.py --track aiml`.
  - Dealer Assistant interactive chat with live tool execution and grounded citations.
  - Demand forecasting visualization and dynamic reorder suggestion calculation.
  - B2B Dealer Portal UI features and end-to-end draft order creation.

---

## 3. Technology Stack & LLM Configuration

### Backend & Core Systems
- **Language**: Python 3.11+ (Python 3.13 tested)
- **Web Framework**: Django 5.1+ / Django REST Framework 3.15+
- **Database Engine**: PostgreSQL mandatory via `psycopg[binary]>=3.2.0` and `dj-database-url>=2.2.0` (SQLite is strictly prohibited per contract).
- **Environment Management**: `python-dotenv>=1.0.1`
- **API Documentation**: `drf-spectacular>=0.28.0` (OpenAPI 3.0 schema, Swagger UI, and ReDoc)
- **Authentication**: JWT via `djangorestframework-simplejwt>=5.5.0` (optional role-based routes)

### AI / GenAI Dealer Assistant
- **Configured Model**: **Google Gemini 2.5 Flash (`gemini-2.5-flash`)**
- **LLM Connection**: Interfaced through Google Gemini's official OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`) via the `openai>=1.50.0` client, providing robust multi-turn structured tool calling.
- **Environment Variable**: `GEMINI_API_KEY`
- **Dynamic Multi-Provider Support**: Implemented in [`assistant/provider.py`](file:///e:/vikmoo/assistant/provider.py). If another provider key is supplied by the evaluation grader, the assistant automatically switches:
  - Google Gemini: `GEMINI_API_KEY` &rarr; `gemini-2.5-flash` *(Primary)*
  - Groq: `GROQ_API_KEY` &rarr; `llama-3.3-70b-versatile`
  - OpenAI: `OPENAI_API_KEY` &rarr; `gpt-4o-mini`
  - Anthropic: `ANTHROPIC_API_KEY` &rarr; `claude-3-5-haiku-20241022`

### Machine Learning & Data Science
- **Libraries**: `scikit-learn`, `pandas`, `numpy`
- **Forecasting Engine**: Autoregressive multi-step `RandomForestRegressor` trained in [`ml/train_and_forecast.py`](file:///e:/vikmoo/ml/train_and_forecast.py) using historical weekly sales, promotional calendars, and non-linear festival lift proximity.

### Frontend
- **Interface**: DealerDesk B2B Portal served at `/` and `/dealer/` via [`templates/dealer/index.html`](file:///e:/vikmoo/templates/dealer/index.html) and [`static/dealer/`](file:///e:/vikmoo/static/dealer/).
- **Styling & Logic**: Modern Vanilla CSS and ES6 JavaScript (zero heavy node runtime build requirements).

---

## 4. Project Structure

```
dealerdesk-ai/
├── manage.py                          # Django management script
├── requirements.txt                   # Production and ML dependencies
├── smoke_test.py                      # Official contract smoke test suite
├── API_CONTRACT.md                    # Exact API specification and scoring rules
├── DECISIONS.md                       # Architectural and engineering design records
├── README.md                          # Project documentation and setup guide
├── .env.example                       # Environment variable template
├── .gitignore                         # Git exclusion rules
│
├── accounts/                          # User accounts, JWT auth, and role verification
│   ├── models.py                      # Custom User model with Role enum (DEALER, SUPPLIER)
│   ├── views.py                       # JWT token views & role verification test endpoints
│   └── urls.py                        # /api/auth/ routing
│
├── assistant/                         # GenAI Dealer Assistant (§9)
│   ├── memory.py                      # Thread-safe in-memory session store (bounded deque)
│   ├── provider.py                    # Multi-provider LLM client & gemini-2.5-flash tool loop
│   ├── serializers.py                 # Request/response validation schemas
│   ├── service.py                     # AssistantService, prompt builder, cited SKU extraction
│   ├── tools.py                       # search_parts, check_stock, create_draft_order tools
│   ├── urls.py                        # /api/assistant/chat/ endpoint
│   ├── views.py                       # AssistantChatView controller
│   └── tests.py                       # Mocked assistant & tool-calling unit tests
│
├── data/                              # Official dataset files (read-only for grader)
│   ├── catalogue.csv                  # 600 catalogue products and stock levels
│   ├── dealers.csv                    # 25 authorized South India dealerships
│   ├── festival_calendar.csv          # Major holiday and Diwali festival dates
│   ├── lead_times.csv                 # Supplier lead times for 40 forecast SKUs
│   ├── promo_calendar.csv             # Historical distributor promotional weeks
│   └── sales_history.csv              # Weekly SKU sales history
│
├── dealerdesk/                        # Django project root configuration
│   ├── asgi.py                        # ASGI entry point
│   ├── exceptions.py                  # Contract-compliant custom error handlers
│   ├── settings.py                    # Settings (PostgreSQL enforcement, apps, CORS)
│   ├── urls.py                        # Master URL routing (includes admin, docs, portal)
│   ├── views.py                       # Health check endpoint (/api/health/)
│   └── wsgi.py                        # WSGI entry point
│
├── inventory/                         # Core domain: Products, Inventory, Dealers, Orders
│   ├── admin.py                       # Django Admin registrations
│   ├── models.py                      # Product, Inventory, Dealer, Order, OrderItem
│   ├── serializers.py                 # DRF serializers matching API_CONTRACT.md
│   ├── supplier_sync.py               # Paginated supplier catalogue synchronizer
│   ├── urls.py                        # /api/products/, /api/inventory/, /api/orders/
│   ├── views.py                       # Core API controllers & DealerPortalView
│   ├── tests.py                       # Domain logic, stock constraint, and ordering tests
│   └── management/commands/
│       └── seed_data.py               # Idempotent database seeder (catalogue & dealers)
│
├── ml/                                # ML Demand Forecasting & Reorder Suggestions (§10)
│   ├── forecast.csv                   # 160-row committed forecast artifact (40 SKUs × 4 weeks)
│   ├── serializers.py                 # Forecast and reorder recommendation serializers
│   ├── services.py                    # Forecast loading, sigma computation, reorder math
│   ├── train_and_forecast.py          # Model training & forecast generation script
│   ├── urls.py                        # /api/forecast/{sku}/ & /api/reorder-suggestions/
│   ├── views.py                       # ForecastDetailView & ReorderSuggestionsView
│   └── tests.py                       # ML endpoint and reorder mathematical tests
│
├── static/dealer/                     # Portal frontend assets (CSS, JS, category SVGs)
└── templates/dealer/                  # Portal frontend HTML templates
```

---

## 5. Core APIs: Catalogue, Inventory, Dealers & Orders

All responses adhere strictly to the JSON conventions, trailing slashes, and error shape defined in `API_CONTRACT.md`:
```json
{"error": {"code": "VALIDATION_ERROR", "message": "Human readable text", "details": []}}
```

### 5.1 Products Catalogue API (§4)
- **`GET /api/products/`**: Paginated list (`count`, `next`, `previous`, `results`).
  - Supports filters: `?search=` (case-insensitive substring match on `sku`, `name`, or `brand`), `?category=` (exact match), `?vehicle=` (case-insensitive substring match on `vehicle_fitment`), `?page=`, `?page_size=`.
  - Prices are strings formatted to 2 decimal places (`"1459.50"`). `stock` is the current live available inventory integer.
- **`POST /api/products/`**: Creates a new product with initial stock 0. Validates `price > 0.00`. Duplicate SKU returns `409 DUPLICATE`.
- **`GET /api/products/{sku}/`**: Retrieves product details by SKU. Returns `404 NOT_FOUND` if absent.
- **`PATCH /api/products/{sku}/`**: Updates product metadata (e.g., price, description). SKU cannot be modified.

### 5.2 Inventory API (§5)
- **`PUT /api/inventory/{sku}/`**: Updates physical stock quantity.
  - Body: `{"quantity": 25, "reason": "stock count correction"}`.
  - Enforces `quantity >= 0` (returns `400 VALIDATION_ERROR` for negative quantities). Returns `200 {"sku": "...", "quantity": 25}`.

### 5.3 Dealers API (§6)
- **`GET /api/dealers/`**: Paginated list of authorized dealers with credit limits, GSTIN, and contact information.
- **`POST /api/dealers/`**: Creates a new dealer account (`dealer_code` and `name` required). Returns `409 DUPLICATE` if `dealer_code` already exists.
- **`GET /api/dealers/{id}/`**: Retrieves dealer details by integer ID.

### 5.4 Draft Orders API (§7.1)
- **`POST /api/orders/`**: Creates a new **`DRAFT`** order.
  - Body: `{"dealer_id": 7, "items": [{"sku": "BRK-1044", "quantity": 3}]}`.
  - Validates that the dealer exists, every SKU exists, items list is non-empty, quantities are integers &ge; 1, and no duplicate SKUs are submitted in the same order.
  - Monetary values are calculated with Decimal precision: `unit_price` equals current catalogue price, `line_subtotal = unit_price * quantity`, `line_tax = line_subtotal * 0.18` (rounded per line using `ROUND_HALF_UP`), and `grand_total = subtotal + tax_total`.
  - Supports the optional `Idempotency-Key` header to safely prevent duplicate submissions.
- **`GET /api/orders/`**: Paginated list of orders. Filterable by `dealer_id` and `status`.
- **`GET /api/orders/{order_number}/`**: Retrieves full order details including line items, tax breakdowns, and status.
- **`PUT /api/orders/{order_number}/`**: Replaces all line items in an order. Restricted strictly to `DRAFT` status (`409 ORDER_LOCKED` if confirmed/dispatched).

---

## 6. GenAI Dealer Assistant & Tool Calling Flow

The Dealer Assistant endpoint (`POST /api/assistant/chat/`) provides an intelligent ordering interface for authorized parts dealers.

### Execution Flow
```
User Message
    │
    ▼
[POST /api/assistant/chat/] ──▶ AssistantChatView (assistant/views.py)
                                    │
                                    ▼
                             AssistantService.handle_chat() (assistant/service.py)
                                    │
                                    ├──▶ Loads session history: session_memory (assistant/memory.py)
                                    ├──▶ Formats system prompt with dealer context
                                    │
                                    ▼
                             AssistantLLMClient.run_turn() (assistant/provider.py)
                                    │
                                    ├──▶ Invokes Google Gemini 2.5 Flash via OpenAI endpoint
                                    │    (tools schema: search_parts, check_stock, create_draft_order)
                                    │
                                    ▼
                             Gemini issues tool call
                                    │
                                    ▼
                             execute_tool() (assistant/provider.py)
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
search_parts()                 check_stock()              create_draft_order()
(assistant/tools.py)        (assistant/tools.py)           (assistant/tools.py)
    │                               │                               │
    └───────────────────────────────┼───────────────────────────────┘
                                    │
                                    ▼
                         Database Tool Results (PostgreSQL)
                                    │
                                    ▼
                         Tool output fed back to Gemini
                                    │
                                    ▼
                         Gemini synthesizes final response
                                    │
                                    ▼
                         extract_cited_skus() verifies real SKUs
                                    │
                                    ▼
                         Final JSON Response to Dealer:
                         {"reply", "cited_skus", "tool_calls", "actions"}
```

### Real Source Files & Components
1. **Endpoint Controller**: [`AssistantChatView`](file:///e:/vikmoo/assistant/views.py) validates the request payload (`session_id`, `dealer_id`, `message`) and verifies the dealer exists.
2. **Orchestration Layer**: [`AssistantService.handle_chat()`](file:///e:/vikmoo/assistant/service.py) loads conversation turns, formats `SYSTEM_PROMPT_TEMPLATE`, runs the LLM turn, updates memory, and extracts verified citations.
3. **Session Memory**: [`session_memory`](file:///e:/vikmoo/assistant/memory.py) maintains a thread-safe, bounded in-memory `deque` (last 24 messages) keyed by `session_id`. If a session is accessed with a different `dealer_id`, memory is cleared to prevent cross-dealer data leakage.
4. **LLM Client & Tool Calling Loop**: [`AssistantLLMClient`](file:///e:/vikmoo/assistant/provider.py) uses `_run_gemini_turn()` with `gemini-2.5-flash`. It executes an iterative function-calling loop (bounded to 5 iterations) passing tools defined in `TOOLS_SCHEMA_OPENAI`.
5. **Database Tools**: Defined in [`assistant/tools.py`](file:///e:/vikmoo/assistant/tools.py):
   - **`search_parts(query, vehicle=None)`**: Performs hybrid multi-field token matching across `sku`, `name`, `category`, `brand`, and `vehicle_fitment` against live `Product` and `Inventory` tables.
   - **`check_stock(sku)`**: Returns the exact live available quantity and unit price from PostgreSQL.
   - **`create_draft_order(dealer_id, items)`**: Enforces `authorized_dealer_id`, validates all SKUs, calculates 18% GST, creates database `Order` and `OrderItem` records with `status="DRAFT"`, and records `{"type": "draft_order_created", "order_number": "ORD-..."}` in `actions`.
6. **Grounded Citations**: [`extract_cited_skus()`](file:///e:/vikmoo/assistant/service.py) scans the model's reply with regex, filters candidates against `Product.objects.filter(sku__in=...)`, and discards any hallucinated SKU.
7. **Security Guardrails**:
   - System instructions mandate that product descriptions and user messages are untrusted data, preventing prompt injection.
   - The assistant is strictly prohibited from confirming, cancelling, or dispatching orders.
   - Off-topic queries (coding, trivia, chit-chat) are politely declined.

---

## 7. Demand Forecasting & Reorder Suggestions (ML)

### 7.1 Forecast Artifact (`ml/forecast.csv`)
- Committed in the repository at [`ml/forecast.csv`](file:///e:/vikmoo/ml/forecast.csv).
- Contains exactly **160 rows** (40 target SKUs from `data/lead_times.csv` &times; 4 forecast weeks).
- Exact header format: `sku,week_start,forecast_units`.
- Forecast target weeks: **`2026-09-28`**, **`2026-10-05`**, **`2026-10-12`**, **`2026-10-19`**.
- All `forecast_units` values are non-negative numeric estimates.

### 7.2 Forecasting Methodology (`ml/train_and_forecast.py`)
The forecast artifact was generated via the dedicated training pipeline in [`ml/train_and_forecast.py`](file:///e:/vikmoo/ml/train_and_forecast.py):
1. **Data Ingestion**: Merges `data/sales_history.csv`, `data/promo_calendar.csv`, `data/lead_times.csv`, and `data/festival_calendar.csv`.
2. **Feature Engineering**:
   - Autoregressive lag features (`lag_1`, `lag_2`, `lag_3`, `lag_4`).
   - Rolling statistics over sales: 4-week moving average (`roll_mean_4`), 12-week moving average (`roll_mean_12`), and 12-week volatility (`roll_std_12`).
   - Promotional indicator flag (`promo_flag`).
   - Calendar features: `month` and `week_of_year`.
   - **Festival Lift Proximity**: Calculates non-linear demand spikes near Diwali using a Gaussian proximity decay function:
     $$\text{fest\_lift} = \exp\left(-\frac{(d + 7)^2}{2 \times 14^2}\right) \quad \text{for } -30 \le d \le 14$$
   - One-hot encoded SKU categorical indicators.
3. **Model Training**: A `RandomForestRegressor(n_estimators=150, max_depth=16, random_state=42)` trained on historical weekly demand.
4. **Multi-Step Autoregressive Projection**: Iteratively projects weekly forecasts for the four target weeks, updating lag buffers dynamically for each SKU.

### 7.3 Forecasting & Reorder APIs
- **`GET /api/forecast/{sku}/`**: Handled by [`ForecastDetailView`](file:///e:/vikmoo/ml/views.py) and [`get_forecast_for_sku()`](file:///e:/vikmoo/ml/services.py).
  - Returns `200` with the 4 forecast weeks matching `ml/forecast.csv`:
    ```json
    {
      "sku": "FIL-1016",
      "forecast": [
        {"week_start": "2026-09-28", "forecast_units": 49.8},
        {"week_start": "2026-10-05", "forecast_units": 52.1},
        {"week_start": "2026-10-12", "forecast_units": 54.0},
        {"week_start": "2026-10-19", "forecast_units": 48.6}
      ]
    }
    ```
  - Returns `404 NOT_FOUND` for non-forecast or unknown SKUs.

- **`GET /api/reorder-suggestions/`**: Handled by [`ReorderSuggestionsView`](file:///e:/vikmoo/ml/views.py) and [`compute_reorder_suggestions()`](file:///e:/vikmoo/ml/services.py).
  - Returns `200 {"results": [...]}` with all 40 forecast SKUs (unpaginated).
  - Implements the exact contract formulation:
    - $L = \text{lead\_time\_weeks}$ from `data/lead_times.csv`
    - $\text{lead\_time\_demand} = \sum_{w=1}^{L} \text{forecast\_units}_w$ (sum of first $L$ forecast weeks)
    - $\sigma = \text{sample standard deviation (ddof=1)}$ of `units_sold` over the most recent 12 weeks of `data/sales_history.csv` for that SKU
    - $\text{safety\_stock} = \lceil 1.65 \times \sigma \times \sqrt{L} \rceil$
    - $\text{reorder\_point} = \text{lead\_time\_demand} + \text{safety\_stock}$
    - $\text{reorder\_qty} = \max(0, \lceil \text{reorder\_point} - \text{current\_stock} \rceil)$
    - $\text{current\_stock} =$ live available quantity from `Inventory.objects` at request time.

---

## 8. Interactive B2B Dealer Portal Frontend

In addition to headless JSON APIs, DealerDesk includes a rich, fully responsive Single Page Application (SPA) Dealer Portal served at the root URL `/` and `/dealer/`:

- **Catalogue Browser**: Fast search and filtering across 600 SKUs by vehicle fitment (e.g. "Bajaj Pulsar", "Royal Enfield Classic 350"), category (Brakes, Engine, Electrical, Filters, etc.), and brand.
- **Interactive Slide-over Cart**: Real-time quantity adjustment, credit limit calculation, line-by-line 18% GST breakdown, and instant draft order placement.
- **Embedded AI Dealer Assistant**: Chat widget allowing dealers to inquire about part compatibility, inspect warehouse stock levels, and place draft orders conversationally. Includes tool-call inspection badges and interactive SKU citation chips.
- **Demand Forecasting & Reorder Dashboard**: Interactive visualizer for the 40 forecast SKUs displaying lead time demand, safety stock thresholds, reorder flags, and 4-week forecast charts.
- **Orders & Profile Hub**: View order status, order totals, and live dealer credit utilization.

---

## 9. Installation & Running on Windows (VS Code Terminal)

Follow these step-by-step instructions to run DealerDesk locally in VS Code on Windows (PowerShell or Command Prompt).

### Step 1: Prerequisites
- **Python**: Version 3.11, 3.12, or 3.13 installed (ensure *"Add Python to PATH"* was selected during installation).
- **PostgreSQL**: A running PostgreSQL instance (local PostgreSQL server on port 5432, or a hosted PostgreSQL instance like Supabase / Neon).

### Step 2: Open Terminal & Create Virtual Environment
In VS Code, open the repository root folder `dealerdesk-ai` (`Ctrl + ~` to open the integrated terminal):

```powershell
# Create a virtual environment named .venv
python -m venv .venv

# Activate the virtual environment in PowerShell
.\.venv\Scripts\Activate.ps1

# (If using Windows Command Prompt cmd.exe instead, use:)
# .\.venv\Scripts\activate.bat
```

> *Tip for PowerShell execution policy error*: If script execution is restricted, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables (`.env`)
Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```

Edit `.env` in VS Code and supply your PostgreSQL connection string and Gemini API key:
```ini
# Django Configuration
SECRET_KEY=django-insecure-dealerdesk-local-dev-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,testserver

# PostgreSQL Database (Mandatory: SQLite is strictly prohibited)
# Format: postgresql://<user>:<password>@<host>:<port>/<dbname>
DATABASE_URL=postgresql://postgres:your_postgres_password@localhost:5432/dealerdesk

# Google Gemini API Key (Required for Dealer Assistant)
GEMINI_API_KEY=your_gemini_api_key_here
```

### Step 5: Apply PostgreSQL Migrations
Create all database tables, check constraints, and indexes:
```powershell
python manage.py migrate
```

### Step 6: Seed Database
Populate the 600 catalogue products, warehouse inventory records, and 25 authorized dealers:
```powershell
python manage.py seed_data
```
*Note*: `seed_data` is strictly idempotent. Running it multiple times will update records without generating duplicates.

### Step 7: Start the Development Server
```powershell
python manage.py runserver 0.0.0.0:8000
```

Access the application in your browser:
- **Dealer Portal**: [http://localhost:8000/](http://localhost:8000/)
- **Interactive Swagger UI**: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)
- **ReDoc Documentation**: [http://localhost:8000/api/redoc/](http://localhost:8000/api/redoc/)
- **Django Admin**: [http://localhost:8000/admin/](http://localhost:8000/admin/)
- **API Health Check**: [http://localhost:8000/api/health/](http://localhost:8000/api/health/)

---

## 10. Automated Tests & Official Smoke Test

### 10.1 Automated Unit & Integration Tests
Run Django's test runner to execute unit tests across models, serializers, stock validation, mocked assistant tool loops, and ML reorder mathematical calculations:
```powershell
python manage.py test
```

### 10.2 Official AI/ML Smoke Test
In a second terminal window (while the server is running on port 8000), execute the official assignment smoke test targeting the AI/ML track:

```powershell
python smoke_test.py --base-url http://localhost:8000 --track aiml
```

To run all checks across every module (core, assistant, forecast, sync):
```powershell
python smoke_test.py --base-url http://localhost:8000 --all
```

---

## 11. Optional Features Implemented & Assumptions

### Optional Features Implemented (Bonus Points)
1. **Full Order Lifecycle Management (§7.2–§7.4)**: Beyond the minimum DRAFT order requirement for the AI/ML track, this repository implements full order status transitions:
   - `POST /api/orders/{order_number}/confirm/`: Atomic stock deduction using `select_for_update()` row-level locking to prevent race conditions, locking catalogue prices.
   - `POST /api/orders/{order_number}/cancel/`: Idempotently restores stock when a confirmed order is cancelled.
   - `POST /api/orders/{order_number}/dispatch/` and `POST /api/orders/{order_number}/deliver/`: Full supply-chain status transitions.
2. **Idempotency Protection (§7.5)**: Implemented using unique `Idempotency-Key` headers on `POST /api/orders/`, safely caching request hashes to eliminate duplicate orders during network retries.
3. **Supplier Catalogue Synchronization (§8)**: Fully implemented in [`inventory/supplier_sync.py`](file:///e:/vikmoo/inventory/supplier_sync.py) at `POST /api/sync/supplier/`, handling cursor-based pagination, rate limits (`429 Retry-After`), exponential backoff, and idempotent catalogue updates without modifying distributor warehouse stock.
4. **OpenAPI 3.0 Documentation**: Auto-generated interactive Swagger UI and ReDoc interfaces available at `/api/docs/` and `/api/redoc/`.
5. **Interactive Dealer Portal UI**: Complete graphical B2B dealer portal with live cart, assistant widget, and forecasting dashboards.

### Engineering Assumptions Supported by Code
- **Single Warehouse Model**: Inventory maintains a 1:1 relationship with `Product`, reflecting the distributor's central Bengaluru distribution facility.
- **In-Memory Session Store**: In accordance with `DECISIONS.md`, assistant conversation memory is maintained in a thread-safe in-memory store keyed by `session_id`. In production, this would be backed by Redis for multi-worker horizontal scaling.
- **Database Engine**: PostgreSQL is mandatory. `settings.py` explicitly rejects SQLite to guarantee transaction isolation, row-level locking, and concurrency safety.
- **GST Standard**: Automotive spare parts are taxed at 18% GST, calculated per line item and rounded using `ROUND_HALF_UP` to the exact paisa.
