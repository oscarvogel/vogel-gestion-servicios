import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { useSessionStore, type MeResponse } from "../stores/session";
import CompaniesView from "../views/CompaniesView.vue";

// Se reexporta el modulo real y se pisa solo lo que hace falta: si se reemplaza entero, el
// store de sesion se queda sin TOKEN_KEY y revienta al crearse.
const apiGet = vi.hoisted(() => vi.fn());
const apiPut = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async () => {
  const real: any = await vi.importActual("../lib/api");
  return {
    ...real,
    apiGet,
    apiPut,
    apiPatch,
    apiPost,
    getApiErrorMessage: () => "error simulado",
  };
});

const routerPush = vi.hoisted(() => vi.fn());
const routerReplace = vi.hoisted(() => vi.fn());

vi.mock("vue-router", () => ({
  useRoute: () => ({ path: "/app/companies", query: {}, fullPath: "/app/companies" }),
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
  RouterLink: { template: "<a><slot /></a>" },
}));

const empresa = {
  id: 3,
  name: "Electrotecniref",
  legal_name: "ELECTROTECNIREF S.A.",
  tax_id: "",
  slug: "electrotecniref",
  email: "",
  phone: "",
  address: "",
  notes: "",
  timezone: "America/Argentina/Cordoba",
  locale: "es-AR",
  whatsapp_instance_id: null,
  notification_sender_name: null,
  notification_sender_email: null,
  active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  user_count: 2,
};

const flexxus = {
  company_id: 3,
  company_name: "Electrotecniref",
  enabled: false,
  database: "C:\\FLEXXUS\\DB\\ETR\\DB-ETR.gdb",
  price_list: 1,
};

function me(isSuperadmin: boolean): MeResponse {
  return {
    id: 1,
    email: isSuperadmin ? "root@staging.example.com" : "admin@electrotecniref.com.ar",
    full_name: isSuperadmin ? "Root" : "Admin",
    is_superadmin: isSuperadmin,
    active: true,
    memberships: [
      {
        company_id: 3,
        company_name: "Electrotecniref",
        company_slug: "electrotecniref",
        company_active: true,
        is_admin: true,
        role: "ADMIN",
        active: true,
      },
    ],
    permissions: [],
  };
}

async function montar(isSuperadmin: boolean) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore(pinia);
  session.$patch({
    me: me(isSuperadmin),
    token: "valid-access",
    authStatus: "authenticated",
    activeCompany: {
      id: 3,
      name: "Electrotecniref",
      slug: "electrotecniref",
      active: true,
      is_admin: true,
    },
  });

  const wrapper = mount(CompaniesView, {
    global: { plugins: [pinia], stubs: { teleport: true } },
  });
  await flushPromises();
  return wrapper;
}

/** La seccion del catalogo de repuestos dentro del modal de empresa. */
function seccionFlexxus(wrapper: Awaited<ReturnType<typeof montar>>) {
  return wrapper.findAll("section").find((s) => s.text().includes("Flexxus"));
}

async function abrirModal(wrapper: Awaited<ReturnType<typeof montar>>) {
  const boton = wrapper.findAll("button").find((b) => b.text() === "Editar");
  expect(boton).toBeTruthy();
  await boton!.trigger("click");
  await flushPromises();
}

describe("el catalogo de repuestos en el modal de empresa", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/flexxus")) return Promise.resolve({ ...flexxus });
      if (url.includes("/ai")) {
        return Promise.resolve({
          company_id: 3,
          company_name: "Electrotecniref",
          enabled: false,
          monthly_quota_usd: 0,
          monthly_request_limit: 0,
          usage_requests: 0,
          usage_cost_usd: 0,
          usage_input_tokens: 0,
          usage_output_tokens: 0,
          last_period_cost_usd: 0,
          over_quota: false,
          quota_exhausted: false,
        });
      }
      return Promise.resolve({ items: [empresa], total: 1 });
    });
    apiPut.mockImplementation((url: string) => {
      if (url.includes("/flexxus")) {
        return Promise.resolve({ ...flexxus, enabled: true, price_list: 3 });
      }
      return Promise.resolve({});
    });
    apiPatch.mockResolvedValue({});
    apiPost.mockResolvedValue({});
  });

  it("el superadmin ve la seccion y carga el estado del catalogo", async () => {
    const w = await montar(true);
    await abrirModal(w);

    const seccion = seccionFlexxus(w);
    expect(seccion).toBeTruthy();
    expect(seccion!.text()).toContain("Catálogo de repuestos");
    expect(apiGet).toHaveBeenCalledWith("/companies/3/flexxus");
  });

  it("guardar manda el interruptor, la base y la lista de precios", async () => {
    const w = await montar(true);
    await abrirModal(w);

    const seccion = seccionFlexxus(w)!;
    const interruptor = seccion.find('input[type="checkbox"]');
    await interruptor.setValue(true);
    const lista = seccion.find('input[type="number"]');
    await lista.setValue("3");
    await flushPromises();

    const guardar = seccion.findAll("button").find((b) => b.text().includes("Guardar el catálogo"));
    expect(guardar).toBeTruthy();
    await guardar!.trigger("click");
    await flushPromises();

    const llamada = apiPut.mock.calls.find((c) => String(c[0]).includes("/flexxus"));
    expect(llamada).toBeTruthy();
    expect(llamada![0]).toBe("/companies/3/flexxus");
    expect(llamada![1]).toMatchObject({ enabled: true, price_list: 3 });
  });

  it("un administrador que no es superadmin ni llega a la pantalla de empresas", async () => {
    // La pantalla de empresas es de plataforma: un admin de empresa es devuelto al
    // dashboard. Con eso, la seccion del catalogo no se le puede mostrar.
    const w = await montar(false);
    await flushPromises();

    expect(routerReplace).toHaveBeenCalledWith({ name: "dashboard" });
    expect(seccionFlexxus(w)).toBeFalsy();
    expect(apiGet).not.toHaveBeenCalledWith("/companies/3/flexxus");
  });
});
