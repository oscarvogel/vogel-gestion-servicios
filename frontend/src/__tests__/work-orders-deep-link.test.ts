import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { useSessionStore, type MeResponse } from "../stores/session";
import WorkOrdersView from "../views/WorkOrdersView.vue";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

// La ruta es mutable: los tests cambian el query para simular el deep-link.
const ruta = vi.hoisted(() => ({
  path: "/app/work-orders",
  query: {} as Record<string, unknown>,
  fullPath: "/app/work-orders",
}));
const replace = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async () => {
  const real: any = await vi.importActual("../lib/api");
  return {
    ...real,
    apiGet,
    apiPost,
    apiPatch: vi.fn(),
    apiDelete: vi.fn(),
    apiPut: vi.fn(),
    getApiErrorMessage: () => "error simulado",
  };
});

vi.mock("vue-router", () => ({
  useRoute: () => ruta,
  useRouter: () => ({ push: vi.fn(), replace }),
  RouterLink: { template: "<a><slot /></a>" },
}));

const RouterLink = { template: "<a><slot /></a>" };

const TECNICOS = [
  { id: 1, name: "Britez Sebastian", active: true, legacy_code: null },
  { id: 2, name: "Alladio", active: true, legacy_code: 33 },
];

function me(permissions: string[]): MeResponse {
  return {
    id: 1,
    email: "admin@electrotecniref.com.ar",
    full_name: "Admin",
    is_superadmin: false,
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
    permissions,
  };
}

function prepararSesion(permissions: string[]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore(pinia);
  session.$patch({
    me: me(permissions),
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
  return pinia;
}

function montar(pinia: ReturnType<typeof createPinia>) {
  return mount(WorkOrdersView, {
    global: { plugins: [pinia], components: { RouterLink } },
  });
}

const PERMISOS = ["work_orders.view", "work_orders.manage", "technicians.view"];

describe("deep-link de nueva orden (botón + Nueva OT del dashboard)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    ruta.path = "/app/work-orders";
    ruta.query = {};
    ruta.fullPath = "/app/work-orders";
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/work-orders/statuses")) return Promise.resolve([]);
      if (url === "/work-orders") {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 25 });
      }
      if (url === "/technicians") return Promise.resolve(TECNICOS);
      if (url === "/companies/current") {
        return Promise.resolve({ timezone: "America/Argentina/Cordoba" });
      }
      if (url === "/company-parameters") return Promise.resolve([]);
      return Promise.resolve([]);
    });
    apiPost.mockResolvedValue({ id: 1, number: 9316, equipment_id: 9 });
  });

  it("abre el modal de recepción cuando la URL trae ?new=1", async () => {
    ruta.query = { new: "1" };
    ruta.fullPath = "/app/work-orders?new=1";
    const pinia = prepararSesion(PERMISOS);
    const wrapper = montar(pinia);
    await flushPromises();

    expect(wrapper.find(".reception-modal").exists()).toBe(true);
    expect(wrapper.text()).toContain("Nueva recepción");
  });

  it("abre el modal aunque una carga falla (por ejemplo, /work-orders/statuses en 500)", async () => {
    // Esto es lo que paso en staging: un 500 transitorio de la base hacia fallar el
    // Promise.all del onMounted y el deep-link nunca se procesaba.
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/work-orders/statuses")) return Promise.reject(new Error("500"));
      if (url === "/work-orders") {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 25 });
      }
      if (url === "/technicians") return Promise.resolve(TECNICOS);
      if (url === "/companies/current") {
        return Promise.resolve({ timezone: "America/Argentina/Cordoba" });
      }
      if (url === "/company-parameters") return Promise.resolve([]);
      return Promise.resolve([]);
    });

    ruta.query = { new: "1" };
    ruta.fullPath = "/app/work-orders?new=1";
    const pinia = prepararSesion(PERMISOS);
    const wrapper = montar(pinia);
    await flushPromises();

    expect(wrapper.find(".reception-modal").exists()).toBe(true);
  });

  it("limpia el query despues de tomar el deep-link", async () => {
    ruta.query = { new: "1" };
    ruta.fullPath = "/app/work-orders?new=1";
    const pinia = prepararSesion(PERMISOS);
    montar(pinia);
    await flushPromises();

    expect(replace).toHaveBeenCalled();
    const llamado = replace.mock.calls[0][0];
    expect(llamado.query.new).toBeUndefined();
  });
});

describe("listado de órdenes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    ruta.path = "/app/work-orders";
    ruta.query = {};
    ruta.fullPath = "/app/work-orders";
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/work-orders/statuses")) return Promise.resolve([]);
      if (url === "/work-orders") {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 25 });
      }
      if (url === "/technicians") return Promise.resolve(TECNICOS);
      if (url === "/companies/current") {
        return Promise.resolve({ timezone: "America/Argentina/Cordoba" });
      }
      if (url === "/company-parameters") return Promise.resolve([]);
      return Promise.resolve([]);
    });
  });

  it("no se rompe si la respuesta del listado viene sin items", async () => {
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/work-orders/statuses")) return Promise.resolve([]);
      if (url === "/work-orders") return Promise.resolve({} as any);
      if (url === "/technicians") return Promise.resolve(TECNICOS);
      if (url === "/companies/current") {
        return Promise.resolve({ timezone: "America/Argentina/Cordoba" });
      }
      if (url === "/company-parameters") return Promise.resolve([]);
      return Promise.resolve([]);
    });

    const pinia = prepararSesion(PERMISOS);
    const wrapper = montar(pinia);
    await flushPromises();

    // La pantalla no se cae: muestra el estado vacio y el contador en cero.
    expect(wrapper.text()).toContain("Todavía no hay órdenes de trabajo");
    expect(wrapper.text()).toContain("0 órdenes en esta empresa");
  });
});

describe("combo de técnicos de la recepción", () => {
  it("el contenedor del desplegable está posicionado", () => {
    // jsdom no calcula posiciones, así que el bug de CSS no se ve en el DOM. Lo que se
    // rompe en el navegador es que el menu se ancla al .modal-backdrop (fixed, toda la
    // pantalla) y aparece en el borde inferior, lejos del campo: la lista se ve pero no
    // se puede hacer clic. Por eso el fix se controla sobre el fuente.
    const rutas = ["src/views/WorkOrdersView.vue", "frontend/src/views/WorkOrdersView.vue"];
    const archivo = rutas.map((r) => resolve(process.cwd(), r)).find((r) => existsSync(r));
    expect(archivo).toBeTruthy();
    const fuente = readFileSync(archivo!, "utf8");
    expect(fuente).toMatch(/\.technician-picker\{[^}]*position:relative/);
  });
});
