import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import WorkOrderStatusesView from "../views/WorkOrderStatusesView.vue";

const apiGet = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async () => {
  const real: any = await vi.importActual("../lib/api");
  return { ...real, apiGet, apiPatch, apiPost, getApiErrorMessage: () => "error simulado" };
});

function estado(id: number, name: string, extra: Record<string, unknown> = {}) {
  return {
    id, name, color: "#3B82F6", sort_order: id * 10, active: true,
    is_initial: false, is_final: false, marks_quoted: false, marks_awaiting_quote_approval: false,
    marks_repair: false, marks_waiting_parts: false, marks_completed: false, marks_delivered: false,
    notify_whatsapp: false, notify_email: false, notifications_active: true,
    notification_template: null, notification_email_subject: null,
    ...extra,
  };
}

async function montar() {
  setActivePinia(createPinia());
  const wrapper = mount(WorkOrderStatusesView, { global: { stubs: { teleport: true } } });
  await flushPromises();
  return wrapper;
}

const filas = (w: any) => w.findAll("article.fila");
const flag = (fila: any, texto: string) => fila.findAll("label.flag").find((l: any) => l.text().startsWith(texto))!;

describe("pantalla de estados de OT", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockImplementation((url: string) => {
      if (url.includes("variables")) return Promise.resolve({ variables: ["cliente", "numero_ot", "equipo", "estado"] });
      return Promise.resolve([
        estado(1, "Recibido"),
        estado(2, "Esperando repuesto", { marks_waiting_parts: true }),
      ]);
    });
    // El backend devuelve lo que se mando (con id).
    apiPatch.mockImplementation((_url: string, body: any) => Promise.resolve({ ...body }));
  });

  it("guardar una fila no descarta lo editado en otra", async () => {
    const w = await montar();
    await filas(w)[0].find("input[id^=nombre]").setValue("Recibido en taller");
    await filas(w)[1].find("input[id^=nombre]").setValue("Frenada");

    await filas(w)[0].findAll("button").find((b: any) => b.text() === "Guardar cambios")!.trigger("click");
    await flushPromises();

    expect((filas(w)[1].find("input[id^=nombre]").element as HTMLInputElement).value).toBe("Frenada");
    expect(w.text()).toContain("Tenés 1 estado sin guardar");
    expect(apiGet).toHaveBeenCalledTimes(2); // la carga inicial y las variables, nada mas
  });

  it("avisa de donde se va a quitar un flag exclusivo y lo saca al guardar", async () => {
    const w = await montar();
    expect(flag(filas(w)[0], "Espera repuesto").text()).toContain("Hoy en: “Esperando repuesto”");

    await flag(filas(w)[0], "Espera repuesto").find("input").setValue(true);
    expect(flag(filas(w)[0], "Espera repuesto").text()).toContain("Se va a quitar de “Esperando repuesto” al guardar");

    await filas(w)[0].findAll("button").find((b: any) => b.text() === "Guardar cambios")!.trigger("click");
    await flushPromises();

    const otra = filas(w)[1];
    expect((flag(otra, "Espera repuesto").find("input").element as HTMLInputElement).checked).toBe(false);
    expect(otra.text()).toContain("Guardado");
    expect(w.text()).not.toContain("sin guardar");
  });

  it("sin canal elegido el aviso sale apagado", async () => {
    const w = await montar();
    await filas(w)[0].find("input[id^=nombre]").setValue("Otro nombre");
    await filas(w)[0].findAll("button").find((b: any) => b.text() === "Guardar cambios")!.trigger("click");
    await flushPromises();

    expect(apiPatch).toHaveBeenCalledWith("/work-orders/statuses/1", expect.objectContaining({ notifications_active: false }));
  });

  it("la vista previa resuelve las variables y marca las que no existen", async () => {
    const w = await montar();
    const fila = filas(w)[0];
    await fila.findAll(".canales input")[0].setValue(true);
    await fila.find("textarea").setValue("Hola {{cliente}}, OT {{numero_ot}} {{clinete}}");

    const previa = fila.find(".previa p");
    expect(previa.text()).toBe("Hola Lucía Benítez, OT 4318 {{clinete}}");
    expect(previa.find("mark").text()).toBe("{{clinete}}");
    expect(fila.text()).toContain("No existe: {{clinete}}");
  });
});
