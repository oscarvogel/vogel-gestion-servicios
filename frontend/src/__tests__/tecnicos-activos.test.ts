import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { useSessionStore, type MeResponse } from "../stores/session";
import TecnicosView from "../views/TecnicosView.vue";
import WorkOrdersView from "../views/WorkOrdersView.vue";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
const apiDelete = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async () => {
  const real: any = await vi.importActual("../lib/api");
  return {
    ...real,
    apiGet,
    apiPost,
    apiPatch,
    apiDelete,
    apiPut: vi.fn(),
    getApiErrorMessage: () => "error simulado",
  };
});

vi.mock("vue-router", () => ({
  useRoute: () => ({ path: "/app/work-orders", query: {}, fullPath: "/app/work-orders" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  RouterLink: { template: "<a><slot /></a>" },
}));

const RouterLink = { template: "<a><slot /></a>" };

const TECNICOS = [
  { id: 1, name: "Britez Sebastian", active: true, legacy_code: 12 },
  { id: 2, name: "Alladio", active: true, legacy_code: 33 },
  { id: 3, name: "Pérez Juan", active: false, legacy_code: 44 },
];

function me(permissions: string[]): MeResponse {
  return {
    id: 1,
    email: "admin@electrotecniref.com.ar",
    full_name: "Administrador",
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

function montar(componente: any, pinia: ReturnType<typeof createPinia>) {
  return mount(componente, {
    global: { plugins: [pinia], components: { RouterLink } },
  });
}

describe("ver los técnicos activos", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockResolvedValue(TECNICOS);
  });

  it("el maestro filtra por estado: todos, activos y desactivados", async () => {
    const pinia = prepararSesion(["technicians.view", "technicians.manage"]);
    const wrapper = montar(TecnicosView, pinia);
    await flushPromises();

    expect(wrapper.text()).toContain("Britez Sebastian");
    expect(wrapper.text()).toContain("Pérez Juan");

    const chipActivos = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Activos ("));
    expect(chipActivos).toBeTruthy();
    await chipActivos!.trigger("click");
    await flushPromises();

    // El desactivado deja de listarse, pero el contador sigue diciendo cuantos hay.
    expect(wrapper.text()).not.toContain("Pérez Juan");
    expect(wrapper.text()).toContain("Britez Sebastian");
    expect(wrapper.text()).toContain("2 activos de 3");

    const chipDesactivados = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Desactivados ("));
    await chipDesactivados!.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Pérez Juan");
    expect(wrapper.text()).not.toContain("Alladio");

    const chipTodos = wrapper.findAll("button").find((b) => b.text().trim() === "Todos");
    await chipTodos!.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Alladio");
    expect(wrapper.text()).toContain("Pérez Juan");
  });
});

describe("los técnicos en la orden de trabajo", () => {
  const OT = {
    id: 1,
    number: 9316,
    customer_id: 7,
    customer_name: "DREAN S.A.",
    customer_phone: null,
    equipment_id: 9,
    equipment_label: "LAVADORA",
    serial_number: null,
    received_at: "2026-10-01T10:00:00",
    expected_delivery_at: null,
    completed_at: null,
    delivered_at: null,
    reported_fault: "No enciende",
    physical_condition: null,
    accessories: null,
    notes: null,
    received_by_name: "Recepción",
    status: "RECEIVED",
    status_id: null,
    status_name: "Recibido",
    status_color: "#10B981",
    technicians: [
      { id: 1, name: "Britez Sebastian", active: true },
      { id: 3, name: "Pérez Juan", active: false },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/work-orders/statuses")) return Promise.resolve([]);
      if (url.includes("/work-orders/1/events")) return Promise.resolve([]);
      if (url.includes("/work-orders/1/notifications")) {
        return Promise.resolve({ items: [], total: 0 });
      }
      if (url.includes("/work-orders/1/documents")) {
        return Promise.resolve({ items: [], total: 0 });
      }
      if (url === "/work-orders/1") return Promise.resolve(OT);
      if (url === "/work-orders") {
        return Promise.resolve({ items: [OT], total: 1, page: 1, page_size: 25 });
      }
      if (url === "/technicians") return Promise.resolve(TECNICOS);
      if (url === "/companies/current") {
        return Promise.resolve({ timezone: "America/Argentina/Cordoba" });
      }
      if (url.includes("/work-orders/1/diagnosis")) return Promise.resolve(null);
      return Promise.resolve([]);
    });
    apiPost.mockResolvedValue({});
    apiDelete.mockResolvedValue({ ...OT, technicians: [] });
  });

  async function abrirOrden() {
    const pinia = prepararSesion([
      "work_orders.view",
      "work_orders.manage",
      "technicians.view",
    ]);
    const wrapper = montar(WorkOrdersView, pinia);
    await flushPromises();
    const abrir = wrapper.find(".work-order-link");
    await abrir!.trigger("click");
    await flushPromises();
    return wrapper;
  }

  it("marca como Inactivo al técnico desactivado que ya estaba asignado", async () => {
    const wrapper = await abrirOrden();

    const chips = wrapper.findAll(".technician-chip");
    expect(chips.length).toBe(2);
    // El activo se ve como siempre.
    expect(chips[0].classes()).not.toContain("technician-chip--inactive");
    expect(chips[0].text()).not.toContain("Inactivo");
    // El desactivado se distingue y lo dice.
    expect(chips[1].classes()).toContain("technician-chip--inactive");
    expect(chips[1].text()).toContain("Inactivo");
  });

  it("el selector solo ofrece técnicos activos", async () => {
    const wrapper = await abrirOrden();

    const input = wrapper.find('input[aria-label="Agregar un técnico"]');
    expect(input.exists()).toBe(true);
    await input.trigger("focus");
    await flushPromises();

    const opciones = wrapper.findAll(".technician-assign .customer-picker__option");
    const nombres = opciones.map((o) => o.text());
    // Solo los activos que todavia no estan en esta OT: Britez ya esta asignado y
    // Perez Juan esta desactivado.
    expect(nombres.join(" ")).toContain("Alladio");
    expect(nombres.join(" ")).not.toContain("Britez Sebastian");
    expect(nombres.join(" ")).not.toContain("Pérez Juan");
  });

  it("el input de agregar técnico toma el estilo del sitio", () => {
    // El input vive fuera de un .field: sin estos estilos sale blanco (el default del
    // navegador) en medio de la pantalla oscura.
    const rutas = ["src/views/WorkOrdersView.vue", "frontend/src/views/WorkOrdersView.vue"];
    const archivo = rutas.map((r) => resolve(process.cwd(), r)).find((r) => existsSync(r));
    expect(archivo).toBeTruthy();
    const fuente = readFileSync(archivo!, "utf8");
    const regla = fuente.match(/\.technician-assign input\{[^}]*\}/);
    expect(regla).toBeTruthy();
    expect(regla![0]).toContain("var(--color-surface)");
    expect(regla![0]).toContain("var(--color-border)");
  });
});
