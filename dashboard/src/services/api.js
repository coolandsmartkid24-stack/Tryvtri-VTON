/**
 * TryVtri Admin Dashboard API Client
 */

const TOKEN_KEY = 'tryvtri_admin_token';
const USERNAME_KEY = 'tryvtri_admin_user';

let onUnauthorizedCb = null;
export function setOnUnauthorized(cb) {
  onUnauthorizedCb = cb;
}

export const auth = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  getUser: () => localStorage.getItem(USERNAME_KEY),
  setSession: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USERNAME_KEY, user);
  },
  clearSession: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
  },
  isAuthenticated: () => !!localStorage.getItem(TOKEN_KEY),
};

async function fetchWithAuth(url, options = {}) {
  const token = auth.getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    auth.clearSession();
    if (onUnauthorizedCb) {
      onUnauthorizedCb();
    }
    throw new Error('Session expired. Please sign in again.');
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.message || data.detail || `Request failed with status ${response.status}`);
  }
  return data;
}

export const api = {
  login: async (username, password) => {
    const res = await fetch('/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.message || data.detail || 'Login failed');
    }
    auth.setSession(data.access_token, data.username);
    return data;
  },

  getDashboard: (windowHours = 24) => fetchWithAuth(`/admin/dashboard?window_hours=${windowHours}`),

  getCustomers: (limit = 50, offset = 0, search = '', windowHours = 24) => {
    let q = `/admin/customers?limit=${limit}&offset=${offset}&window_hours=${windowHours}`;
    if (search) q += `&search=${encodeURIComponent(search)}`;
    return fetchWithAuth(q);
  },

  getUsage: (days = 30) => fetchWithAuth(`/admin/usage?days=${days}`),

  getGpuStatus: () => fetchWithAuth('/gpu/status'),

  startGpu: () => fetchWithAuth('/admin/gpu/start', { method: 'POST' }),

  stopGpu: () => fetchWithAuth('/admin/gpu/stop', { method: 'POST' }),
};
