import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

import { useSessionStore, type MeResponse } from "../stores/session";
import { invalidarAreas } from "../lib/work-areas";
import AreasView from "../views/AreasView.vue";
import WorkAreaPicker from "../components/WorkAreaPicker.vue";
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

const RouterLink = { template: "<a><slot /></a>" };

const AREAS = [
  {
    id: 1,
    area_code: "WHIRLPOOLGARANTIAS",
    area_name: "WHIRLPOOL GARANTÍAS",
    policy_code: "AGU",
    policy_description: "Garantía de fábrica",
    is_principal: false,
    billing_customer_id: 10,
    billing_customer_name: "DREAN S.A.",
    warranty_type: 1,
    warranty_label: "Garantía de terceros",
    liquidate_mode: 0,
    active: true,
  },
  {
    id: 2,
    area_code: "WHIRLPOOLFUERA",
    area_name: "WHIRLPOOL FUERA",
    policy_code: "FUERA",
    policy_description: null,
    is_principal: false,
    billing_customer_id: null,
    billing_customer_name: null,
    warranty_type: 0,
    warranty_label: "Fuera de garantía",
    liquidate_mode: 0,
    active: true,
  },
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

function montar(componente: any, pinia: ReturnType<typeof createPinia>) {
  return mount(componente, {
    global: { plugins: [pinia], components: { RouterLink } },
  });
}

describe("combo de área de trabajo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    invalidarAreas();
    apiGet.mockResolvedValue(AREAS);
  });

  it("filtra por texto sin distinguir mayúsculas ni acentos", async () => {
    const pinia = prepararSesion(["work_orders.view"]);
    const wrapper = montar(WorkAreaPicker, pinia);
    await flushPromises();

    const input = wrapper.find('input[aria-label="Área de trabajo"]');
    await input.setValue("garant");
    await flushPromises();

    const opciones = wrapper.findAll(".area-picker__option").map((o) => o.text());
    expect(opciones.some((t) => t.includes("WHIRLPOOL GARANTÍAS"))).toBe(true);
    expect(opciones.some((t) => t.includes("WHIRLPOOL FUERA"))).toBe(false);

    // "AGU" encuentra la política aunque esté en minúsculas.
    await input.setValue("agu");
    await flushPromises();
    expect(wrapper.findAll(".area-picker__option")).toHaveLength(1);
  });

  it("elegir un área de la lista guarda su id y muestra a quién se liquida", async () => {
    const pinia = prepararSesion(["work_orders.view"]);
    const wrapper = montar(WorkAreaPicker, pinia);
    await flushPromises();

    const input = wrapper.find('input[aria-label="Área de trabajo"]');
    await input.setValue("drean");
    await flushPromises();

    const opcion = wrapper
      .findAll(".area-picker__option")
      .find((o) => o.text().includes("WHIRLPOOL GARANTÍAS"));
    expect(opcion).toBeTruthy();
    await opcion!.trigger("mousedown");
    await flushPromises();

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([1]);
    expect(wrapper.emitted("change")?.at(-1)).toEqual([
      { area: AREAS[0], coincide: true },
    ]);
    // El operador tiene que ver a quién se le liquida antes de confirmar.
    expect(wrapper.text()).toContain("Se liquida a DREAN S.A.");
  });

  it("un texto que no está en el maestro no se guarda", async () => {
    const pinia = prepararSesion(["work_orders.view"]);
    const wrapper = montar(WorkAreaPicker, pinia);
    await flushPromises();

    const input = wrapper.find('input[aria-label="Área de trabajo"]');
    await input.setValue("fulano que no existe");
    await flushPromises();

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([null]);
    expect(wrapper.emitted("change")?.at(-1)).toEqual([
      { area: null, coincide: false },
    ]);
    expect(wrapper.text()).toContain("Ese área no está en el maestro");
  });

  it("avisa cuando el área no tiene empresa a liquidar", async () => {
    const pinia = prepararSesion(["work_orders.view"]);
    const wrapper = mount(WorkAreaPicker, {
      props: { modelValue: 2 },
      global: { plugins: [pinia], components: { RouterLink } },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Sin empresa a liquidar");
    expect(wrapper.text()).toContain("no entra al cierre");
  });
});

describe("maestro de áreas", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    invalidarAreas();
    apiGet.mockImplementation((url: string) => {
      if (url === "/work-areas") return Promise.resolve(AREAS);
      if (url.startsWith("/customers")) {
        return Promise.resolve({ items: [{ id: 10, name: "DREAN S.A.", customer_type: "COMPANY" }] });
      }
      return Promise.resolve([]);
    });
    apiPost.mockResolvedValue({
      ...AREAS[0],
      id: 3,
      area_name: "DREAN GARANTÍAS",
      area_code: "DREANGARANTIAS",
    });
    apiPatch.mockResolvedValue(AREAS[0]);
  });

  it("lista las áreas con su garantía y su empresa a liquidar", async () => {
    const pinia = prepararSesion(["work_areas.view", "work_areas.manage"]);
    const wrapper = montar(AreasView, pinia);
    await flushPromises();

    expect(apiGet).toHaveBeenCalledWith("/work-areas");
    expect(wrapper.text()).toContain("WHIRLPOOL GARANTÍAS");
    expect(wrapper.text()).toContain("AGU");
    expect(wrapper.text()).toContain("DREAN S.A.");
    expect(wrapper.text()).toContain("Garantía de terceros");
    // El área sin empresa a liquidar lo dice, no lo deja pasar en silencio.
    expect(wrapper.text()).toContain("Nadie");
  });

  it("filtra por texto sin distinguir mayúsculas ni acentos", async () => {
    const pinia = prepararSesion(["work_areas.view", "work_areas.manage"]);
    const wrapper = montar(AreasView, pinia);
    await flushPromises();

    await wrapper.find('input[aria-label="Buscar área"]').setValue("garanti");
    await flushPromises();
    expect(wrapper.text()).toContain("WHIRLPOOL GARANTÍAS");
    expect(wrapper.text()).not.toContain("WHIRLPOOL FUERA");
  });

  it("da de alta un área con su garantía y su empresa a liquidar", async () => {
    const pinia = prepararSesion(["work_areas.view", "work_areas.manage"]);
    const wrapper = montar(AreasView, pinia);
    await flushPromises();

    const nueva = wrapper.findAll("button").find((b) => b.text().includes("Nueva área"));
    expect(nueva).toBeTruthy();
    await nueva!.trigger("click");
    await flushPromises();

    await wrapper.find("#area-nombre").setValue("DREAN GARANTÍAS");
    await wrapper.find("#area-politica").setValue("agu");
    await wrapper.find("#area-garantia").setValue("1");

    // La empresa a liquidar sale de la lista de clientes.
    await wrapper.find("#area-empresa").setValue("drean");
    await flushPromises();
    const opcion = wrapper
      .findAll(".empresa-picker__option")
      .find((o) => o.text().includes("DREAN S.A."));
    expect(opcion).toBeTruthy();
    await opcion!.trigger("mousedown");
    await flushPromises();

    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(apiPost).toHaveBeenCalledWith("/work-areas", {
      area_name: "DREAN GARANTÍAS",
      policy_code: "AGU",
      policy_description: null,
      billing_customer_id: 10,
      warranty_type: 1,
      active: true,
    });
  });

  it("sin permiso de administrar no deja dar de alta", async () => {
    const pinia = prepararSesion(["work_areas.view"]);
    const wrapper = montar(AreasView, pinia);
    await flushPromises();

    expect(wrapper.findAll("button").some((b) => b.text().includes("Nueva área"))).toBe(false);
  });
});

describe("área en la orden de trabajo", () => {
  const CLIENTE = { id: 7, name: "PEREZ JUAN", phone: "351", whatsapp: null };
  const EQUIPO = {
    id: 9,
    category_name: "Lavarropas",
    brand: "LAVARROPAS",
    model: "X",
    serial_number: "SN-1",
  };
  const OT = {
    id: 1,
    number: 9316,
    customer_id: 7,
    customer_name: "PEREZ JUAN",
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
    technicians: [],
    work_area_id: 1,
    work_area_name: "WHIRLPOOL GARANTÍAS · AGU",
    warranty_type: 1,
    warranty_label: "Garantía de terceros",
    billing_customer_id: 10,
    billing_customer_name: "DREAN S.A.",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    invalidarAreas();
    apiGet.mockImplementation((url: string) => {
      if (url === "/work-areas") return Promise.resolve(AREAS);
      if (url === "/technicians") return Promise.resolve([]);
      if (url.includes("/work-orders/statuses")) return Promise.resolve([]);
      if (url.includes("/work-orders/1/events")) return Promise.resolve([]);
      if (url.includes("/work-orders/1/notifications")) {
        return Promise.resolve({ items: [], total: 0 });
      }
      if (url.includes("/work-orders/1/documents")) return Promise.resolve({ items: [], total: 0 });
      if (url === "/work-orders/1") return Promise.resolve(OT);
      if (url === "/work-orders") {
        return Promise.resolve({ items: [OT], total: 1, page: 1, page_size: 25 });
      }
      if (url.startsWith("/customers")) return Promise.resolve({ items: [CLIENTE] });
      if (url === "/customers/7/equipment") return Promise.resolve([EQUIPO]);
      if (url === "/companies/current") {
        return Promise.resolve({ timezone: "America/Argentina/Cordoba" });
      }
      if (url.includes("/work-orders/1/diagnosis")) return Promise.resolve(null);
      return Promise.resolve([]);
    });
    apiPost.mockImplementation((url: string) => {
      if (url === "/work-orders") return Promise.resolve(OT);
      return Promise.resolve({});
    });
    apiPatch.mockResolvedValue(OT);
  });

  it("la ficha de la orden muestra la garantía y a quién se liquida", async () => {
    const pinia = prepararSesion(["work_orders.view", "work_orders.manage"]);
    const wrapper = montar(WorkOrdersView, pinia);
    await flushPromises();

    await wrapper.find(".work-order-link").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Garantía y liquidación");
    expect(wrapper.text()).toContain("WHIRLPOOL GARANTÍAS · AGU");
    expect(wrapper.text()).toContain("Garantía de terceros");
    expect(wrapper.text()).toContain("DREAN S.A.");
  });

  it("la recepción manda el área elegida a la orden", async () => {
    const pinia = prepararSesion(["work_orders.view", "work_orders.manage"]);
    const wrapper = montar(WorkOrdersView, pinia);
    await flushPromises();

    const nueva = wrapper.findAll("button").find((b) => b.text().includes("Nueva recepción"));
    await nueva!.trigger("click");
    await flushPromises();

    // Cliente.
    await wrapper
      .find('input[placeholder*="Buscar por nombre"]')
      .setValue("PEREZ");
    await flushPromises();
    const cliente = wrapper
      .findAll(".customer-picker__option")
      .find((o) => o.text().includes("PEREZ JUAN"));
    await cliente!.trigger("click");
    await flushPromises();

    // Equipo.
    const selectEquipo = wrapper.find("select");
    await selectEquipo.setValue("9");
    await wrapper.find("textarea").setValue("No enciende");
    await flushPromises();

    // Área: se escribe y se elige de la lista.
    const inputArea = wrapper.find('input[aria-label="Área de trabajo"]');
    await inputArea.setValue("drean");
    await flushPromises();
    const opcion = wrapper
      .findAll(".area-picker__option")
      .find((o) => o.text().includes("WHIRLPOOL GARANTÍAS"));
    expect(opcion).toBeTruthy();
    await opcion!.trigger("mousedown");
    await flushPromises();

    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(apiPost).toHaveBeenCalledWith(
      "/work-orders",
      expect.objectContaining({ work_area_id: 1 }),
    );
  });

  it("no manda una orden con un área que no está en el maestro", async () => {
    const pinia = prepararSesion(["work_orders.view", "work_orders.manage"]);
    const wrapper = montar(WorkOrdersView, pinia);
    await flushPromises();

    const nueva = wrapper.findAll("button").find((b) => b.text().includes("Nueva recepción"));
    await nueva!.trigger("click");
    await flushPromises();

    await wrapper
      .find('input[placeholder*="Buscar por nombre"]')
      .setValue("PEREZ");
    await flushPromises();
    const cliente = wrapper
      .findAll(".customer-picker__option")
      .find((o) => o.text().includes("PEREZ JUAN"));
    await cliente!.trigger("click");
    await flushPromises();

    await wrapper.find("select").setValue("9");
    await wrapper.find("textarea").setValue("No enciende");
    await flushPromises();

    // Un área que no existe: la orden no se manda.
    await wrapper
      .find('input[aria-label="Área de trabajo"]')
      .setValue("fulano que no existe");
    await flushPromises();
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(apiPost).not.toHaveBeenCalledWith("/work-orders", expect.anything());
  });
});
