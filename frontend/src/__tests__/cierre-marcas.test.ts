import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { useSessionStore, type MeResponse } from "../stores/session";
import CierreMarcasView from "../views/CierreMarcasView.vue";

// Se reexporta el modulo real y se pisa solo lo que hace falta: si se reemplaza entero, el
// store de sesion se queda sin TOKEN_KEY y revienta al crearse.
const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async () => {
  const real: any = await vi.importActual("../lib/api");
  return { ...real, apiGet, apiPost, getApiErrorMessage: () => "error simulado" };
});

const reporte = {
  period: "2025-06",
  companies: [
    {
      billing_customer_id: 7,
      billing_customer_name: "DREAN S.A.",
      works_count: 2,
      total_amount: "300.000000",
      warranty_works_count: 1,
      warranty_amount: "100.000000",
      out_of_warranty_works_count: 1,
      out_of_warranty_amount: "200.000000",
      own_warranty_works_count: 0,
      own_warranty_amount: "0.000000",
      works: [
        {
          work_order_id: 1,
          number: 9316,
          legacy_number: "48542",
          completed_at: "2025-06-18T10:00:00",
          client_name: "DREAN S.A.",
          work_area: "WHIRLPOOL GARANTIAS",
          policy_code: "AGU",
          warranty_type: 1,
          amount: "100.000000",
          equipment: "LAVADORA",
          serial_number: "S/N",
        },
        {
          work_order_id: 2,
          number: 9315,
          legacy_number: null,
          completed_at: "2025-06-19T10:00:00",
          client_name: "DREAN S.A.",
          work_area: "WHIRLPOOL FUERA",
          policy_code: "FUERA",
          warranty_type: 0,
          amount: "200.000000",
          equipment: "LAVADORA",
          serial_number: null,
        },
      ],
    },
    {
      billing_customer_id: 8,
      billing_customer_name: "ALLADIO",
      works_count: 1,
      total_amount: "50.000000",
      warranty_works_count: 0,
      warranty_amount: "0.000000",
      out_of_warranty_works_count: 0,
      out_of_warranty_amount: "0.000000",
      own_warranty_works_count: 1,
      own_warranty_amount: "50.000000",
      works: [],
    },
  ],
  totals: {
    works_count: 3,
    total_amount: "350.000000",
    warranty_works_count: 1,
    warranty_amount: "100.000000",
    out_of_warranty_works_count: 1,
    out_of_warranty_amount: "200.000000",
    own_warranty_works_count: 1,
    own_warranty_amount: "50.000000",
  },
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

async function montar(permissions: string[]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  // Se pide el store con el pinia explicito: en pinia 3, useSessionStore() sin argumento
  // puede resolver otra instancia si hay contexto de app y el componente no ve los permisos.
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

  const wrapper = mount(CierreMarcasView, { global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}

describe("pantalla de cierre mensual a marcas", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/warranty-settlements/registros")) {
        return Promise.resolve({ items: [], total: 0 });
      }
      return Promise.resolve(reporte);
    });
    apiPost.mockResolvedValue({});
  });

  it("muestra los totales del periodo", async () => {
    const wrapper = await montar(["warranty_settlements.view"]);

    expect(wrapper.text()).toContain("350,00");
    expect(wrapper.text()).toContain("Cierre por empresa");
    expect(wrapper.text()).toContain("DREAN S.A.");
    expect(wrapper.text()).toContain("ALLADIO");
  });

  it("separa garantia de terceros, garantia propia y fuera de garantia", async () => {
    const wrapper = await montar(["warranty_settlements.view"]);

    // Los tres casilleros con su monto, y no fundidos en dos.
    expect(wrapper.text()).toContain("En garantía de terceros");
    expect(wrapper.text()).toContain("Garantía propia o de service");
    expect(wrapper.text()).toContain("Fuera de garantía");
    expect(wrapper.text()).toContain("100,00");
    expect(wrapper.text()).toContain("50,00");
    expect(wrapper.text()).toContain("200,00");
  });

  it("muestra el detalle de los trabajos al tocar una empresa", async () => {
    const wrapper = await montar(["warranty_settlements.view"]);

    expect(wrapper.text()).not.toContain("WHIRLPOOL GARANTIAS");

    await wrapper.findAll(".fila-empresa")[0].trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("WHIRLPOOL GARANTIAS");
    expect(wrapper.text()).toContain("#9316");
    expect(wrapper.text()).toContain("48542");
    expect(wrapper.text()).toContain("Garantía de terceros");
    expect(wrapper.text()).toContain("Fuera de garantía");
  });

  it("no ofrece generar ni liquidar sin el permiso de administrar", async () => {
    const wrapper = await montar(["warranty_settlements.view"]);

    expect(wrapper.text()).not.toContain("Generar cierre");
    expect(wrapper.text()).not.toContain("Liquidar");
  });

  it("ofrece generar el cierre con el permiso de administrar", async () => {
    const wrapper = await montar(["warranty_settlements.view", "warranty_settlements.manage"]);

    expect(wrapper.text()).toContain("Generar cierre");

    await wrapper.findAll("button").find((b) => b.text() === "Generar cierre")!.trigger("click");
    await flushPromises();

    expect(apiPost).toHaveBeenCalledWith("/warranty-settlements/generate", { period: expect.any(String) });
  });

  it("una empresa sin cierre se puede generar sola", async () => {
    const wrapper = await montar(["warranty_settlements.view", "warranty_settlements.manage"]);

    const botones = wrapper.findAll("button").filter((b) => b.text() === "Generar");
    expect(botones).toHaveLength(2);
    await botones[0].trigger("click");
    await flushPromises();

    expect(apiPost).toHaveBeenCalledWith("/warranty-settlements/generate/7", { period: expect.any(String) });
    expect(apiPost).not.toHaveBeenCalledWith("/warranty-settlements/generate", expect.anything());
  });

  it("un cierre emitido manda sobre el calculo y se puede filtrar por estado", async () => {
    apiGet.mockImplementation((url: string) => {
      if (url.includes("/warranty-settlements/registros")) {
        const drean = reporte.companies[0];
        return Promise.resolve({
          items: [
            { ...drean, id: 50, period: "2025-06", status: "cancelled", total_amount: "1.000000", generated_at: "2025-07-01" },
            { ...drean, id: 51, period: "2025-06", status: "issued", total_amount: "275.000000", generated_at: "2025-07-02" },
          ],
          total: 2,
        });
      }
      return Promise.resolve(reporte);
    });
    const wrapper = await montar(["warranty_settlements.view", "warranty_settlements.manage"]);

    // El emitido congela el numero: se ve su total, no el del calculo ni el del anulado.
    expect(wrapper.text()).toContain("275,00");
    expect(wrapper.text()).toContain("Emitido");
    expect(wrapper.text()).toContain("Liquidar");
    expect(wrapper.findAll(".fila-empresa")).toHaveLength(2);

    await wrapper.findAll(".filtro").find((b) => b.text().startsWith("Emitido"))!.trigger("click");
    expect(wrapper.findAll(".fila-empresa")).toHaveLength(1);
    expect(wrapper.text()).not.toContain("ALLADIO");
  });

  it("no muestra la pantalla sin el permiso de ver", async () => {
    const wrapper = await montar(["work_orders.view"]);

    expect(wrapper.text()).not.toContain("Cierre por empresa");
    expect(apiGet).not.toHaveBeenCalled();
  });
});
