/**
 * DealerDesk - Client-Side Cart Service
 * Manages shopping cart state, line items, quantity adjustments,
 * and frontend GST previews.
 */

const STORAGE_KEY = "dealerdesk_dealer_cart";

class CartService {
  constructor() {
    this.items = this.loadCart();
    this.listeners = [];
  }

  loadCart() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      console.warn("Could not read cart from localStorage:", e);
      return [];
    }
  }

  saveCart() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.items));
    } catch (e) {
      console.warn("Could not save cart to localStorage:", e);
    }
    this.notify();
  }

  subscribe(listener) {
    this.listeners.push(listener);
    listener(this.getState());
  }

  notify() {
    const state = this.getState();
    this.listeners.forEach((fn) => fn(state));
  }

  addItem(product, quantity = 1) {
    if (!product || product.stock <= 0) return false;

    const existingIndex = this.items.findIndex((item) => item.id === product.id);
    if (existingIndex > -1) {
      const newQty = this.items[existingIndex].quantity + quantity;
      this.items[existingIndex].quantity = Math.min(newQty, product.stock);
    } else {
      this.items.push({
        id: product.id,
        sku: product.sku,
        name: product.name,
        brand: product.brand,
        price: product.price,
        stock: product.stock,
        gst_rate: product.gst_rate || 18.0,
        quantity: Math.min(quantity, product.stock),
        icon: product.icon || "📦",
      });
    }
    this.saveCart();
    return true;
  }

  updateQuantity(productId, newQty) {
    const item = this.items.find((i) => i.id === productId);
    if (!item) return;

    if (newQty <= 0) {
      this.removeItem(productId);
      return;
    }

    item.quantity = Math.min(newQty, item.stock);
    this.saveCart();
  }

  removeItem(productId) {
    this.items = this.items.filter((i) => i.id !== productId);
    this.saveCart();
  }

  clearCart() {
    this.items = [];
    this.saveCart();
  }

  getState() {
    const totalItems = this.items.reduce((sum, item) => sum + item.quantity, 0);
    const subtotal = this.items.reduce(
      (sum, item) => sum + item.price * item.quantity,
      0
    );

    // Indicative GST preview calculation based on line GST rates
    const gstEstimate = this.items.reduce((sum, item) => {
      const lineSubtotal = item.price * item.quantity;
      return sum + (lineSubtotal * (item.gst_rate || 18.0)) / 100;
    }, 0);

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

export const cartService = new CartService();
