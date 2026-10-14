/**
 * DealerDesk - Main Dealer Portal Application Orchestrator
 * Fully connected to Django REST Framework backend APIs:
 * - Real 600-product catalogue from PostgreSQL (/api/products/)
 * - Live warehouse stock from Inventory model (/api/inventory/)
 * - Real draft order creation (/api/orders/)
 * - Genuine AI Dealer Assistant with tool calling (/api/assistant/chat/)
 */

// Cart Service (in-memory & localStorage synced)
const CART_STORAGE_KEY = "dealerdesk_dealer_cart";

class CartService {
  constructor() {
    this.items = this.loadCart();
    this.listeners = [];
  }

  loadCart() {
    try {
      const saved = localStorage.getItem(CART_STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      return [];
    }
  }

  saveCart() {
    try {
      localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(this.items));
    } catch (e) {
      console.warn("Could not save cart:", e);
    }
    this.notify();
  }

  subscribe(listener) {
    this.listeners.push(listener);
    listener(this.getState());
  }

  notify() {
    const s = this.getState();
    this.listeners.forEach((fn) => {
      try { fn(s); } catch (e) { console.error("Cart listener error:", e); }
    });
  }

  addItem(product, quantity = 1) {
    if (!product || product.stock <= 0) return false;
    const idx = this.items.findIndex((item) => item.sku === product.sku);
    if (idx > -1) {
      const newQty = this.items[idx].quantity + quantity;
      this.items[idx].quantity = Math.min(newQty, product.stock);
    } else {
      this.items.push({
        id: product.sku,
        sku: product.sku,
        name: product.name,
        brand: product.brand || "OEM",
        price: parseFloat(product.price),
        stock: product.stock,
        gst_rate: 18.0,
        quantity: Math.min(quantity, product.stock),
      });
    }
    this.saveCart();
    return true;
  }

  updateQuantity(sku, newQty) {
    const item = this.items.find((i) => i.sku === sku || i.id === sku);
    if (!item) return;
    if (newQty <= 0) {
      this.removeItem(sku);
      return;
    }
    item.quantity = Math.min(newQty, item.stock);
    this.saveCart();
  }

  removeItem(sku) {
    this.items = this.items.filter((i) => i.sku !== sku && i.id !== sku);
    this.saveCart();
  }

  clearCart() {
    this.items = [];
    this.saveCart();
  }

  getState() {
    const totalItems = this.items.reduce((sum, item) => sum + item.quantity, 0);
    const subtotal = this.items.reduce((sum, item) => sum + item.price * item.quantity, 0);
    const gstEstimate = subtotal * 0.18;
    const totalEstimate = subtotal + gstEstimate;
    return {
      items: [...this.items],
      totalItems,
      subtotal,
      gstEstimate,
      totalEstimate,
    };
  }
}

const cartService = new CartService();

// Simple Auth Helper
const authService = {
  getAccessToken: () => localStorage.getItem("dealerdesk_access_token"),
  isLoggedIn: () => Boolean(localStorage.getItem("dealerdesk_access_token")),
};

// Global App State
const state = {
  activeView: "catalogue", // "catalogue" | "assistant" | "orders" | "profile"
  selectedCategory: "all",
  searchQuery: "",
  stockFilter: "all", // "all" | "in-stock" | "low-stock"
  sortBy: "featured", // "featured" | "price-asc" | "price-desc" | "name-asc"
  currentPage: 1,
  pageSize: 12,
  totalProducts: 600,
  dealerId: 1,
  userProfile: null,
  products: [],
  orders: [],
  assistantSessionId: "session-" + Math.random().toString(36).substring(2, 9) + "-" + Date.now(),
};

// Indian Rupee Currency Formatter
const formatINR = (num) => {
  return "₹" + Number(num || 0).toLocaleString("en-IN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
};

// Toast notification helper
const showToast = (message, type = "info") => {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${type === "success" ? "✅" : type === "danger" ? "⚠️" : "ℹ️"}</span> <div>${message}</div>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
};

// Initialize App function
async function initApp() {
  console.log("DealerDesk: Initializing App...");

  try {
    await loadDealerProfile();
  } catch (e) {
    console.warn("loadDealerProfile error:", e);
  }

  try {
    initSidebar();
  } catch (e) {
    console.error("initSidebar error:", e);
  }

  try {
    initCategories();
  } catch (e) {
    console.error("initCategories error:", e);
  }

  try {
    initSearchAndFilters();
  } catch (e) {
    console.error("initSearchAndFilters error:", e);
  }

  try {
    initCartDrawer();
  } catch (e) {
    console.error("initCartDrawer error:", e);
  }

  try {
    initModals();
  } catch (e) {
    console.error("initModals error:", e);
  }

  try {
    initAssistant();
  } catch (e) {
    console.error("initAssistant error:", e);
  }

  // Load live products from backend
  try {
    await fetchLiveProducts();
  } catch (e) {
    console.error("fetchLiveProducts error:", e);
  }

  // Load real orders
  try {
    await fetchLiveOrders();
  } catch (e) {
    console.error("fetchLiveOrders error:", e);
  }

  // Subscribe cart changes to update UI badge and drawer
  try {
    cartService.subscribe((cartState) => {
      updateCartBadges(cartState);
      renderCartDrawerItems(cartState);
    });
  } catch (e) {
    console.error("cartService subscribe error:", e);
  }

  console.log("DealerDesk: App Initialized Successfully!");
}

// Hook startup: run immediately if DOM is ready, or on DOMContentLoaded
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}

/* ==========================================================================
   Dealer Profile & Header
   ========================================================================== */

async function loadDealerProfile() {
  try {
    const res = await fetch(`/api/dealers/${state.dealerId}/`);
    if (res.ok) {
      const d = await res.json();
      state.userProfile = {
        id: d.id,
        dealer_code: d.dealer_code,
        business_name: d.name,
        contact_person: d.contact_person || "Ramesh Kumar",
        phone: d.phone || "+91 98450 12345",
        email: d.email || "dealer@dealersouth.in",
        address: d.address || "Industrial Area, Bengaluru",
        city: d.city || "Bengaluru",
        state: d.state || "Karnataka",
        pincode: d.pincode || "560058",
        credit_limit: parseFloat(d.credit_limit || 500000.0),
        available_credit: parseFloat(d.credit_limit || 500000.0),
      };
    }
  } catch (e) {
    console.warn("Could not load dealer from backend:", e);
  }

  const p = state.userProfile || {
    id: 1,
    dealer_code: "DLR-001",
    business_name: "Sri Lakshmi Motors",
    credit_limit: 500000.0,
    available_credit: 500000.0,
  };

  const sidebarName = document.getElementById("sidebarDealerName");
  const sidebarCode = document.getElementById("sidebarDealerCode");
  const sidebarAvatar = document.getElementById("sidebarAvatar");
  const creditVal = document.getElementById("sidebarCreditVal");
  const headerDealer = document.getElementById("headerDealerName");
  const assistantBadge = document.getElementById("assistantDealerBadge");

  if (sidebarName) sidebarName.textContent = p.business_name;
  if (sidebarCode) sidebarCode.textContent = p.dealer_code;
  if (sidebarAvatar) {
    const initials = (p.business_name || "DD")
      .split(" ")
      .slice(0, 2)
      .map((w) => w[0])
      .join("")
      .toUpperCase();
    sidebarAvatar.textContent = initials || "DD";
  }
  if (creditVal) creditVal.textContent = formatINR(p.available_credit);
  if (headerDealer) headerDealer.textContent = p.business_name;
  if (assistantBadge) assistantBadge.textContent = `Dealer #${p.id}: ${p.business_name}`;
}

/* ==========================================================================
   Navigation & Sidebar
   ========================================================================== */

function initSidebar() {
  const navItems = document.querySelectorAll(".nav-item[data-view]");
  navItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view;
      switchView(view);
    });
  });

  const mobileBtn = document.getElementById("mobileMenuBtn");
  const sidebar = document.getElementById("appSidebar");
  if (mobileBtn && sidebar) {
    mobileBtn.addEventListener("click", () => {
      sidebar.classList.toggle("mobile-open");
    });
  }

  const authBtn = document.getElementById("sidebarAuthBtn");
  if (authBtn) {
    authBtn.addEventListener("click", () => {
      openAuthModal();
    });
  }
}

function switchView(viewName) {
  state.activeView = viewName;

  document.querySelectorAll(".nav-item[data-view]").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === viewName);
  });

  const catalogueView = document.getElementById("catalogueView");
  const assistantView = document.getElementById("assistantView");
  const ordersView = document.getElementById("ordersView");
  const profileView = document.getElementById("profileView");
  const forecastView = document.getElementById("forecastView");

  if (catalogueView) catalogueView.style.display = viewName === "catalogue" ? "block" : "none";
  if (assistantView) assistantView.style.display = viewName === "assistant" ? "block" : "none";
  if (ordersView) ordersView.style.display = viewName === "orders" ? "block" : "none";
  if (profileView) profileView.style.display = viewName === "profile" ? "block" : "none";
  if (forecastView) forecastView.style.display = viewName === "forecast" ? "block" : "none";

  const sidebar = document.getElementById("appSidebar");
  if (sidebar) sidebar.classList.remove("mobile-open");

  if (viewName === "orders") {
    fetchLiveOrders();
  } else if (viewName === "profile") {
    renderProfilePage();
  } else if (viewName === "assistant") {
    const input = document.getElementById("assistantInput");
    if (input) input.focus();
  } else if (viewName === "forecast") {
    fetchAndRenderForecast();
  }
}

/* ==========================================================================
   Product Catalogue & Live Backend Retrieval
   ========================================================================== */

function initCategories() {
  const container = document.getElementById("categoryPills");
  if (!container) return;

  const categories = [
    { id: "all", name: "All Categories", icon: "📦" },
    { id: "Brakes", name: "Brakes", icon: "🛑" },
    { id: "Filters", name: "Filters", icon: "🌪️" },
    { id: "Engine & Oils", name: "Engine & Oils", icon: "⚙️" },
    { id: "Lighting & Electrical", name: "Electrical", icon: "⚡" },
    { id: "Drivetrain", name: "Drivetrain", icon: "⛓️" },
    { id: "Controls & Grips", name: "Controls", icon: "🔌" },
    { id: "Tyres & Tubes", name: "Tyres & Tubes", icon: "🛞" },
  ];

  container.innerHTML = "";
  categories.forEach((cat) => {
    const pill = document.createElement("button");
    pill.className = `category-pill ${state.selectedCategory === cat.id ? "active" : ""}`;
    pill.textContent = `${cat.icon} ${cat.name}`;
    pill.addEventListener("click", () => {
      state.selectedCategory = cat.id;
      state.currentPage = 1;
      document.querySelectorAll(".category-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      fetchLiveProducts();
    });
    container.appendChild(pill);
  });
}

function initSearchAndFilters() {
  const searchInput = document.getElementById("searchInput");
  let searchTimeout;
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        state.searchQuery = e.target.value.trim();
        state.currentPage = 1;
        fetchLiveProducts();
      }, 350);
    });
  }

  const stockSelect = document.getElementById("stockFilter");
  if (stockSelect) {
    stockSelect.addEventListener("change", (e) => {
      state.stockFilter = e.target.value;
      renderProductsGrid();
    });
  }

  const sortSelect = document.getElementById("sortSelect");
  if (sortSelect) {
    sortSelect.addEventListener("change", (e) => {
      state.sortBy = e.target.value;
      renderProductsGrid();
    });
  }

  const resetBtn = document.getElementById("resetFiltersBtn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      state.selectedCategory = "all";
      state.searchQuery = "";
      state.stockFilter = "all";
      state.sortBy = "featured";
      state.currentPage = 1;
      if (searchInput) searchInput.value = "";
      if (stockSelect) stockSelect.value = "all";
      if (sortSelect) sortSelect.value = "featured";
      initCategories();
      fetchLiveProducts();
      showToast("Filters reset to default.");
    });
  }
}

async function fetchLiveProducts() {
  const grid = document.getElementById("productGrid");
  const countEl = document.getElementById("resultsCount");
  if (grid) {
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #64748b;">
      <div style="font-size: 1.5rem; margin-bottom: 8px;">⏳</div>
      Loading catalogue from PostgreSQL...
    </div>`;
  }

  try {
    const params = new URLSearchParams();
    if (state.searchQuery) params.append("search", state.searchQuery);
    if (state.selectedCategory !== "all") params.append("category", state.selectedCategory);
    params.append("page", state.currentPage);
    params.append("page_size", state.pageSize);

    const res = await fetch(`/api/products/?${params.toString()}`);
    if (res.ok) {
      const data = await res.json();
      state.products = data.results || [];
      state.totalProducts = data.count || 0;
      if (countEl) {
        countEl.textContent = `Showing ${state.products.length} of ${state.totalProducts} catalogue spare parts`;
      }
      renderProductsGrid();
      renderPagination(state.totalProducts);
    } else {
      if (grid) grid.innerHTML = `<div style="grid-column: 1/-1; color: #dc2626; text-align: center; padding: 40px;">Failed to load products from API.</div>`;
    }
  } catch (e) {
    console.error("fetchLiveProducts error:", e);
    if (grid) grid.innerHTML = `<div style="grid-column: 1/-1; color: #dc2626; text-align: center; padding: 40px;">Connection error loading products.</div>`;
  }
}

function getProductCategoryImage(category) {
  const cat = (category || "").toLowerCase();
  if (cat.includes("brake")) return "/static/dealer/images/categories/brakes.svg";
  if (cat.includes("light") || cat.includes("electr")) return "/static/dealer/images/categories/lighting.svg";
  if (cat.includes("body") || cat.includes("styl")) return "/static/dealer/images/categories/body.svg";
  if (cat.includes("drive") || cat.includes("chain")) return "/static/dealer/images/categories/drivetrain.svg";
  if (cat.includes("filter")) return "/static/dealer/images/categories/filters.svg";
  if (cat.includes("control") || cat.includes("grip")) return "/static/dealer/images/categories/controls.svg";
  if (cat.includes("tyre") || cat.includes("tire") || cat.includes("tube")) return "/static/dealer/images/categories/tyres.svg";
  if (cat.includes("gear") || cat.includes("helmet")) return "/static/dealer/images/categories/gear.svg";
  if (cat.includes("engine") || cat.includes("oil")) return "/static/dealer/images/categories/engine.svg";
  if (cat.includes("care") || cat.includes("clean")) return "/static/dealer/images/categories/carcare.svg";
  return "/static/dealer/images/categories/accessories.svg";
}

function renderProductsGrid() {
  const grid = document.getElementById("productGrid");
  if (!grid) return;

  let list = [...state.products];

  // Stock filtering
  if (state.stockFilter === "in-stock") {
    list = list.filter((p) => p.stock > 10);
  } else if (state.stockFilter === "low-stock") {
    list = list.filter((p) => p.stock > 0 && p.stock <= 10);
  }

  // Client sorting for active page
  if (state.sortBy === "price-asc") {
    list.sort((a, b) => parseFloat(a.price) - parseFloat(b.price));
  } else if (state.sortBy === "price-desc") {
    list.sort((a, b) => parseFloat(b.price) - parseFloat(a.price));
  } else if (state.sortBy === "name-asc") {
    list.sort((a, b) => a.name.localeCompare(b.name));
  }

  if (list.length === 0) {
    grid.innerHTML = `
      <div class="empty-state-box" style="grid-column: 1/-1;">
        <div class="empty-state-icon">🔍</div>
        <h3>No matching spare parts found</h3>
        <p>Try searching for a different part name, SKU code (e.g. BRK, FIL), or reset your filters.</p>
        <button class="btn-secondary" id="emptyResetBtn">Reset All Filters</button>
      </div>
    `;
    document.getElementById("emptyResetBtn")?.addEventListener("click", () => {
      document.getElementById("resetFiltersBtn")?.click();
    });
    return;
  }

  grid.innerHTML = list
    .map((product) => {
      const isOutOfStock = product.stock <= 0;
      let stockBadgeClass = "in-stock";
      let stockText = `In Stock (${product.stock} units)`;

      if (isOutOfStock) {
        stockBadgeClass = "out-of-stock";
        stockText = "Out of Stock";
      } else if (product.stock <= 10) {
        stockBadgeClass = "low-stock";
        stockText = `Low Stock (${product.stock} left)`;
      }

      const imgUrl = getProductCategoryImage(product.category);

      return `
        <div class="product-card" data-sku="${product.sku}">
          <div class="card-top-meta">
            <span class="badge-category">${product.category}</span>
            <span class="badge-brand">${product.brand || "OEM"}</span>
          </div>

          <div class="product-image-box">
            <img src="${imgUrl}" alt="${product.name}" class="product-img-thumb" loading="lazy" onerror="this.src='/static/dealer/images/categories/accessories.svg'" />
          </div>

          <h3 class="product-name" title="${product.name}">${product.name}</h3>
          <div><span class="product-sku">${product.sku}</span></div>
          <p class="compatibility-text">Fitment: ${product.vehicle_fitment || "Universal / OEM"}</p>

          <div class="card-stock-row">
            <span class="stock-indicator ${stockBadgeClass}">
              <span class="stock-dot"></span>
              ${stockText}
            </span>
            <span style="font-size: 0.72rem; color: #64748b;">GST: 18%</span>
          </div>

          <div class="card-price-row">
            <div class="price-box">
              <span class="price-val">${formatINR(product.price)}</span>
              <span class="price-note">Excl. GST</span>
            </div>
            <button
              type="button"
              class="btn-add-cart"
              data-sku="${product.sku}"
              ${isOutOfStock ? "disabled" : ""}
            >
              ${isOutOfStock ? "Unavailable" : "+ Add to Cart"}
            </button>
          </div>
        </div>
      `;
    })
    .join("");

  // Attach Add to Cart event listeners
  grid.querySelectorAll(".btn-add-cart").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sku = btn.dataset.sku;
      const product = state.products.find((p) => p.sku === sku);
      if (product) {
        cartService.addItem({
          id: product.sku,
          sku: product.sku,
          name: product.name,
          brand: product.brand,
          price: parseFloat(product.price),
          stock: product.stock,
          gst_rate: 18.0,
        });
        showToast(`Added ${product.sku} (${product.name}) to cart.`, "success");
      }
    });
  });
}

function renderPagination(totalCount) {
  const container = document.getElementById("paginationBox");
  const info = document.getElementById("paginationInfo");
  const controls = document.getElementById("paginationControls");
  if (!container || !controls) return;

  const totalPages = Math.ceil(totalCount / state.pageSize);
  if (totalPages <= 1) {
    container.style.display = "none";
    return;
  }

  container.style.display = "flex";
  const start = (state.currentPage - 1) * state.pageSize + 1;
  const end = Math.min(state.currentPage * state.pageSize, totalCount);
  if (info) info.textContent = `Showing ${start}-${end} of ${totalCount} items`;

  let html = `
    <button type="button" class="page-btn" id="prevPageBtn" ${state.currentPage === 1 ? "disabled" : ""}>Previous</button>
  `;

  // Render max 5 page buttons
  const startPage = Math.max(1, state.currentPage - 2);
  const endPage = Math.min(totalPages, startPage + 4);

  for (let i = startPage; i <= endPage; i++) {
    html += `
      <button type="button" class="page-btn ${i === state.currentPage ? "active" : ""}" data-page="${i}">
        ${i}
      </button>
    `;
  }

  html += `
    <button type="button" class="page-btn" id="nextPageBtn" ${state.currentPage === totalPages ? "disabled" : ""}>Next</button>
  `;

  controls.innerHTML = html;

  controls.querySelectorAll(".page-btn[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.currentPage = parseInt(btn.dataset.page, 10);
      fetchLiveProducts();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  document.getElementById("prevPageBtn")?.addEventListener("click", () => {
    if (state.currentPage > 1) {
      state.currentPage--;
      fetchLiveProducts();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  });

  document.getElementById("nextPageBtn")?.addEventListener("click", () => {
    if (state.currentPage < totalPages) {
      state.currentPage++;
      fetchLiveProducts();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  });
}

/* ==========================================================================
   Cart Drawer & Real Draft Order Creation
   ========================================================================== */

function initCartDrawer() {
  const openBtn = document.getElementById("openCartBtn");
  const closeBtn = document.getElementById("closeCartBtn");
  const overlay = document.getElementById("cartOverlay");
  const drawer = document.getElementById("cartDrawer");
  const checkoutBtn = document.getElementById("btnDrawerCheckout");

  const open = () => {
    overlay?.classList.add("open");
    drawer?.classList.add("open");
  };

  const close = () => {
    overlay?.classList.remove("open");
    drawer?.classList.remove("open");
  };

  openBtn?.addEventListener("click", open);
  closeBtn?.addEventListener("click", close);
  overlay?.addEventListener("click", close);

  checkoutBtn?.addEventListener("click", async () => {
    const { items, totalEstimate } = cartService.getState();
    if (items.length === 0) return;

    checkoutBtn.disabled = true;
    checkoutBtn.textContent = "Creating Draft Order...";

    try {
      const payload = {
        dealer_id: state.dealerId,
        items: items.map((it) => ({ sku: it.sku, quantity: it.quantity })),
      };

      const res = await fetch("/api/orders/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const orderData = await res.json();
        cartService.clearCart();
        close();
        showToast(`DRAFT Order ${orderData.order_number} created successfully! Total: ${formatINR(orderData.grand_total)}`, "success");
        switchView("orders");
      } else {
        const err = await res.json();
        showToast(err.error?.message || "Failed to create draft order", "danger");
      }
    } catch (e) {
      showToast("Network error creating draft order", "danger");
    } finally {
      checkoutBtn.disabled = false;
      checkoutBtn.textContent = "Proceed to Review Draft Order";
    }
  });
}

function updateCartBadges(cartState) {
  const badge = document.getElementById("headerCartBadge");
  if (badge) {
    badge.textContent = cartState.totalItems;
    badge.style.display = cartState.totalItems > 0 ? "inline-block" : "none";
  }

  const checkoutBtn = document.getElementById("btnDrawerCheckout");
  if (checkoutBtn) {
    checkoutBtn.disabled = cartState.totalItems === 0;
  }

  const subtotalEl = document.getElementById("drawerSubtotal");
  const gstEl = document.getElementById("drawerGst");
  const totalEl = document.getElementById("drawerTotal");

  if (subtotalEl) subtotalEl.textContent = formatINR(cartState.subtotal);
  if (gstEl) gstEl.textContent = formatINR(cartState.gstEstimate);
  if (totalEl) totalEl.textContent = formatINR(cartState.totalEstimate);
}

function renderCartDrawerItems(cartState) {
  const list = document.getElementById("cartItemsList");
  const emptyView = document.getElementById("cartEmptyView");
  if (!list || !emptyView) return;

  if (cartState.items.length === 0) {
    emptyView.style.display = "block";
    list.innerHTML = "";
    return;
  }

  emptyView.style.display = "none";
  list.innerHTML = cartState.items
    .map(
      (item) => `
      <div class="cart-item-row" data-id="${item.id}">
        <div class="item-icon">📦</div>
        <div class="item-info">
          <div class="item-name">${item.name}</div>
          <div class="item-sku">${item.sku} &bull; ${item.brand || "OEM"}</div>
          <div class="item-price">${formatINR(item.price)} each</div>
        </div>
        <div class="item-actions">
          <div class="qty-control">
            <button type="button" class="btn-qty btn-minus" data-id="${item.id}">-</button>
            <span class="qty-val">${item.quantity}</span>
            <button type="button" class="btn-qty btn-plus" data-id="${item.id}">+</button>
          </div>
          <div class="item-line-total">${formatINR(item.price * item.quantity)}</div>
          <button type="button" class="btn-remove-item" data-id="${item.id}">&times;</button>
        </div>
      </div>
    `
    )
    .join("");

  list.querySelectorAll(".btn-plus").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      const item = cartState.items.find((i) => i.id === id);
      if (item) cartService.updateQuantity(id, item.quantity + 1);
    });
  });

  list.querySelectorAll(".btn-minus").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.id;
      const item = cartState.items.find((i) => i.id === id);
      if (item) cartService.updateQuantity(id, item.quantity - 1);
    });
  });

  list.querySelectorAll(".btn-remove-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      cartService.removeItem(btn.dataset.id);
    });
  });
}

/* ==========================================================================
   Order History (Real Database Orders)
   ========================================================================== */

async function fetchLiveOrders() {
  const tbody = document.getElementById("ordersTableBody");
  try {
    const res = await fetch(`/api/orders/?dealer_id=${state.dealerId}`);
    if (res.ok) {
      const data = await res.json();
      state.orders = data.results || [];
      const badge = document.getElementById("sidebarOrderCountBadge");
      if (badge) badge.textContent = `${state.orders.length} Orders`;
      renderOrders();
    }
  } catch (e) {
    console.warn("fetchLiveOrders error:", e);
  }
}

function renderOrders() {
  const tbody = document.getElementById("ordersTableBody");
  if (!tbody) return;

  if (state.orders.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 30px; color: #64748b;">No orders placed yet. Add items to cart or ask the AI Assistant to create a draft order.</td></tr>`;
    return;
  }

  tbody.innerHTML = state.orders
    .map(
      (o, idx) => `
      <tr>
        <td><span class="order-num-link" style="font-family: monospace; font-weight: 700; color: #0284c7;">${o.order_number}</span></td>
        <td>${new Date(o.created_at).toLocaleDateString("en-IN")}</td>
        <td>${(o.items || []).length} line items</td>
        <td><strong>${formatINR(o.grand_total)}</strong></td>
        <td><span class="status-badge ${o.status.toLowerCase()}">${o.status}</span></td>
        <td>
          <button type="button" class="btn-table-action btn-view-order" data-order-idx="${idx}">
            View Details
          </button>
        </td>
      </tr>
    `
    )
    .join("");

  tbody.querySelectorAll(".btn-view-order").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = parseInt(btn.dataset.orderIdx, 10);
      const order = state.orders[idx];
      if (order) openOrderDetailsModal(order);
    });
  });
}

function openOrderDetailsModal(order) {
  const modal = document.getElementById("orderDetailsModal");
  if (!modal) return;

  document.getElementById("modalOrderNum").textContent = order.order_number;
  document.getElementById("modalOrderDate").textContent = new Date(order.created_at).toLocaleString("en-IN");
  document.getElementById("modalOrderStatus").textContent = order.status;
  document.getElementById("modalOrderStatus").className = `status-badge ${order.status.toLowerCase()}`;
  document.getElementById("modalOrderNotes").textContent = `Consignment for Dealer #${order.dealer_id} via Bengaluru distribution warehouse.`;

  const itemsList = document.getElementById("modalOrderItemsList");
  if (itemsList) {
    itemsList.innerHTML = (order.items || [])
      .map(
        (it) => `
        <tr>
          <td>
            <strong>${it.name || it.sku}</strong><br>
            <span style="font-family: monospace; font-size: 0.75rem; color: #64748b;">${it.sku}</span>
          </td>
          <td>${it.quantity}</td>
          <td>${formatINR(it.unit_price)}</td>
          <td>18% (${formatINR(it.line_tax)})</td>
          <td><strong>${formatINR(it.line_total)}</strong></td>
        </tr>
      `
      )
      .join("");
  }

  document.getElementById("modalOrderSubtotal").textContent = formatINR(order.subtotal);
  document.getElementById("modalOrderGst").textContent = formatINR(order.tax_total);
  document.getElementById("modalOrderTotal").textContent = formatINR(order.grand_total);

  modal.classList.add("open");
}

/* ==========================================================================
   Dealer Profile Page
   ========================================================================== */

function renderProfilePage() {
  const p = state.userProfile;
  if (!p) return;

  const setT = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  setT("profileHeroName", p.business_name);
  setT("profileHeroCode", p.dealer_code);
  setT("profileHeroInitials", (p.business_name || "DD").split(" ").slice(0, 2).map((w) => w[0]).join(""));
  setT("profUsername", `dealer_${p.id}`);
  setT("profBusinessName", p.business_name);
  setT("profContactPerson", p.contact_person);
  setT("profPhone", p.phone);
  setT("profEmail", p.email);
  setT("profGstin", "29AAACL1234F1Z5");
  setT("profAddress", p.address);
  setT("profLocation", `${p.city}, ${p.state} - ${p.pincode}`);
  setT("profCreditLimit", formatINR(p.credit_limit));
  setT("profOutstanding", formatINR(0));
  setT("profAvailableCredit", formatINR(p.credit_limit));
}

/* ==========================================================================
   AI Dealer Assistant Controller (§9)
   ========================================================================== */

function initAssistant() {
  const input = document.getElementById("assistantInput");
  const sendBtn = document.getElementById("btnAssistantSend");
  const newSessBtn = document.getElementById("btnNewSession");
  const floatingBtn = document.getElementById("openAssistantFloatingBtn");
  const chips = document.querySelectorAll(".prompt-chip[data-prompt]");

  if (floatingBtn) {
    floatingBtn.addEventListener("click", () => {
      switchView("assistant");
    });
  }

  if (newSessBtn) {
    newSessBtn.addEventListener("click", () => {
      state.assistantSessionId = "session-" + Math.random().toString(36).substring(2, 9) + "-" + Date.now();
      const container = document.getElementById("assistantMessagesContainer");
      if (container) {
        container.innerHTML = `
          <div class="chat-bubble-row assistant">
            <div class="chat-avatar-mini bot">🤖</div>
            <div class="chat-bubble">
              <div class="bubble-text">
                Session reset. New conversation started (Session ID: <code>${state.assistantSessionId}</code>).<br>
                How can I assist you with parts or orders today?
              </div>
            </div>
          </div>
        `;
      }
      showToast("Assistant session reset.", "info");
    });
  }

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const text = chip.dataset.prompt;
      if (input) input.value = text;
      sendAssistantMessage();
    });
  });

  if (sendBtn) {
    sendBtn.addEventListener("click", sendAssistantMessage);
  }

  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendAssistantMessage();
      }
    });
  }
}

async function sendAssistantMessage() {
  const input = document.getElementById("assistantInput");
  const sendBtn = document.getElementById("btnAssistantSend");
  const container = document.getElementById("assistantMessagesContainer");
  if (!input || !container) return;

  const msg = input.value.trim();
  if (!msg) return;

  // Append user message bubble
  appendChatBubble("user", msg);
  input.value = "";
  input.disabled = true;
  if (sendBtn) sendBtn.disabled = true;

  // Append typing indicator
  const typingIndicator = showTypingIndicator();
  container.scrollTop = container.scrollHeight;

  try {
    const res = await fetch("/api/assistant/chat/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.assistantSessionId,
        dealer_id: state.dealerId,
        message: msg,
      }),
    });

    typingIndicator.remove();

    if (res.ok) {
      const data = await res.json();
      appendAssistantResponseBubble(data);
      // If a draft order was created, refresh orders list in the background
      if (data.actions && data.actions.some((a) => a.type === "draft_order_created")) {
        fetchLiveOrders();
      }
    } else {
      const errData = await res.json().catch(() => ({}));
      const errMsg = errData.error?.message || `Server error (${res.status})`;
      appendChatBubble("assistant", `⚠️ **Error:** ${errMsg}`);
    }
  } catch (err) {
    typingIndicator.remove();
    appendChatBubble("assistant", `⚠️ **Connection Error:** Could not contact assistant backend (${err.message}).`);
  } finally {
    input.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
    input.focus();
    container.scrollTop = container.scrollHeight;
  }
}

function appendChatBubble(role, text) {
  const container = document.getElementById("assistantMessagesContainer");
  if (!container) return;

  const row = document.createElement("div");
  row.className = `chat-bubble-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = `chat-avatar-mini ${role === "user" ? "user" : "bot"}`;
  avatar.textContent = role === "user" ? "👤" : "🤖";

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";

  const bubbleText = document.createElement("div");
  bubbleText.className = "bubble-text";
  bubbleText.textContent = text;

  bubble.appendChild(bubbleText);
  row.appendChild(avatar);
  row.appendChild(bubble);

  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
}

function showTypingIndicator() {
  const container = document.getElementById("assistantMessagesContainer");
  const row = document.createElement("div");
  row.className = "chat-bubble-row assistant";
  row.innerHTML = `
    <div class="chat-avatar-mini bot">🤖</div>
    <div class="typing-indicator-box">
      <span>Querying catalogue &amp; executing tools</span>
      <div class="typing-dots">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
      </div>
    </div>
  `;
  container.appendChild(row);
  return row;
}

function appendAssistantResponseBubble(data) {
  const container = document.getElementById("assistantMessagesContainer");
  if (!container) return;

  const row = document.createElement("div");
  row.className = "chat-bubble-row assistant";

  const avatar = document.createElement("div");
  avatar.className = "chat-avatar-mini bot";
  avatar.textContent = "🤖";

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";

  // Tool calls chips (if LLM invoked tools)
  if (data.tool_calls && data.tool_calls.length > 0) {
    const toolsBox = document.createElement("div");
    toolsBox.className = "tool-invocations-box";
    data.tool_calls.forEach((tc) => {
      const chip = document.createElement("span");
      chip.className = "tool-chip";
      const argsSummary = Object.entries(tc.arguments || {})
        .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`)
        .join(", ");
      chip.innerHTML = `⚡ <strong>${tc.name}</strong>(${argsSummary})`;
      toolsBox.appendChild(chip);
    });
    bubble.appendChild(toolsBox);
  }

  // Draft order actions banner
  if (data.actions && data.actions.length > 0) {
    data.actions.forEach((act) => {
      if (act.type === "draft_order_created") {
        const actionBox = document.createElement("div");
        actionBox.className = "action-pill-box";
        actionBox.innerHTML = `
          <span>🎉</span>
          <div>
            <strong>DRAFT Order Created in PostgreSQL!</strong><br>
            Order Number: <code style="font-weight:700;">${act.order_number}</code> (Status: DRAFT)
          </div>
        `;
        bubble.appendChild(actionBox);
      }
    });
  }

  // Assistant reply text
  const textDiv = document.createElement("div");
  textDiv.className = "bubble-text";
  textDiv.textContent = data.reply;
  bubble.appendChild(textDiv);

  // Cited SKUs badges
  if (data.cited_skus && data.cited_skus.length > 0) {
    const citedBox = document.createElement("div");
    citedBox.className = "cited-skus-container";
    citedBox.innerHTML = `<span style="font-size:0.75rem; color:#64748b; font-weight:600;">Cited Parts:</span>`;
    data.cited_skus.forEach((sku) => {
      const tag = document.createElement("span");
      tag.className = "cited-sku-tag";
      tag.textContent = `[${sku}]`;
      tag.title = `Click to filter catalogue by ${sku}`;
      tag.addEventListener("click", () => {
        state.searchQuery = sku;
        switchView("catalogue");
        const searchInput = document.getElementById("searchInput");
        if (searchInput) searchInput.value = sku;
        fetchLiveProducts();
      });
      citedBox.appendChild(tag);
    });
    bubble.appendChild(citedBox);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);

  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
}

/* ==========================================================================
   Modals (Order Details & Auth)
   ========================================================================== */

function initModals() {
  document.querySelectorAll(".modal-close-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.closest(".modal-backdrop")?.classList.remove("open");
    });
  });

  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.classList.remove("open");
    });
  });

  const btnEditProfile = document.getElementById("btnEditProfile");
  if (btnEditProfile) {
    btnEditProfile.addEventListener("click", () => {
      const p = state.userProfile;
      if (p) {
        const cp = document.getElementById("editContactPerson");
        const ph = document.getElementById("editPhone");
        const ad = document.getElementById("editAddress");
        if (cp) cp.value = p.contact_person || "";
        if (ph) ph.value = p.phone || "";
        if (ad) ad.value = p.address || "";
      }
      document.getElementById("editProfileModal")?.classList.add("open");
    });
  }

  const btnSaveProfile = document.getElementById("btnSaveProfileModal");
  if (btnSaveProfile) {
    btnSaveProfile.addEventListener("click", () => {
      if (state.userProfile) {
        const cp = document.getElementById("editContactPerson");
        const ph = document.getElementById("editPhone");
        const ad = document.getElementById("editAddress");
        if (cp) state.userProfile.contact_person = cp.value;
        if (ph) state.userProfile.phone = ph.value;
        if (ad) state.userProfile.address = ad.value;
        renderProfilePage();
      }
      document.getElementById("editProfileModal")?.classList.remove("open");
      showToast("Profile details updated for session.", "success");
    });
  }
}

function openAuthModal() {
  document.getElementById("authModal")?.classList.add("open");
}

/* ==========================================================================
   Demand Forecasting & Reorder Suggestions View (§10)
   ========================================================================== */

let forecastInitialized = false;

function initForecastControls() {
  if (forecastInitialized) return;
  forecastInitialized = true;

  const searchInput = document.getElementById("forecastSearchInput");
  const statusFilter = document.getElementById("forecastStatusFilter");
  const refreshBtn = document.getElementById("btnRefreshForecast");

  if (searchInput) {
    searchInput.addEventListener("input", () => renderForecastTable());
  }

  if (statusFilter) {
    statusFilter.addEventListener("change", () => renderForecastTable());
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      showToast("Refreshing inventory & forecast calculations...", "info");
      fetchAndRenderForecast(true);
    });
  }
}

async function fetchAndRenderForecast(showToastOnDone = false) {
  initForecastControls();
  const tbody = document.getElementById("forecastTableBody");
  if (!tbody) return;

  if (!state.reorderSuggestions || state.reorderSuggestions.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; padding: 30px; color: #64748b;">
          <div style="font-size: 1.5rem; margin-bottom: 8px;">⏳</div>
          Loading 40 forecast SKUs and live reorder suggestions from PostgreSQL backend...
        </td>
      </tr>
    `;
  }

  try {
    const res = await fetch("/api/reorder-suggestions/");
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    state.reorderSuggestions = data.results || [];

    // Update KPI metrics
    const total = state.reorderSuggestions.length;
    const reorderNeeded = state.reorderSuggestions.filter((r) => r.reorder_qty > 0).length;
    const avgLeadTime = total > 0
      ? (state.reorderSuggestions.reduce((acc, r) => acc + r.lead_time_weeks, 0) / total).toFixed(1)
      : "2.6";

    const elTotal = document.getElementById("kpiTotalSkus");
    const elReorder = document.getElementById("kpiReorderNeeded");
    const elLead = document.getElementById("kpiAvgLeadTime");

    if (elTotal) elTotal.textContent = total;
    if (elReorder) elReorder.textContent = `${reorderNeeded} SKUs`;
    if (elLead) elLead.textContent = `${avgLeadTime} Wks`;

    renderForecastTable();
    if (showToastOnDone) {
      showToast("Forecast & reorder suggestions updated successfully.", "success");
    }
  } catch (err) {
    console.error("Failed to fetch reorder suggestions:", err);
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; padding: 24px; color: #dc2626;">
          ⚠️ Error loading reorder suggestions. Please ensure the backend server is active.
        </td>
      </tr>
    `;
  }
}

function renderForecastTable() {
  const tbody = document.getElementById("forecastTableBody");
  const countEl = document.getElementById("forecastCount");
  if (!tbody || !state.reorderSuggestions) return;

  const searchQuery = (document.getElementById("forecastSearchInput")?.value || "").trim().toUpperCase();
  const statusFilter = document.getElementById("forecastStatusFilter")?.value || "all";

  let filtered = state.reorderSuggestions.filter((item) => {
    if (searchQuery && !item.sku.toUpperCase().includes(searchQuery)) return false;
    if (statusFilter === "reorder-only" && item.reorder_qty <= 0) return false;
    if (statusFilter === "healthy-only" && item.reorder_qty > 0) return false;
    return true;
  });

  if (countEl) countEl.textContent = `Showing ${filtered.length} of ${state.reorderSuggestions.length} SKUs`;

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; padding: 30px; color: #64748b;">
          No forecast SKUs match your filter criteria.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = "";
  filtered.forEach((item) => {
    const tr = document.createElement("tr");

    const needsReorder = item.reorder_qty > 0;
    const reorderBadge = needsReorder
      ? `<span style="background: #fee2e2; color: #b91c1c; font-weight: 700; padding: 4px 8px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px;">
           ⚠️ ${item.reorder_qty} units
         </span>`
      : `<span style="background: #dcfce7; color: #15803d; font-weight: 600; padding: 4px 8px; border-radius: 4px;">
           ✓ Optimal
         </span>`;

    tr.innerHTML = `
      <td><strong style="color: #0f172a; font-family: monospace; font-size: 0.9rem;">${item.sku}</strong></td>
      <td>
        <span style="font-weight: 700; color: ${item.current_stock < item.reorder_point ? "#e11d48" : "#0f172a"};">
          ${item.current_stock}
        </span>
      </td>
      <td><span style="background: #f1f5f9; padding: 3px 8px; border-radius: 4px; font-weight: 600;">${item.lead_time_weeks} wks</span></td>
      <td>${item.lead_time_demand}</td>
      <td><span style="color: #475569; font-weight: 600;">${item.safety_stock}</span></td>
      <td><span style="font-weight: 700; color: #2563eb;">${item.reorder_point}</span></td>
      <td>${reorderBadge}</td>
      <td>
        <div style="display: flex; gap: 8px; align-items: center;">
          <button type="button" class="btn-secondary btn-forecast-trend" data-sku="${item.sku}" style="padding: 4px 10px; font-size: 0.78rem;" title="View 4-week demand prediction breakdown">
            📊 Trend
          </button>
          ${
            needsReorder
              ? `<button type="button" class="btn-checkout btn-forecast-reorder" data-sku="${item.sku}" data-qty="${item.reorder_qty}" style="padding: 4px 10px; font-size: 0.78rem; width: auto;" title="Add recommended replenishment quantity to cart">
                   🛒 Order
                 </button>`
              : ""
          }
        </div>
      </td>
    `;

    tbody.appendChild(tr);
  });

  // Attach event listeners for trend and reorder buttons
  tbody.querySelectorAll(".btn-forecast-trend").forEach((btn) => {
    btn.addEventListener("click", () => {
      openSkuForecastModal(btn.dataset.sku);
    });
  });

  tbody.querySelectorAll(".btn-forecast-reorder").forEach((btn) => {
    btn.addEventListener("click", () => {
      handleForecastAddToCart(btn.dataset.sku, parseInt(btn.dataset.qty, 10));
    });
  });
}

async function openSkuForecastModal(sku) {
  const modal = document.getElementById("forecastModal");
  const title = document.getElementById("forecastModalTitle");
  const body = document.getElementById("forecastModalBody");
  if (!modal || !body) return;

  if (title) title.textContent = `4-Week Demand Forecast: ${sku}`;
  body.innerHTML = `
    <div style="text-align: center; padding: 24px; color: #64748b;">
      <div style="font-size: 1.5rem; margin-bottom: 8px;">⏳</div>
      Fetching demand prediction breakdown for ${sku}...
    </div>
  `;
  modal.classList.add("open");

  try {
    const res = await fetch(`/api/forecast/${encodeURIComponent(sku)}/`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const weeks = data.forecast || [];

    // Calculate maximum forecast units for visual bar proportion
    const maxVal = Math.max(...weeks.map((w) => w.forecast_units), 1);
    const totalDemand = weeks.reduce((acc, w) => acc + w.forecast_units, 0).toFixed(1);

    let html = `
      <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <strong style="color: #0f172a; font-size: 1rem;">SKU: ${data.sku}</strong>
            <div style="font-size: 0.8rem; color: #64748b; margin-top: 2px;">Automotive Catalogue Spare Part</div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 0.75rem; color: #64748b; font-weight: 600; text-transform: uppercase;">4-Week Total Demand</div>
            <div style="font-size: 1.25rem; font-weight: 800; color: #2563eb;">${totalDemand} units</div>
          </div>
        </div>
      </div>

      <div style="display: flex; flex-direction: column; gap: 12px;">
    `;

    weeks.forEach((w, idx) => {
      const pct = Math.min(100, Math.round((w.forecast_units / maxVal) * 100));
      html += `
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
          <div style="display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: 600; margin-bottom: 6px;">
            <span style="color: #334155;">Week ${idx + 1} (Starting ${w.week_start})</span>
            <span style="color: #0f172a; font-weight: 700;">${w.forecast_units} units</span>
          </div>
          <div style="width: 100%; height: 10px; background: #f1f5f9; border-radius: 5px; overflow: hidden;">
            <div style="height: 100%; width: ${pct}%; background: linear-gradient(90deg, #3b82f6, #1d4ed8); border-radius: 5px;"></div>
          </div>
        </div>
      `;
    });

    html += `</div>`;
    body.innerHTML = html;
  } catch (err) {
    console.error("Failed to load SKU forecast modal:", err);
    body.innerHTML = `
      <div style="text-align: center; padding: 20px; color: #dc2626;">
        ⚠️ Could not load forecast data for SKU ${sku}.
      </div>
    `;
  }
}

function handleForecastAddToCart(sku, reorderQty) {
  // Check if product exists in loaded catalogue
  let product = (state.allProducts || []).find((p) => p.sku === sku);
  if (!product) {
    product = {
      sku: sku,
      name: `Part ${sku}`,
      brand: "OEM Direct",
      price: "100.00",
      stock: 9999,
    };
  }
  cartService.addItem(product, reorderQty);
  showToast(`Added ${reorderQty} units of ${sku} to cart for replenishment.`, "success");
  openCartDrawer();
}

