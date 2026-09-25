import axios, { AxiosInstance, AxiosRequestConfig } from "axios";

const baseURL =
  (import.meta.env.VITE_API_URL as string | undefined) || "/api/v1";

export const TOKEN_KEY = "vogel.token";
export const REFRESH_KEY = "vogel.refresh";
export const ACTIVE_COMPANY_KEY = "vogel.activeCompany";
export const THEME_KEY = "vogel.theme";

export const api: AxiosInstance = axios.create({ baseURL });

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && onUnauthorized) {
      onUnauthorized();
    }
    return Promise.reject(error);
  }
);

export async function apiGet<T>(path: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await api.get<T>(path, config);
  return res.data;
}

export async function apiPost<T>(path: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await api.post<T>(path, body, config);
  return res.data;
}

export async function apiPatch<T>(path: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await api.patch<T>(path, body, config);
  return res.data;
}

export function setToken(token: string | null, refresh?: string | null) {
  if (token === null) {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    return;
  }
  localStorage.setItem(TOKEN_KEY, token);
  if (refresh) {
    localStorage.setItem(REFRESH_KEY, refresh);
  }
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(ACTIVE_COMPANY_KEY);
}