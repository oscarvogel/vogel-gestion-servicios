import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

import { useSessionStore, type MeResponse } from "../stores/session";
import TecnicosView from "../views/TecnicosView.vue";
import WorkOrdersView from "../views/WorkOrdersView.vue";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
const apiDelete = vi.hoisted(() => vi.fn());
const apiPut = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async () => {
  const real: any = await vi.importActual("../lib/api");
  return {
    ...real,
    apiGet,
    apiPost,
    apiPatch,
    apiDelete,
    apiPut,
    getApiErrorMessage: () => "error simulado",
  };
});

vi.mock("vue-router", () => ({
  useRoute: () => ({ path: "/app/work-orders", query: {}, fullPath: "/app/work-orders" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  RouterLink: { template: "<a><slot /></a>" },
}));

// El componente se registra a mano porque el router esta simulado.
const RouterLink = { template: "<a><slot /></a>" };

const TECNICOS = [
  { id: 1, name: "Britez Sebastian", active: true, legacy_code: null },
  { id: 2, name: "Alladio", active: true, legacy_code: 33 },
  { id: 3, name: "Pérez Juan", active: false, legacy_code: null },
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

// La sesion se arma sobre el MISMO pinia que se le pasa al componente: en pinia 3,
// useSessionStore() sin argumento puede resolver otra instancia si hay contexto de app.
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

describe("maestro de técnicos", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockResolvedValue(TECNICOS);
    apiPost.mockResolvedValue({ id: 4, name: "Nuevo", active: true, legacy_code: null });
    apiPatch.mockResolvedValue({ id: 1, name: "Britez, Sebastian", active: true, legacy_code: null });
  });

  it("lista los técnicos de la empresa", async () => {
    const pinia = prepararSesion(["technicians.view", "technicians.manage"]);
    const wrapper = montar(TecnicosView, pinia);
    await flushPromises();

    expect(apiGet).toHaveBeenCalledWith("/technicians");
    expect(wrapper.text()).toContain("Britez Sebastian");
    expect(wrapper.text()).toContain("Alladio");
    // Activos de 3: uno está desactivado.
    expect(wrapper.text()).toContain("2 activos de 3");
  });

  it("filtra por texto sin distinguir mayúsculas ni acentos", async () => {
    const pinia = prepararSesion(["technicians.view", "technicians.manage"]);
    const wrapper = montar(TecnicosView, pinia);
    await flushPromises();

    await wrapper.find('input[aria-label="Buscar técnico"]').setValue("perez");
    await flushPromises();
    expect(wrapper.text()).toContain("Pérez Juan");
    expect(wrapper.text()).not.toContain("Alladio");

    await wrapper.find('input[aria-label="Buscar técnico"]').setValue("ALL");
    await flushPromises();
    expect(wrapper.text()).toContain("Alladio");
    expect(wrapper.text()).not.toContain("Britez Sebastian");
  });

  it("da de alta un técnico nuevo", async () => {
    const pinia = prepararSesion(["technicians.view", "technicians.manage"]);
    const wrapper = montar(TecnicosView, pinia);
    await flushPromises();

    await wrapper.find("#nuevo-tecnico").setValue("Nuevo");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(apiPost).toHaveBeenCalledWith("/technicians", { name: "Nuevo" });
    expect(wrapper.text()).toContain("Nuevo");
  });

  it("renombra un técnico", async () => {
    const pinia = prepararSesion(["technicians.view", "technicians.manage"]);
    const wrapper = montar(TecnicosView, pinia);
    await flushPromises();

    const botonRenombrar = wrapper.findAll("button").find((b) => b.text() === "Renombrar");
    expect(botonRenombrar).toBeTruthy();
    await botonRenombrar!.trigger("click");
    await flushPromises();

    const guardar = wrapper.findAll("button").find((b) => b.text() === "Guardar");
    await guardar!.trigger("click");
    await flushPromises();

    expect(apiPatch).toHaveBeenCalledWith("/technicians/1", { name: "Britez Sebastian" });
  });

  it("sin permiso de administrar no deja dar de alta ni editar", async () => {
    const pinia = prepararSesion(["technicians.view"]);
    const wrapper = montar(TecnicosView, pinia);
    await flushPromises();

    expect(wrapper.text()).toContain("Britez Sebastian");
    expect(wrapper.find("#nuevo-tecnico").exists()).toBe(false);
    expect(wrapper.findAll("button").some((b) => b.text() === "Renombrar")).toBe(false);
  });
});

describe("asignación de técnicos a la orden de trabajo", () => {
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
    technicians: [{ id: 1, name: "Britez Sebastian", active: true }],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/work-orders/statuses")) return Promise.resolve([]);
      if (url.includes("/work-orders/1/events")) return Promise.resolve([]);
      if (url.includes("/work-orders/1/notifications")) return Promise.resolve({ items: [], total: 0 });
      if (url.includes("/work-orders/1/documents")) return Promise.resolve({ items: [], total: 0 });
      if (url === "/work-orders/1") return Promise.resolve(OT);
      if (url === "/work-orders") {
        return Promise.resolve({ items: [OT], total: 1, page: 1, page_size: 25 });
      }
      if (url === "/technicians") return Promise.resolve(TECNICOS);
      if (url === "/companies/current") {
        return Promise.resolve({ timezone: "America/Argentina/Cordoba" });
      }
      // El taller: sin diagnostico, sin presupuesto, sin ejecucion.
      if (url.includes("/work-orders/1/diagnosis")) return Promise.resolve(null);
      return Promise.resolve([]);
    });
    apiPost.mockImplementation((url: string) => {
      if (url.endsWith("/technicians")) {
        return Promise.resolve({ ...OT, technicians: [...OT.technicians, { id: 2, name: "Alladio", active: true }] });
      }
      if (url === "/work-orders") return Promise.resolve(OT);
      return Promise.resolve({});
    });
    apiDelete.mockResolvedValue({ ...OT, technicians: [] });
  });

  async function abrirOrden() {
    const pinia = prepararSesion(["work_orders.view", "work_orders.manage", "technicians.view"]);
    const wrapper = montar(WorkOrdersView, pinia);
    await flushPromises();
    const abrir = wrapper.findAll("button").find((b) => b.text() === "Abrir OT");
    expect(abrir).toBeTruthy();
    await abrir!.trigger("click");
    await flushPromises();
    return wrapper;
  }

  it("muestra los técnicos ya asignados en la OT", async () => {
    const wrapper = await abrirOrden();
    expect(wrapper.text()).toContain("Técnicos asignados");
    expect(wrapper.text()).toContain("Britez Sebastian");
  });

  it("asigna un técnico elegido de la lista", async () => {
    const wrapper = await abrirOrden();

    // El combo filtra por "contiene" y sin distinguir mayusculas ni acentos.
    const input = wrapper.find(".technician-assign input");
    expect(input.exists()).toBe(true);
    await input.setValue("allad");
    await flushPromises();

    const opcion = wrapper.findAll(".customer-picker__option").find((b) => b.text().includes("Alladio"));
    expect(opcion).toBeTruthy();
    await opcion!.trigger("click");
    await flushPromises();

    expect(apiPost).toHaveBeenCalledWith("/work-orders/1/technicians", { technician_id: 2 });
  });

  it("quita un técnico asignado", async () => {
    const wrapper = await abrirOrden();

    const quitar = wrapper.findAll("button.technician-chip__remove")[0];
    expect(quitar).toBeTruthy();
    await quitar.trigger("click");
    await flushPromises();

    expect(apiDelete).toHaveBeenCalledWith("/work-orders/1/technicians/1");
  });

  it("no deja escribir un técnico que no está en el maestro", async () => {
    const wrapper = await abrirOrden();

    const input = wrapper.find(".technician-assign input");
    await input.setValue("fulano que no existe");
    await flushPromises();

    expect(wrapper.findAll(".customer-picker__option").some((b) => b.text().includes("fulano"))).toBe(false);
    expect(apiPost).not.toHaveBeenCalled();
  });
});

describe("técnico en la recepción", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/work-orders/statuses")) return Promise.resolve([]);
      if (url === "/work-orders") return Promise.resolve({ items: [], total: 0, page: 1, page_size: 25 });
      if (url === "/technicians") return Promise.resolve(TECNICOS);
      if (url === "/companies/current") return Promise.resolve({ timezone: "America/Argentina/Cordoba" });
      if (url.includes("/documents")) return Promise.resolve({ items: [], total: 0 });
      return Promise.resolve([]);
    });
    apiPost.mockResolvedValue({ id: 1, number: 9316, equipment_id: 9 });
  });

  async function abrirRecepcion() {
    const pinia = prepararSesion(["work_orders.view", "work_orders.manage", "technicians.view"]);
    const wrapper = montar(WorkOrdersView, pinia);
    await flushPromises();
    const nueva = wrapper.findAll("button").find((b) => b.text().includes("Nueva recepción"));
    expect(nueva).toBeTruthy();
    await nueva!.trigger("click");
    await flushPromises();
    return wrapper;
  }

  it("elige un técnico del maestro y lo manda al crear la OT", async () => {
    const wrapper = await abrirRecepcion();

    const input = wrapper.find(".technician-picker input");
    expect(input.exists()).toBe(true);
    await input.setValue("allad");
    await flushPromises();

    const opcion = wrapper.findAll(".customer-picker__option").find((b) => b.text().includes("Alladio"));
    expect(opcion).toBeTruthy();
    await opcion!.trigger("click");
    await flushPromises();

    await wrapper.find(".reception-modal form").trigger("submit");
    await flushPromises();

    const llamada = apiPost.mock.calls.find((c) => c[0] === "/work-orders");
    expect(llamada).toBeTruthy();
    expect((llamada![1] as any).technician_id).toBe(2);
  });

  it("si el técnico no está en el maestro, la OT se crea sin técnico", async () => {
    const wrapper = await abrirRecepcion();

    const input = wrapper.find(".technician-picker input");
    await input.setValue("fulano que no existe");
    await flushPromises();

    await wrapper.find(".reception-modal form").trigger("submit");
    await flushPromises();

    const llamada = apiPost.mock.calls.find((c) => c[0] === "/work-orders");
    expect(llamada).toBeTruthy();
    expect((llamada![1] as any).technician_id).toBe(null);
  });
});
