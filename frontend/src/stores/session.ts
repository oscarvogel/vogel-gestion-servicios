import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  apiGet,
  apiPost,
  setToken,
  TOKEN_KEY,
  ACTIVE_COMPANY_KEY,
  clearSession,
} from "../lib/api";

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

  const isAuthenticated = computed(() => !!token.value && !!me.value);
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
    try {
      const response = await apiPost<{
        access_token: string;
        refresh_token: string;
        token_type: string;
      }>("/auth/login", { email, password });
      setToken(response.access_token, response.refresh_token);
      token.value = response.access_token;
      await loadMe();
    } finally {
      loading.value = false;
    }
  }

  async function loadMe() {
    if (!token.value) return;
    const data = await apiGet<MeResponse>("/auth/me");
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
    const refreshToken = localStorage.getItem("vogel.refresh");
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
    setToken(null);
    token.value = null;
    me.value = null;
    persistActiveCompany(null);
    clearSession();
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
    isAuthenticated,
    isSuperAdmin,
    permissions,
    memberships,
    hasPermission,
    login,
    logout,
    refresh,
    loadMe,
    selectCompany,
    leaveCompany,
    loadCompanies,
    persistActiveCompany,
  };
});