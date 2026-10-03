/** Tipos y llamadas del modulo de IA. */
import { apiGet, apiPost } from "./api";

export interface AiUsage {
  requests: number;
  registros: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  monthly_quota_usd: number;
  monthly_request_limit: number;
  previous_month_cost_usd: number;
}

export interface AiStatus {
  enabled: boolean;
  available: boolean;
  reason: string | null;
  provider: string | null;
  model: string | null;
  herramientas: string[];
  usage: AiUsage;
}

export interface FichaBloque {
  tipo: string;
  titulo: string;
  vacio: boolean;
  detalle?: string | null;
  resultados?: Record<string, unknown>[];
  equipo?: Record<string, unknown> | null;
  cantidad_de_ordenes?: number;
  historial?: HistorialOrden[];
}

export interface Ficha {
  bloques: FichaBloque[];
  consultas: { herramienta: string; tiene_datos: boolean }[];
}

export interface HistorialOrden {
  orden: number;
  estado: string;
  recibida: string | null;
  entrega_estimada: string | null;
  completada: string | null;
  entregada: string | null;
  falla_reportada: string;
}

export interface Propuesta {
  id: number;
  tool: string;
  status: string;
  riesgo: string;
  notifica_cliente: boolean;
  notificado: boolean;
  argumentos_propuestos: Record<string, unknown>;
  argumentos_confirmados: Record<string, unknown> | null;
  lo_que_cambio: Record<string, unknown> | null;
  resultado: Record<string, unknown> | null;
  error: string | null;
  propuesta_por: number;
  confirmada_por: number | null;
  confirmada_en: string | null;
  aplicada_en: string | null;
  creada_en: string | null;
}

export interface ChatResponse {
  ok: boolean;
  status: string;
  text: string;
  provider: string;
  model: string;
  reason: string | null;
  detail: string | null;
  tool_calls: { name: string; ok: boolean; error: string | null; repetida: boolean }[];
  ficha: Ficha;
  consulto: boolean;
  texto_saneado: boolean;
  propuestas?: Propuesta[];
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export function aiStatus(): Promise<AiStatus> {
  return apiGet<AiStatus>("/ai/status");
}

export function aiChat(
  messages: ChatTurn[],
  conHerramientas: boolean,
): Promise<ChatResponse> {
  return apiPost<ChatResponse>("/ai/chat", {
    messages: messages.map((m) => ({ role: m.role, content: m.content })),
    con_herramientas: conHerramientas,
  });
}

export function aiPropuestas(estado?: string): Promise<Propuesta[]> {
  const query = estado ? `?estado=${encodeURIComponent(estado)}` : "";
  return apiGet<Propuesta[]>(`/ai/propuestas${query}`);
}

export function aiConfirmarPropuesta(
  id: number,
  argumentos?: Record<string, unknown>,
): Promise<Propuesta & { ya_se_habia_aplicado?: boolean }> {
  return apiPost(`/ai/propuestas/${id}/confirmar`, {
    argumentos: argumentos ?? null,
  });
}

export function aiRechazarPropuesta(id: number): Promise<Propuesta> {
  return apiPost(`/ai/propuestas/${id}/rechazar`);
}

/** Motivos de no disponibilidad, en castellano. El operador tiene que entender por que. */
export const MOTIVOS: Record<string, string> = {
  no_habilitado:
    "La IA no está contratada para esta empresa. Un administrador puede prenderla desde Parámetros.",
  proveedor_sin_configurar:
    "La IA no tiene credencial cargada en la plataforma. Hay que avisarle al que administra el sistema.",
  proveedor_caido:
    "La IA está caída o no responde. Podés seguir trabajando normalmente: el resto del sistema no depende de ella.",
  cuota_excedida: "Se alcanzó la cuota mensual de IA de esta empresa.",
  en_curso: "La propuesta se está aplicando en este momento.",
  ya_resuelta: "Esa propuesta ya se resolvió.",
  sin_permiso: "Tu usuario no tiene permiso para esto.",
  argumentos_invalidos: "Los datos de la propuesta no sirven.",
  error_interno: "La consulta falló por un problema interno.",
  herramienta_desconocida: "La herramienta que se pidió no existe.",
  no_encontrado: "No encontré nada con eso.",
};

export function motivoLegible(motivo: string | null | undefined): string | null {
  if (!motivo) return null;
  return MOTIVOS[motivo] ?? motivo;
}
