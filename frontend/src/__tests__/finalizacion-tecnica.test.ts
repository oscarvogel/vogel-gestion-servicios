import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

import { useSessionStore, type MeResponse } from "../stores/session";
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

const CLIENTE = { id: 7, name: "PEREZ JUAN", phone: "351", whatsapp: null };
const EQUIPO = {
  id: 9,
  category_name: "Heladera",
  brand: "HELADERA BRIKET",
  model: "X",
  serial_number: "SN-1",
};
const STATUS_ENTREGADO = {
  id: 8,
  name: "Entregado",
  color: "#64748B",
  sort_order: 80,
  active: true,
  is_initial: false,
  is_final: true,
  marks_completed: false,
  marks_delivered: true,
};

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

function orden(extra: Record<string, unknown> = {}) {
  return {
    id: 1,
    number: 9316,
    customer_id: 7,
    customer_name: "PEREZ JUAN",
    customer_phone: null,
    equipment_id: 9,
    equipment_label: "HELADERA BRIKET",
    serial_number: null,
    received_at: "2026-10-21T10:00:00",
    expected_delivery_at: null,
    completed_at: null,
    delivered_at: null,
    reported_fault: "No enfria",
    physical_condition: null,
    accessories: null,
    notes: null,
    received_by_name: "Recepción",
    status: "RECEIVED",
    status_id: 1,
    status_name: "Recibido",
    status_color: "#10B981",
    technicians: [],
    work_area_id: 1,
    work_area_name: "BRIKET GARANTIAS",
    warranty_type: 1,
    warranty_label: "Garantía de terceros",
    billing_customer_id: 10,
    billing_customer_name: "BRIKET S.A.",
    ...extra,
  };
}

/** Las respuestas de la API para una orden dada. */
function mockearApi(ot: Record<string, unknown>) {
  apiGet.mockImplementation((url: string) => {
    if (url === "/work-orders") {
      return Promise.resolve({ items: [ot], total: 1, page: 1, page_size: 25 });
    }
    if (url === "/work-orders/1") return Promise.resolve(ot);
    if (url.includes("/work-orders/statuses")) return Promise.resolve([STATUS_ENTREGADO]);
    if (url.includes("/work-orders/1/events")) return Promise.resolve([]);
    if (url.includes("/work-orders/1/notifications")) {
      return Promise.resolve({ items: [], total: 0 });
    }
    if (url.includes("/work-orders/1/documents")) {
      return Promise.resolve({ items: [], total: 0 });
    }
    if (url.includes("/work-orders/1/diagnosis")) return Promise.resolve(null);
    if (url === "/work-orders/1/quotes") return Promise.resolve([]);
    if (url === "/work-orders/1/execution") return Promise.resolve([]);
    if (url === "/work-orders/1/final-tests") return Promise.resolve([]);
    if (url === "/work-areas") return Promise.resolve([]);
    if (url === "/technicians") return Promise.resolve([]);
    if (url === "/companies/current") {
      return Promise.resolve({ timezone: "America/Argentina/Cordoba" });
    }
    if (url.startsWith("/customers")) return Promise.resolve({ items: [CLIENTE] });
    if (url === "/customers/7/equipment") return Promise.resolve([EQUIPO]);
    return Promise.resolve([]);
  });
  apiPost.mockImplementation((url: string) => {
    if (url === "/work-orders/1/technical-completion") {
      return Promise.resolve({ ...ot, completed_at: "2026-10-26T21:32:00" });
    }
    return Promise.resolve({});
  });
}

describe("finalización técnica de la orden", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockearApi(orden());
  });

  it("avisa que sin finalización técnica la orden no entra al cierre", async () => {
    const pinia = prepararSesion(["work_orders.view", "work_orders.manage"]);
    const wrapper = montar(pinia);
    await flushPromises();

    await wrapper.find(".work-order-link").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Sin finalización técnica esta orden no entra al cierre a marcas");
    expect(wrapper.find(".area-hint-action").exists()).toBe(true);
  });

  it("registra la finalización técnica con la fecha de la entrega real", async () => {
    mockearApi(orden({ delivered_at: "2026-10-26T21:32:00" }));
    const pinia = prepararSesion(["work_orders.view", "work_orders.manage"]);
    const wrapper = montar(pinia);
    await flushPromises();

    await wrapper.find(".work-order-link").trigger("click");
    await flushPromises();

    await wrapper.find(".area-hint-action").trigger("click");
    await flushPromises();

    // El modal viene con la fecha de la entrega real, que es cuando terminó el trabajo.
    const fecha = wrapper
      .find('input[aria-label="Fecha de finalización técnica"]')
      .element as HTMLInputElement;
    expect(fecha.value).toBe("2026-10-26T18:32");

    const guardar = wrapper
      .findAll("button")
      .find((b) => b.text().trim() === "Registrar" && b.classes().includes("btn--primary"));
    expect(guardar).toBeTruthy();
    await guardar!.trigger("click");
    await flushPromises();

    // La hora escrita es la de la empresa: se guarda como UTC, que es como se compara
    // contra el período del cierre.
    expect(apiPost).toHaveBeenCalledWith("/work-orders/1/technical-completion", {
      completed_at: "2026-10-26T21:32:00.000Z",
      note: null,
    });
  });

  it("deja registrarla aunque la orden ya esté entregada", async () => {
    // El caso real: la orden esta en estado final (entregada) y hay que corregirle la
    // finalización técnica para que entre al cierre.
    mockearApi(
      orden({
        status_id: 8,
        status_name: "Entregado",
        status: "ENTREGADO",
        delivered_at: "2026-10-26T21:32:00",
      }),
    );
    const pinia = prepararSesion(["work_orders.view", "work_orders.manage"]);
    const wrapper = montar(pinia);
    await flushPromises();

    await wrapper.find(".work-order-link").trigger("click");
    await flushPromises();

    // La orden entregada no tiene finalización técnica: el aviso y el botón siguen ahí.
    expect(wrapper.text()).toContain("Sin finalización técnica esta orden no entra al cierre a marcas");
    expect(wrapper.find(".area-hint-action").exists()).toBe(true);

    await wrapper.find(".area-hint-action").trigger("click");
    await flushPromises();
    const guardar = wrapper
      .findAll("button")
      .find((b) => b.text().trim() === "Registrar" && b.classes().includes("btn--primary"));
    await guardar!.trigger("click");
    await flushPromises();

    expect(apiPost).toHaveBeenCalledWith(
      "/work-orders/1/technical-completion",
      expect.objectContaining({ completed_at: "2026-10-26T21:32:00.000Z" }),
    );
  });

  it("sin permiso de administrar no deja registrarla", async () => {
    const pinia = prepararSesion(["work_orders.view"]);
    const wrapper = montar(pinia);
    await flushPromises();

    await wrapper.find(".work-order-link").trigger("click");
    await flushPromises();

    // El aviso se ve igual: el problema hay que saberlo siempre.
    expect(wrapper.text()).toContain("Sin finalización técnica esta orden no entra al cierre a marcas");
    expect(wrapper.find(".area-hint-action").exists()).toBe(false);
    expect(wrapper.find(".completion-editor button").exists()).toBe(false);
  });
});
