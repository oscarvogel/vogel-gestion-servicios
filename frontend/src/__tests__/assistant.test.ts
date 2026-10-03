import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { motivoLegible, type ChatResponse, type Propuesta } from "../lib/ai";
import { useSessionStore } from "../stores/session";
import AssistantView from "../views/AssistantView.vue";
import AiProposalDialog from "../components/assistant/AiProposalDialog.vue";

// Se reexporta el modulo real y se pisa solo lo que hace falta. Si se reemplaza entero, el
// store de sesion se queda sin TOKEN_KEY y revienta al crearse.
vi.mock("../lib/api", async () => {
  const real: any = await vi.importActual("../lib/api");
  return { ...real, getApiErrorMessage: () => "error simulado" };
});

const chat = vi.hoisted(() => vi.fn());
const propuestas = vi.hoisted(() => vi.fn());
const confirmar = vi.hoisted(() => vi.fn());
const rechazar = vi.hoisted(() => vi.fn());

vi.mock("../lib/ai", async () => {
  const real: any = await vi.importActual("../lib/ai");
  return {
    ...real,
    aiStatus: vi.fn(),
    aiChat: chat,
    aiPropuestas: propuestas,
    aiConfirmarPropuesta: confirmar,
    aiRechazarPropuesta: rechazar,
  };
});

const { aiStatus } = await import("../lib/ai");

function estado(over: Record<string, unknown> = {}) {
  return {
    enabled: true,
    available: true,
    reason: null,
    provider: "minimax",
    model: "MiniMax-M3",
    herramientas: ["buscar_cliente", "crear_cliente"],
    usage: {
      requests: 0, registros: 0, cost_usd: 0, input_tokens: 0, output_tokens: 0,
      monthly_quota_usd: 0, monthly_request_limit: 0, previous_month_cost_usd: 0,
    },
    ...over,
  };
}

function propuesta(over: Partial<Propuesta> = {}): Propuesta {
  return {
    id: 1,
    tool: "crear_cliente",
    status: "pendiente",
    riesgo: "ninguno",
    notifica_cliente: false,
    notificado: false,
    argumentos_propuestos: { nombre: "Propuesto", telefono: "111" },
    argumentos_confirmados: null,
    lo_que_cambio: null,
    resultado: null,
    error: null,
    propuesta_por: 1,
    confirmada_por: null,
    confirmada_en: null,
    aplicada_en: null,
    creada_en: "2026-10-03T12:00:00",
    ...over,
  };
}

async function montar() {
  const pinia = createPinia();
  setActivePinia(pinia);
  // La vista no carga nada sin empresa activa, asi que hay que dejar una sesion armada.
  const session = useSessionStore();
  session.me = {
    id: 1,
    email: "op@ejemplo.com",
    full_name: "Operador",
    is_superadmin: false,
    active: true,
    memberships: [
      {
        company_id: 6, company_name: "Prueba Docs", company_slug: "prueba-docs",
        company_active: true, is_admin: true, role: "ADMIN", active: true,
      },
    ],
    permissions: ["ai.use", "customers.view", "equipment.view", "work_orders.view"],
  };
  session.persistActiveCompany({
    id: 6, name: "Prueba Docs", slug: "prueba-docs", active: true, is_admin: true,
  });
  const w = mount(AssistantView, { global: { plugins: [pinia] } });
  await flushPromises();
  return w;
}

beforeEach(() => {
  vi.clearAllMocks();
  (aiStatus as any).mockResolvedValue(estado());
  propuestas.mockResolvedValue([]);
  chat.mockResolvedValue({
    ok: true, status: "disponible", text: "Listo.", provider: "minimax", model: "MiniMax-M3",
    reason: null, detail: null, tool_calls: [], ficha: { bloques: [], consultas: [] },
    consulto: false, texto_saneado: false, propuestas: [],
  } as ChatResponse);
  localStorage.clear();
});

describe("la pantalla del asistente", () => {
  it("muestra por que la IA no esta disponible, sin sacarlo del sistema", async () => {
    (aiStatus as any).mockResolvedValue(
      estado({ available: false, reason: "proveedor_caido", herramientas: [] }),
    );
    const w = await montar();
    expect(w.text()).toContain("La IA no está disponible ahora");
    // El motivo tiene que ser el real, translated, no un codigo.
    expect(w.text()).toContain("Podés seguir trabajando normalmente");
    // Y no hay caja de chat: no se puede mandar nada que no sirva.
    expect(w.find("form.chat__form").exists()).toBe(false);
  });

  it("distingue 'no esta contratada' de 'esta caida'", async () => {
    (aiStatus as any).mockResolvedValue(estado({ enabled: false, available: false, reason: "no_habilitado" }));
    const w = await montar();
    expect(w.text()).toContain("no está contratada");
    expect(w.text()).not.toContain("La IA no está disponible ahora");
  });

  it("lista las herramientas disponibles en contexto", async () => {
    const w = await montar();
    expect(w.text()).toContain("Puede:");
    expect(w.text()).toContain("buscar clientes");
    expect(w.text()).toContain("dar de alta clientes");
  });

  it("avisa cuando la IA no consulto nada, para que no parezca que consulto", async () => {
    const w = await montar();
    await w.find("form.chat__form input").setValue("hola");
    await w.find("form.chat__form").trigger("submit");
    await flushPromises();
    expect(w.text()).toContain("No consultó la base en esta respuesta");
  });
});

describe("las propuestas nunca se aplican solas", () => {
  it("una propuesta pendiente aparece y NO se aplica al mandar un mensaje", async () => {
    propuestas.mockResolvedValue([propuesta()]);
    const w = await montar();
    expect(w.text()).toContain("Acciones esperando tu confirmación");
    expect(w.text()).toContain("Nada de esto se aplicó todavía");

    chat.mockResolvedValue({
      ok: true, status: "disponible", text: "Propuse el alta.", provider: "minimax",
      model: "MiniMax-M3", reason: null, detail: null, tool_calls: [],
      ficha: { bloques: [], consultas: [] }, consulto: false, texto_saneado: false,
    } as ChatResponse);

    await w.find("form.chat__form input").setValue("dale de alta a Propuesto");
    await w.find("form.chat__form").trigger("submit");
    await flushPromises();

    // Mandar el mensaje no confirma nada: la unica llamada de escritura posible es la del dialogo.
    expect(confirmar).not.toHaveBeenCalled();
    expect(chat).toHaveBeenCalledTimes(1);
  });

  it("no hay ningun boton que aplique una propuesta fuera del dialogo", async () => {
    propuestas.mockResolvedValue([propuesta()]);
    const w = await montar();
    // Los unicos botones sobre la propuesta son Descartar y Revisar.
    const textos = w.findAll(".prop-item button").map((b) => b.text());
    expect(textos).toEqual(["Descartar", "Revisar"]);
  });

  it("confirmar manda los argumentos editados, no los propuestos", async () => {
    const w = mount(AiProposalDialog, {
      props: { open: true, propuesta: propuesta() },
      global: { stubs: { teleport: true } },
    });
    const nombre = w.find('input[type="text"]');
    await nombre.setValue("Corregido a Mano");
    await w.find("button.btn--primary").trigger("click");

    const emitidos = w.emitted("confirmar");
    expect(emitidos).toBeTruthy();
    expect(emitidos![0][0]).toEqual({ nombre: "Corregido a Mano", telefono: "111" });
  });

  it("el dialogo avisa del riesgo antes de dejar confirmar", async () => {
    const w = mount(AiProposalDialog, {
      props: {
        open: true,
        propuesta: propuesta({ riesgo: "financiero", tool: "agregar_repuesto" }),
      },
      global: { stubs: { teleport: true } },
    });
    expect(w.text()).toContain("Mueve plata");
    expect(w.find("button.btn--primary").exists()).toBe(true);
  });

  it("el dialogo avisa que se le avisa al cliente antes de confirmar", async () => {
    const w = mount(AiProposalDialog, {
      props: {
        open: true,
        propuesta: propuesta({ riesgo: "comunicacion", notifica_cliente: true, tool: "actualizar_ot" }),
      },
      global: { stubs: { teleport: true } },
    });
    expect(w.text()).toContain("no se puede deshacer");
  });

  it("al cambiar de propuesta se borra la edicion anterior", async () => {
    const w = mount(AiProposalDialog, {
      props: { open: true, propuesta: propuesta() },
      global: { stubs: { teleport: true } },
    });
    await w.find('input[type="text"]').setValue("Editado de la primera");
    await w.setProps({
      propuesta: propuesta({ id: 2, argumentos_propuestos: { nombre: "Otra propuesta" } }),
    });
    await flushPromises();
    expect((w.find('input[type="text"]').element as HTMLInputElement).value).toBe("Otra propuesta");
  });
});

describe("la ficha va antes del texto del modelo", () => {
  it("renderiza la ficha y el texto del modelo por separado", async () => {
    chat.mockResolvedValue({
      ok: true, status: "disponible",
      text: "El asistente comento la respuesta; el detalle esta en la ficha de arriba.",
      provider: "minimax", model: "MiniMax-M3", reason: null, detail: null,
      tool_calls: [{ name: "buscar_cliente", ok: true, error: null, repetida: false }],
      ficha: {
        bloques: [{
          tipo: "buscar_cliente", titulo: "Clientes encontrados", vacio: false,
          resultados: [{ id: 7, nombre: "Cliente Real", telefono: "123" }],
        }],
        consultas: [{ herramienta: "buscar_cliente", tiene_datos: true }],
      },
      consulto: true, texto_saneado: true,
    } as ChatResponse);

    const w = await montar();
    await w.find("form.chat__form input").setValue("buscame a Cliente Real");
    await w.find("form.chat__form").trigger("submit");
    await flushPromises();

    // La ficha esta, con el dato real de la base.
    expect(w.text()).toContain("Cliente Real");
    // Y el texto del modelo va aparte, sin los numeros que el backend descarto.
    expect(w.text()).toContain("el detalle esta en la ficha");
    // Y la ficha se dibuja antes que el texto del modelo. Se mide dentro de la burbuja del
    // asistente: la clase msg__texto la usa tambien el mensaje del usuario, que va primero.
    const htmlAsistente = w.find(".msg--assistant").html();
    expect(htmlAsistente.indexOf("ficha__rotulo")).toBeLessThan(
      htmlAsistente.indexOf("msg__texto"),
    );
  });
});

describe("los motivos tienen que ser entendibles", () => {
  it("traduce los motivos del backend", () => {
    expect(motivoLegible("no_habilitado")).toContain("contratada");
    expect(motivoLegible("proveedor_caido")).toContain("seguir trabajando");
    expect(motivoLegible("cuota_excedida")).toContain("cuota mensual");
    expect(motivoLegible("sin_permiso")).toContain("permiso");
  });

  it("un motivo desconocido no se traga, se muestra tal cual", () => {
    expect(motivoLegible("motivo_nuevo_del_backend")).toBe("motivo_nuevo_del_backend");
    expect(motivoLegible(null)).toBeNull();
  });
});
