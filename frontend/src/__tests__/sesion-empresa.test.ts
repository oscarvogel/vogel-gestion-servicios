import { describe, it, expect, beforeEach, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import {
  useSessionStore,
  type MeResponse,
} from "../stores/session";
import { TOKEN_KEY, REFRESH_KEY, ACTIVE_COMPANY_KEY } from "../lib/api";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async () => {
  const real: any = await vi.importActual("../lib/api");
  return {
    ...real,
    apiGet,
    apiPost,
  };
});

function me(empresas: number, companyId = 3): MeResponse {
  return {
    id: 1,
    email: "admin@electrotecniref.com.ar",
    full_name: "Administrador",
    is_superadmin: false,
    active: true,
    memberships: [
      {
        company_id: companyId,
        company_name: "Electrotecniref",
        company_slug: "electrotecniref",
        company_active: true,
        is_admin: true,
        role: "ADMIN",
        active: true,
      },
    ],
    permissions: ["work_orders.view", "work_orders.manage"],
  };
}

describe("sesión sin empresa activa", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    apiGet.mockImplementation((url: string) => {
      if (url === "/auth/me") return Promise.resolve(me(1));
      return Promise.resolve([]);
    });
    apiPost.mockImplementation((url: string) => {
      if (url === "/auth/select-company") {
        return Promise.resolve({
          access_token: "access-con-empresa",
          refresh_token: "refresh-con-empresa",
          token_type: "bearer",
        });
      }
      return Promise.resolve({});
    });
  });

  it("vuelve a elegir la empresa si la sesión se recargó sin ella guardada", async () => {
    // Esto es lo que pasaba en staging: el token quedó en modo plataforma y todas
    // las consultas de empresa respondían 409, así que la pantalla quedaba en cero.
    localStorage.setItem(TOKEN_KEY, "access-plataforma");
    localStorage.setItem(REFRESH_KEY, "refresh-plataforma");

    const pinia = createPinia();
    setActivePinia(pinia);
    const session = useSessionStore(pinia);
    await session.bootstrap();

    expect(apiPost).toHaveBeenCalledWith("/auth/select-company", { company_id: 3 });
    expect(session.activeCompany?.id).toBe(3);
    expect(localStorage.getItem(ACTIVE_COMPANY_KEY)).toContain("Electrotecniref");
    // Y el refresh token nuevo (que ya trae la empresa) queda guardado.
    expect(localStorage.getItem(REFRESH_KEY)).toBe("refresh-con-empresa");
  });

  it("elige la empresa y guarda el refresh token que viene con ella", async () => {
    localStorage.setItem(TOKEN_KEY, "access-plataforma");

    const pinia = createPinia();
    setActivePinia(pinia);
    const session = useSessionStore(pinia);
    await session.selectCompany({
      id: 3,
      name: "Electrotecniref",
      slug: "electrotecniref",
      active: true,
      is_admin: true,
    });

    expect(localStorage.getItem(REFRESH_KEY)).toBe("refresh-con-empresa");
    expect(localStorage.getItem(TOKEN_KEY)).toBe("access-con-empresa");
  });

  it("no elige nada si el usuario tiene varias empresas", async () => {
    localStorage.setItem(TOKEN_KEY, "access-plataforma");
    apiGet.mockImplementation((url: string) => {
      if (url === "/auth/me") {
        const base = me(1);
        return Promise.resolve({
          ...base,
          memberships: [
            ...base.memberships,
            {
              company_id: 4,
              company_name: "Otra",
              company_slug: "otra",
              company_active: true,
              is_admin: true,
              role: "ADMIN",
              active: true,
            },
          ],
        });
      }
      return Promise.resolve([]);
    });

    const pinia = createPinia();
    setActivePinia(pinia);
    const session = useSessionStore(pinia);
    await session.bootstrap();

    expect(apiPost).not.toHaveBeenCalledWith(
      "/auth/select-company",
      expect.anything()
    );
    expect(session.activeCompany).toBe(null);
  });
});
