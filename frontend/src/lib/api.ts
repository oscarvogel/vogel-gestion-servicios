import axios, { AxiosInstance, AxiosRequestConfig } from "axios";

const baseURL =
  (import.meta.env.VITE_API_URL as string | undefined) || "/api/v1";

export const TOKEN_KEY = "vogel.token";
export const REFRESH_KEY = "vogel.refresh";
export const ACTIVE_COMPANY_KEY = "vogel.activeCompany";
export const THEME_KEY = "vogel.theme";

export const api: AxiosInstance = axios.create({ baseURL });

let onUnauthorized: (() => void) | null = null;
let refreshInFlight: Promise<string> | null = null;

interface RetryableRequestConfig extends AxiosRequestConfig {
  _authRetry?: boolean;
}

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

function notifyUnauthorized() {
  clearSession();
  onUnauthorized?.();
}

export async function refreshAccessToken(): Promise<string> {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) {
    throw new Error("No refresh token available");
  }
  if (!refreshInFlight) {
    refreshInFlight = axios
      .post<{ access_token: string }>(
        `${baseURL}/auth/refresh`,
        { refresh_token: refreshToken },
      )
      .then(async ({ data }) => {
        let accessToken = data.access_token;
        const rawCompany = localStorage.getItem(ACTIVE_COMPANY_KEY);
        if (rawCompany) {
          try {
            const company = JSON.parse(rawCompany) as { id?: number };
            if (company.id) {
              const selected = await axios.post<{ access_token: string }>(
                `${baseURL}/auth/select-company`,
                { company_id: company.id },
                { headers: { Authorization: `Bearer ${accessToken}` } },
              );
              accessToken = selected.data.access_token;
            }
          } catch (_) {
            localStorage.removeItem(ACTIVE_COMPANY_KEY);
          }
        }
        setToken(accessToken);
        return accessToken;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
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
  async (error) => {
    const status = error?.response?.status;
    const config = error?.config as RetryableRequestConfig | undefined;
    const isRefreshRequest = config?.url?.endsWith("/auth/refresh");

    if (status === 401 && !isRefreshRequest && config && !config._authRetry) {
      config._authRetry = true;
      try {
        const accessToken = await refreshAccessToken();
        config.headers = config.headers ?? {};
        config.headers.Authorization = `Bearer ${accessToken}`;
        return api(config);
      } catch (_) {
        notifyUnauthorized();
      }
    } else if (status === 401) {
      notifyUnauthorized();
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

export async function apiPut<T>(path: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await api.put<T>(path, body, config);
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


const API_ERROR_MESSAGES: Record<number, string> = {
  401: "La sesión venció. Ingresá nuevamente.",
  403: "No tenés permisos para realizar esta acción.",
  404: "No se encontró el recurso solicitado.",
  409: "La operación entra en conflicto con datos existentes.",
  422: "Revisá los datos ingresados.",
  500: "Ocurrió un error interno. Intentá nuevamente.",
};

export function getApiErrorMessage(error: unknown, fallback = "No se pudo completar la operación"): string {
  const response = (error as {
    response?: { status?: number; data?: { detail?: unknown } };
  })?.response;
  const detail = response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length) {
    return "Revisá los datos ingresados.";
  }
  return (response?.status && API_ERROR_MESSAGES[response.status]) || fallback;
}
