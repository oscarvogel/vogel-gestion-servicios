import { describe, it, expect, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useSessionStore } from "../stores/session";

describe("session store permissions", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("grants all permissions to SuperAdmin", () => {
    const store = useSessionStore();
    store.$patch({
      me: {
        id: 1,
        email: "su@vogel.local",
        full_name: "Super Admin",
        is_superadmin: true,
        active: true,
        memberships: [],
        permissions: [],
      },
    });
    expect(store.isSuperAdmin).toBe(true);
    expect(store.hasPermission("users.create")).toBe(true);
    expect(store.hasPermission("anything.at.all")).toBe(true);
  });

  it("only honors permissions returned by the API for company users", () => {
    const store = useSessionStore();
    store.$patch({
      me: {
        id: 2,
        email: "admin@vogel.local",
        full_name: "Admin",
        is_superadmin: false,
        active: true,
        memberships: [
          {
            company_id: 1,
            company_name: "A",
            company_slug: "a",
            company_active: true,
            is_admin: true,
            role: "ADMIN",
            active: true,
          },
        ],
        permissions: ["users.view", "users.create"],
      },
    });
    expect(store.hasPermission("users.view")).toBe(true);
    expect(store.hasPermission("users.create")).toBe(true);
    expect(store.hasPermission("roles.manage")).toBe(false);
  });
});