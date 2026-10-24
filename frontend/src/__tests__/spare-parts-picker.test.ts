import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

import SparePartPicker from "../components/SparePartPicker.vue";

const apiGet = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async () => {
  const real: any = await vi.importActual("../lib/api");
  return { ...real, apiGet };
});

const PARTE = {
  code: "05589",
  description: "ADAPTADOR TRIPLE PIRAMIDAL CHATO NEGRO",
  rubro: "ADAPTADORES",
  marca: "STARBOX",
  stock: 1,
  stock_minimo: 0,
  cost: 1440,
  cost_currency: "ARS",
  cost_source_currency: "PESOS",
  sale_price: 2160,
  sale_price_currency: "ARS",
  price_source: "flexxus:PRECIOVENTA1",
  price_synced_at: "2026-10-24T12:00:00Z",
};

function montar() {
  const wrapper = mount(SparePartPicker, { props: { modelValue: "" } });
  montados.push(wrapper);
  return wrapper;
}

/**
 * El desplegable va por Teleport a `body`: no esta dentro del wrapper, asi
 * que se busca en el documento.
 */
function menu() {
  return document.querySelector(".spare-picker__menu");
}
function opciones() {
  return Array.from(document.querySelectorAll(".spare-picker__option"));
}
function clic(element: Element) {
  element.dispatchEvent(
    new MouseEvent("mousedown", { bubbles: true, cancelable: true }),
  );
}

/** Escribe en el input y espera a que pase el debounce. */
async function escribir(wrapper: ReturnType<typeof montar>, texto: string) {
  const input = wrapper.get("input");
  await input.setValue(texto);
  await vi.advanceTimersByTimeAsync(300);
  await flushPromises();
}

let montados: ReturnType<typeof montar>[] = [];

beforeEach(() => {
  vi.useFakeTimers();
  apiGet.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  // Se desmonta antes de limpiar: si se borra el body con nodos de Vue
  // pendientes, el patch del Teleport explota.
  montados.forEach((w) => w.unmount());
  montados = [];
  document.querySelectorAll(".spare-picker__menu").forEach((el) => el.remove());
});

describe("SparePartPicker", () => {
  it("pregunta si el catálogo aplica y lo avisa", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/spare-parts/status") {
        return Promise.resolve({ disponible: true, motivo: null, falla: false });
      }
      return Promise.resolve({ disponible: true, aviso: null, items: [] });
    });

    const wrapper = montar();
    await flushPromises();

    expect(apiGet).toHaveBeenCalledWith("/spare-parts/status");
    expect(wrapper.emitted("availability")?.[0]).toEqual([true]);
  });

  it("busca al escribir y muestra las opciones", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/spare-parts/status") {
        return Promise.resolve({ disponible: true, motivo: null, falla: false });
      }
      return Promise.resolve({ disponible: true, aviso: null, items: [PARTE] });
    });

    const wrapper = montar();
    await flushPromises();
    await escribir(wrapper, "adaptador");

    expect(apiGet).toHaveBeenCalledWith("/spare-parts/search", {
      params: { q: "adaptador", limit: 12 },
    });
    expect(menu()).not.toBeNull();
    expect(document.body.textContent).toContain(
      "ADAPTADOR TRIPLE PIRAMIDAL CHATO NEGRO",
    );
    // El precio se muestra formateado en locale es-AR.
    expect(document.body.textContent).toContain("2.160");
  });

  it("el desplegable va por Teleport, para que el modal no lo recorte", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/spare-parts/status") {
        return Promise.resolve({ disponible: true, motivo: null, falla: false });
      }
      return Promise.resolve({ disponible: true, aviso: null, items: [PARTE] });
    });

    const wrapper = montar();
    await flushPromises();
    await escribir(wrapper, "adaptador");

    // Esta fuera del wrapper (que es lo que lo salva del overflow del modal).
    expect(wrapper.find(".spare-picker__menu").exists()).toBe(false);
    expect(menu()).not.toBeNull();
    expect(menu()?.getAttribute("style")).toContain("position: fixed");
  });

  it("elegir una opción avisa la descripción y la parte", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/spare-parts/status") {
        return Promise.resolve({ disponible: true, motivo: null, falla: false });
      }
      return Promise.resolve({ disponible: true, aviso: null, items: [PARTE] });
    });

    const wrapper = montar();
    await flushPromises();
    await escribir(wrapper, "adaptador");

    clic(opciones()[0]);

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([
      "ADAPTADOR TRIPLE PIRAMIDAL CHATO NEGRO",
    ]);
    const change = wrapper.emitted("change")?.at(-1) as any[];
    expect(change[0].part.code).toBe("05589");
    expect(change[0].part.price_source).toBe("flexxus:PRECIOVENTA1");
  });

  it("si el texto coincide con una opción, la toma sola", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/spare-parts/status") {
        return Promise.resolve({ disponible: true, motivo: null, falla: false });
      }
      return Promise.resolve({ disponible: true, aviso: null, items: [PARTE] });
    });

    const wrapper = montar();
    await flushPromises();
    await escribir(wrapper, "adaptador triple piramidal chato negro");

    const change = wrapper.emitted("change")?.at(-1) as any[];
    expect(change[0].part.code).toBe("05589");
  });

  it("editar el texto después de elegir invalida la selección", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/spare-parts/status") {
        return Promise.resolve({ disponible: true, motivo: null, falla: false });
      }
      return Promise.resolve({ disponible: true, aviso: null, items: [PARTE] });
    });

    const wrapper = montar();
    await flushPromises();
    await escribir(wrapper, "adaptador");
    clic(opciones()[0]);
    expect((wrapper.emitted("change")?.at(-1) as any[])[0].part).not.toBeNull();

    // El operador corrige el texto a mano: la eleccion deja de valer.
    const input = wrapper.get("input");
    await input.setValue("ADAPTADOR TRIPLE PIRAMIDAL");
    await vi.advanceTimersByTimeAsync(300);
    await flushPromises();

    const change = wrapper.emitted("change")?.at(-1) as any[];
    expect(change[0].part).toBeNull();
  });

  it("si el ERP no responde, degrada a texto libre con aviso", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/spare-parts/status") {
        return Promise.resolve({ disponible: true, motivo: null, falla: false });
      }
      return Promise.resolve({
        disponible: false,
        aviso: "No se pudo consultar el catálogo de repuestos en Flexxus.",
        items: [],
      });
    });

    const wrapper = montar();
    await flushPromises();
    await escribir(wrapper, "adaptador");

    expect(wrapper.emitted("availability")?.at(-1)).toEqual([false]);
    expect(wrapper.text()).toContain("No se pudo consultar el catálogo");
    expect(menu()).toBeNull();
  });

  it("si la empresa no tiene el módulo, no busca, no avisa y deja escribir a mano", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/spare-parts/status") {
        return Promise.resolve({
          disponible: false,
          motivo: "El catálogo de repuestos no está disponible para esta empresa.",
          falla: false,
        });
      }
      return Promise.resolve({ disponible: true, aviso: null, items: [PARTE] });
    });

    const wrapper = montar();
    await flushPromises();
    await escribir(wrapper, "adaptador");

    expect(wrapper.emitted("availability")?.[0]).toEqual([false]);
    // No se busco en el ERP: la busqueda solo dispara al escribir.
    const llamadas = apiGet.mock.calls.map((c) => c[0]);
    expect(llamadas).not.toContain("/spare-parts/search");
    // Y no se molesta al operador con un aviso: que la empresa no tenga el
    // modulo es el estado normal, no una falla.
    expect(wrapper.text()).not.toContain("no está disponible");
  });

  it("si al modulo le corresponde y falla, avisa", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/spare-parts/status") {
        return Promise.resolve({
          disponible: false,
          motivo: "No hay credencial de Flexxus configurada en el servidor.",
          falla: true,
        });
      }
      return Promise.resolve({ disponible: true, aviso: null, items: [PARTE] });
    });

    const wrapper = montar();
    await flushPromises();

    expect(wrapper.text()).toContain("No hay credencial de Flexxus");
  });
});
