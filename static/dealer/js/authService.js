/**
 * DealerDesk - Authentication Service
 * Manages JWT tokens, backend authentication calls, and user profile resolution.
 */

import { MOCK_DEALER_PROFILE } from "./mockData.js";

const ACCESS_TOKEN_KEY = "dealerdesk_access_token";
const REFRESH_TOKEN_KEY = "dealerdesk_refresh_token";
const USER_KEY = "dealerdesk_current_user";

class AuthService {
  getAccessToken() {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  getRefreshToken() {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  }

  setSession(tokens, user) {
    if (tokens?.access) localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
    if (tokens?.refresh) localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  clearSession() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  isLoggedIn() {
    return Boolean(this.getAccessToken());
  }

  async login(username, password) {
    try {
      const response = await fetch("/api/auth/login/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.non_field_errors?.[0] || "Login failed");
      }

      this.setSession(data.tokens, data.user);
      return { success: true, user: data.user };
    } catch (err) {
      return { success: false, error: err.message };
    }
  }

  async fetchCurrentUser() {
    const token = this.getAccessToken();
    if (!token) return null;

    try {
      const response = await fetch("/api/auth/me/", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        this.clearSession();
        return null;
      }

      const user = await response.json();
      localStorage.setItem(USER_KEY, JSON.stringify(user));
      return user;
    } catch (e) {
      console.warn("Failed to fetch authenticated user from API:", e);
      return null;
    }
  }

  getProfile() {
    // If authenticated user with dealer profile exists in session, use it;
    // otherwise fallback gracefully to mock dealer data for testing/demo.
    try {
      const cached = localStorage.getItem(USER_KEY);
      if (cached) {
        const u = JSON.parse(cached);
        if (u.dealer_profile) {
          return {
            id: u.dealer_profile.id || u.id,
            dealer_code: u.dealer_profile.dealer_code || `DLR-KA-${u.id}`,
            business_name: u.dealer_profile.business_name || u.username,
            username: u.username,
            contact_person: u.dealer_profile.contact_person || u.username,
            phone: u.dealer_profile.phone || "+91 98450 12345",
            email: u.email,
            gstin: u.dealer_profile.gstin || "29AAACL1234F1Z5",
            address: u.dealer_profile.address || "Bengaluru Distribution Area",
            city: u.dealer_profile.city || "Bengaluru",
            state: u.dealer_profile.state || "Karnataka",
            pincode: u.dealer_profile.pincode || "560058",
            credit_limit: parseFloat(u.dealer_profile.credit_limit || 500000),
            outstanding_balance: parseFloat(u.dealer_profile.outstanding_balance || 0),
            available_credit:
              parseFloat(u.dealer_profile.credit_limit || 500000) -
              parseFloat(u.dealer_profile.outstanding_balance || 0),
            is_live_auth: true,
          };
        }
      }
    } catch (e) {
      console.warn("Error parsing cached profile:", e);
    }

    return { ...MOCK_DEALER_PROFILE, is_live_auth: false };
  }
}

export const authService = new AuthService();
