import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import axios from "axios";
import {
  resolvePostLoginDestination,
  useSessionStore,
  type MeResponse,
} from "../stores/session";
import { createAppRouter } from "../router";
import * as apiModule from "../lib/api";
import DashboardView from "../views/DashboardView.vue";
import { mount } from "@vue/test-utils";

const superAdmin: MeResponse = {
  id: 1,
  email: "superadmin@vogel.local",
  full_name: "SuperAdmin Vogel",
  is_superadmin: true,
  active: true,
  memberships: [],
  permissions: [],
};

const normalUser: MeResponse = {
  id: 2,
  email: "admin@vogel.local",
  full_name: "Admin Vogel",
  is_superadmin: false,
  active: true,
  memberships: [
    {
      company_id: 10,
      company_name: "Empresa Uno",
      company_slug: "empresa-uno",
      company_active: true,
      is_admin: true,
      role: "ADMIN",
      active: true,
    },
  ],
  permissions: ["users.view", "users.create", "roles.view"],
};

function rejected401() {
  return Promise.reject({ response: { status: 401 } });
}

describe("authentication bootstrap and route guards", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.restoreAllMocks();
  });

  it("starts anonymous when no credentials exist", async () => {
    const session = useSessionStore();

    await session.bootstrap();

    expect(session.authStatus).toBe("anonymous");
    expect(session.isAuthenticated).toBe(false);
  });

  it("clears an invalid access and failed refresh token", async () => {
    localStorage.setItem(apiModule.TOKEN_KEY, "invalid-access");
    localStorage.setItem(apiModule.REFRESH_KEY, "invalid-refresh");
    vi.spyOn(apiModule, "apiGet").mockImplementation(() => rejected401());
    vi.spyOn(apiModule, "apiPost").mockImplementation(() => rejected401());
    const session = useSessionStore();

    await session.bootstrap();

    expect(session.authStatus).toBe("anonymous");
    expect(session.isAuthenticated).toBe(false);
    expect(localStorage.getItem(apiModule.TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(apiModule.REFRESH_KEY)).toBeNull();
  });

  it("redirects anonymous users from every private route to login", async () => {
    const router = createAppRouter();

    for (const path of ["/", "/dashboard", "/empresas", "/usuarios", "/roles", "/app/dashboard"]) {
      await router.push(path);
      expect(router.currentRoute.value.name).toBe("login");
    }
  });

  it("does not allow an authenticated user to remain on login", async () => {
    const session = useSessionStore();
    session.$patch({
      me: superAdmin,
      token: "valid-access",
      authStatus: "authenticated",
    });
    const router = createAppRouter();

    await router.push("/login");

    expect(router.currentRoute.value.name).toBe("post-login");
  });

  it("allows SuperAdmin into the platform and denies company-only routes without logging out", async () => {
    const session = useSessionStore();
    session.$patch({
      me: superAdmin,
      token: "valid-access",
      authStatus: "authenticated",
    });
    const router = createAppRouter();

    await router.push("/app/dashboard");
    expect(router.currentRoute.value.name).toBe("dashboard");
    await router.push("/empresas");
    expect(router.currentRoute.value.name).toBe("companies");
    expect(session.isAuthenticated).toBe(true);
  });

  it("resolves platform, one-company, multiple-company and no-company destinations", () => {
    expect(resolvePostLoginDestination(superAdmin, null)).toBe("dashboard");
    expect(resolvePostLoginDestination(normalUser, null)).toBe("select-company");
    expect(
      resolvePostLoginDestination(
        { ...normalUser, memberships: [...normalUser.memberships, { ...normalUser.memberships[0], company_id: 11, company_name: "Empresa Dos" }] },
        null,
      ),
    ).toBe("company-selector");
    expect(resolvePostLoginDestination({ ...normalUser, memberships: [] }, null)).toBe("no-companies");
  });

  it("clears all session state on logout", async () => {
    const session = useSessionStore();
    localStorage.setItem(apiModule.TOKEN_KEY, "access");
    localStorage.setItem(apiModule.REFRESH_KEY, "refresh");
    localStorage.setItem(apiModule.ACTIVE_COMPANY_KEY, JSON.stringify({ id: 10 }));
    session.$patch({ me: normalUser, token: "access", authStatus: "authenticated" });
    session.persistActiveCompany({
      id: 10,
      name: "Empresa Uno",
      slug: "empresa-uno",
      active: true,
      is_admin: true,
    });

    await session.logout();

    expect(session.authStatus).toBe("anonymous");
    expect(session.me).toBeNull();
    expect(session.activeCompany).toBeNull();
    expect(localStorage.getItem(apiModule.TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(apiModule.REFRESH_KEY)).toBeNull();
    expect(localStorage.getItem(apiModule.ACTIVE_COMPANY_KEY)).toBeNull();
  });

  it("refreshes a 401 once and retries the original request", async () => {
    localStorage.setItem(apiModule.TOKEN_KEY, "expired-access");
    localStorage.setItem(apiModule.REFRESH_KEY, "valid-refresh");
    const originalAdapter = apiModule.api.defaults.adapter;
    const adapter = vi
      .fn()
      .mockRejectedValueOnce({ response: { status: 401 }, config: {} })
      .mockResolvedValueOnce({
        data: { ok: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {},
      });
    apiModule.api.defaults.adapter = adapter;
    vi.spyOn(axios, "post").mockResolvedValue({
      data: { access_token: "renewed-access" },
    } as never);

    await expect(apiModule.apiGet("/protected")).resolves.toEqual({ ok: true });

    expect(adapter).toHaveBeenCalledTimes(2);
    expect(localStorage.getItem(apiModule.TOKEN_KEY)).toBe("renewed-access");
    apiModule.api.defaults.adapter = originalAdapter;
  });

  it("does not logout on a 403", async () => {
    const originalAdapter = apiModule.api.defaults.adapter;
    const unauthorized = vi.fn();
    apiModule.setUnauthorizedHandler(unauthorized);
    apiModule.api.defaults.adapter = vi.fn().mockRejectedValue({
      response: { status: 403 },
      config: {},
    });

    await expect(apiModule.apiGet("/forbidden")).rejects.toMatchObject({
      response: { status: 403 },
    });

    expect(unauthorized).not.toHaveBeenCalled();
    apiModule.api.defaults.adapter = originalAdapter;
  });

  it("never renders an undefined identity or company", () => {
    const session = useSessionStore();
    session.$patch({
      me: normalUser,
      authStatus: "authenticated",
      token: "valid-access",
      activeCompany: null,
    });

    const wrapper = mount(DashboardView, {
      global: { plugins: [/* the active Pinia is already installed */] },
    });

    expect(wrapper.text()).not.toContain("undefined");
    expect(wrapper.text()).not.toContain("Buenas tardes, .");
  });
});
