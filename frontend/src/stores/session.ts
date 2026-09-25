import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  apiGet,
  apiPost,
  setToken,
  TOKEN_KEY,
  REFRESH_KEY,
  ACTIVE_COMPANY_KEY,
  clearSession,
} from "../lib/api";

export type AuthStatus = "initializing" | "authenticated" | "anonymous";

export interface MembershipSummary {
  company_id: number;
  company_name: string;
  company_slug: string | null;
  company_active: boolean;
  is_admin: boolean;
  role: string;
  active: boolean;
}

export interface MeResponse {
  id: number;
  email: string;
  full_name: string;
  is_superadmin: boolean;
  active: boolean;
  memberships: MembershipSummary[];
  permissions: string[];
}

export interface CompanyOption {
  id: number;
  name: string;
  slug: string | null;
  active: boolean;
  is_admin: boolean;
}

export type PostLoginDestination =
  | "dashboard"
  | "company-selector"
  | "no-companies"
  | "select-company";

export function resolvePostLoginDestination(
  user: MeResponse | null,
  company: CompanyOption | null,
): PostLoginDestination {
  if (!user || user.is_superadmin || company) return "dashboard";
  if (user.memberships.length === 0) return "no-companies";
  if (user.memberships.length === 1) return "select-company";
  return "company-selector";
}

export const useSessionStore = defineStore("session", () => {
  const me = ref<MeResponse | null>(null);
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY));
  const activeCompany = ref<CompanyOption | null>(
    (() => {
      try {
        const raw = localStorage.getItem(ACTIVE_COMPANY_KEY);
        return raw ? (JSON.parse(raw) as CompanyOption) : null;
      } catch (_) {
        return null;
      }
    })()
  );
  const loading = ref(false);
  const authStatus = ref<AuthStatus>("initializing");
  let bootstrapPromise: Promise<void> | null = null;

  const isAuthenticated = computed(
    () => authStatus.value === "authenticated" && !!me.value
  );
  const isSuperAdmin = computed(() => me.value?.is_superadmin === true);
  const permissions = computed(() => me.value?.permissions ?? []);
  const memberships = computed(() => me.value?.memberships ?? []);

  function hasPermission(code: string): boolean {
    if (!me.value) return false;
    if (me.value.is_superadmin) return true;
    return me.value.permissions.includes(code);
  }

  function persistActiveCompany(company: CompanyOption | null) {
    activeCompany.value = company;
    if (company) {
      localStorage.setItem(ACTIVE_COMPANY_KEY, JSON.stringify(company));
    } else {
      localStorage.removeItem(ACTIVE_COMPANY_KEY);
    }
  }

  async function login(email: string, password: string) {
    loading.value = true;
    authStatus.value = "initializing";
    try {
      const response = await apiPost<{
        access_token: string;
        refresh_token: string;
        token_type: string;
      }>("/auth/login", { email, password });
      setToken(response.access_token, response.refresh_token);
      token.value = response.access_token;
      await loadMe();
      authStatus.value = "authenticated";
    } catch (error) {
      await logout();
      throw error;
    } finally {
      loading.value = false;
    }
  }

  async function loadMe() {
    token.value = localStorage.getItem(TOKEN_KEY);
    if (!token.value) throw new Error("No access token available");
    const data = await apiGet<MeResponse>("/auth/me");
    token.value = localStorage.getItem(TOKEN_KEY);
    me.value = data;
    // Si ya hay empresa activa pero no es válida para este usuario, limpiar.
    if (activeCompany.value) {
      const valid = data.memberships.some(
        (m) => m.company_id === activeCompany.value!.id && m.active
      );
      if (!valid && !data.is_superadmin) {
        persistActiveCompany(null);
      } else if (data.is_superadmin) {
        // SuperAdmin puede mantener el contexto o salir; respetamos lo que tenga.
      }
    }
  }

  async function refresh() {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) return false;
    try {
      const response = await apiPost<{
        access_token: string;
        token_type: string;
      }>("/auth/refresh", { refresh_token: refreshToken });
      setToken(response.access_token);
      token.value = response.access_token;
      return true;
    } catch (_) {
      return false;
    }
  }

  async function logout() {
    clearSession();
    token.value = null;
    me.value = null;
    activeCompany.value = null;
    authStatus.value = "anonymous";
  }

  async function bootstrap() {
    if (bootstrapPromise) return bootstrapPromise;
    if (authStatus.value === "authenticated" && me.value && token.value) {
      return;
    }

    bootstrapPromise = (async () => {
      authStatus.value = "initializing";
      token.value = localStorage.getItem(TOKEN_KEY);
      if (!token.value) {
        me.value = null;
        activeCompany.value = null;
        clearSession();
        authStatus.value = "anonymous";
        return;
      }

      try {
        await loadMe();
        authStatus.value = "authenticated";
        return;
      } catch (_) {
        // Access may be expired. Try the persisted refresh token exactly once.
      }

      if (await refresh()) {
        try {
          await loadMe();
          authStatus.value = "authenticated";
          return;
        } catch (_) {
          // The refreshed access token is not a valid session either.
        }
      }

      await logout();
    })().finally(() => {
      bootstrapPromise = null;
    });

    return bootstrapPromise;
  }

  async function selectCompany(company: CompanyOption) {
    const response = await apiPost<{ access_token: string; token_type: string }>(
      "/auth/select-company",
      { company_id: company.id }
    );
    setToken(response.access_token);
    token.value = response.access_token;
    persistActiveCompany(company);
    await loadMe();
  }

  async function leaveCompany() {
    const response = await apiPost<{ access_token: string; token_type: string }>(
      "/auth/leave-company"
    );
    setToken(response.access_token);
    token.value = response.access_token;
    persistActiveCompany(null);
    await loadMe();
  }

  async function loadCompanies(): Promise<CompanyOption[]> {
    return apiGet<CompanyOption[]>("/auth/companies");
  }

  return {
    me,
    token,
    activeCompany,
    loading,
    authStatus,
    isAuthenticated,
    isSuperAdmin,
    permissions,
    memberships,
    hasPermission,
    login,
    logout,
    bootstrap,
    refresh,
    loadMe,
    selectCompany,
    leaveCompany,
    loadCompanies,
    persistActiveCompany,
  };
});
