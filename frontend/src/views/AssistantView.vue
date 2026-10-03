<script setup lang="ts">
/**
 * Pantalla del asistente (#44, sub-issue 7).
 *
 * Tres cosas que el issue pide y que aca se cumplimiento de verdad:
 *
 * 1. **Nunca se ve una accion a punto de ejecutarse sin haberla confirmada.** El modelo nunca
 *    ejecuta: deja una propuesta, y la unica forma de aplicarla es el dialogo, con un boton
 *    explicito. No hay ningun camino donde apretar "enviar" aplique algo.
 * 2. **El panel dice por que la IA no esta.** Sin sacarlo del sistema: la pantalla explica y
 *    el resto de la aplicacion sigue igual. Si la IA no esta contratada, se dice y se termina.
 * 3. **La interfaz se opera completa sin IA.** Esta pantalla es un adicional; las demas no
 *    dependen de que haya IA.
 */
import { computed, nextTick, onMounted, ref } from "vue";
import {
  aiChat,
  aiConfirmarPropuesta,
  aiPropuestas,
  aiRechazarPropuesta,
  aiStatus,
  motivoLegible,
  type AiStatus,
  type ChatResponse,
  type ChatTurn,
  type Ficha,
  type Propuesta,
} from "../lib/ai";
import { getApiErrorMessage } from "../lib/api";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";
import AiDataCard from "../components/assistant/AiDataCard.vue";
import AiProposalDialog from "../components/assistant/AiProposalDialog.vue";

interface Burbuja {
  id: number;
  role: "user" | "assistant";
  texto: string;
  ficha?: Ficha;
  consulto?: boolean;
  saneado?: boolean;
  herramientas?: ChatResponse["tool_calls"];
  error?: string | null;
}

const session = useSessionStore();
const toast = useToastStore();

const status = ref<AiStatus | null>(null);
const burbujas = ref<Burbuja[]>([]);
const historial = ref<ChatTurn[]>([]);
const texto = ref("");
const conHerramientas = ref(true);
const enviando = ref(false);
const cargando = ref(false);

const propuestas = ref<Propuesta[]>([]);
const aConfirmar = ref<Propuesta | null>(null);
const aplicando = ref(false);

const scroll = ref<HTMLElement | null>(null);
let siguienteId = 1;

const pendiente = computed(() => propuestas.value.filter((p) => p.status === "pendiente"));

/** El motivo por el que la IA no esta disponible, ya en castellano. */
const motivo = computed(() => {
  if (!status.value) return null;
  if (status.value.available) return null;
  return motivoLegible(status.value.reason) ?? "La IA no está disponible en este momento.";
});

const habilitada = computed(() => status.value?.enabled === true);
const disponible = computed(() => status.value?.available === true);

const ETIQUETAS_HERRAMIENTA: Record<string, string> = {
  buscar_cliente: "buscar clientes",
  buscar_equipo: "buscar equipos",
  consultar_historial_equipo: "ver historial de un equipo",
  crear_cliente: "dar de alta clientes",
  crear_equipo: "registrar equipos",
  crear_ot: "abrir órdenes de trabajo",
  actualizar_ot: "modificar órdenes",
  agregar_diagnostico: "guardar diagnósticos",
  agregar_trabajo: "sumar trabajo",
  agregar_repuesto: "sumar repuestos",
};

async function cargar() {
  if (!session.activeCompany) return;
  cargando.value = true;
  try {
    status.value = await aiStatus();
    propuestas.value = await aiPropuestas();
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo consultar el estado de la IA"), "error");
  } finally {
    cargando.value = false;
  }
}

async function irAbajo() {
  await nextTick();
  if (scroll.value) scroll.value.scrollTop = scroll.value.scrollHeight;
}

async function enviar() {
  const pregunta = texto.value.trim();
  if (!pregunta || enviando.value || !disponible.value) return;

  const turno: ChatTurn = { role: "user", content: pregunta };
  burbujas.value.push({ id: siguienteId++, role: "user", texto: pregunta });
  historial.value = [...historial.value, turno];
  texto.value = "";
  enviando.value = true;
  await irAbajo();

  try {
    const r = await aiChat(historial.value, conHerramientas.value);
    burbujas.value.push({
      id: siguienteId++,
      role: "assistant",
      texto: r.text,
      ficha: r.ficha,
      consulto: r.consulto,
      saneado: r.texto_saneado,
      herramientas: r.tool_calls,
      error: motivoLegible(r.reason),
    });
    // Se manda de vuelta el texto que el operador vio, que es el ya saneado. Mandar el crudo
    // volveria a meter en el contexto los numeros que el backend descarto.
    historial.value = [...historial.value, { role: "assistant", content: r.text }];
    if (r.propuestas?.length) {
      propuestas.value = await aiPropuestas();
    }
  } catch (e) {
    burbujas.value.push({
      id: siguienteId++,
      role: "assistant",
      texto: "",
      error: getApiErrorMessage(e, "No se pudo completar la consulta."),
    });
  } finally {
    enviando.value = false;
    await irAbajo();
  }
}

async function confirmar(argumentos: Record<string, unknown>) {
  if (!aConfirmar.value) return;
  aplicando.value = true;
  try {
    const r = await aiConfirmarPropuesta(aConfirmar.value.id, argumentos);
    if (r.ya_se_habia_aplicado) {
      toast.push("Esa propuesta ya se había aplicado antes.", "success");
    } else {
      toast.push("Acción aplicada.", "success");
    }
    aConfirmar.value = null;
    propuestas.value = await aiPropuestas();
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo aplicar la propuesta"), "error");
  } finally {
    aplicando.value = false;
  }
}

async function rechazar(p: Propuesta) {
  try {
    await aiRechazarPropuesta(p.id);
    propuestas.value = await aiPropuestas();
    toast.push("Propuesta descartada.", "success");
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo descartar la propuesta"), "error");
  }
}

onMounted(cargar);
</script>

<template>
  <div class="page-stack">
    <!-- Estado: si la IA no esta, se dice por que y se termina. -->
    <div v-if="cargando" class="card text-muted">Cargando…</div>

    <div v-else-if="!habilitada" class="card aviso aviso--off">
      <div class="aviso__titulo">La IA no está contratada para esta empresa</div>
      <p class="aviso__texto">
        Un administrador puede prenderla desde <strong>Parámetros → Inteligencia artificial</strong>.
        Mientras tanto, el resto del sistema funciona igual.
      </p>
    </div>

    <div v-else-if="!disponible" class="card aviso aviso--warn">
      <div class="aviso__titulo">La IA no está disponible ahora</div>
      <p class="aviso__texto">{{ motivo }}</p>
    </div>

    <template v-else>
      <div class="card">
        <div class="flex flex--between flex--center gap-12">
          <div>
            <h2 class="card__title">Asistente</h2>
            <p class="text-secondary">
              Preguntale por clientes, equipos e historial. Para cambiar algo del sistema te va a
              proponer una acción y vos la confirmás.
            </p>
          </div>
          <label class="switchIA" title="Permitir que consulte y proponga acciones">
            <input v-model="conHerramientas" type="checkbox" />
            <span></span>
            <em>Con herramientas</em>
          </label>
        </div>

        <div v-if="status" class="ayuda">
          <span class="text-muted">Puede:</span>
          <span v-for="h in status.herramientas" :key="h" class="badge badge--muted">
            {{ ETIQUETAS_HERRAMIENTA[h] ?? h }}
          </span>
          <span v-if="!status.herramientas.length" class="text-muted">
            todavía no hay herramientas disponibles para tu usuario.
          </span>
        </div>
      </div>

      <!-- Propuestas esperando: lo unico que puede cambiar el sistema, siempre a la vista. -->
      <div v-if="pendiente.length" class="card">
        <h3 class="card__title">
          Acciones esperando tu confirmación
          <span class="badge badge--warning">{{ pendiente.length }}</span>
        </h3>
        <p class="text-secondary">
          Nada de esto se aplicó todavía. Abrilo, revisalo y confirmá lo que quieras dejar.
        </p>
        <ul class="lista-prop">
          <li v-for="p in pendiente" :key="p.id" class="prop-item">
            <div class="prop-item__info">
              <strong>{{ p.tool }}</strong>
              <span class="text-muted">
                N° {{ p.id }} ·
                <template v-if="p.riesgo === 'financiero'">mueve plata · </template>
                <template v-if="p.riesgo === 'comunicacion'">avisa al cliente · </template>
                {{ p.creada_en?.slice(11, 16) }}
              </span>
            </div>
            <div class="prop-item__acciones">
              <button class="btn btn--ghost btn--sm" @click="rechazar(p)">Descartar</button>
              <button class="btn btn--primary btn--sm" @click="aConfirmar = p">
                Revisar
              </button>
            </div>
          </li>
        </ul>
      </div>

      <!-- Conversacion -->
      <div class="card chat">
        <div ref="scroll" class="chat__scroll">
          <div v-if="!burbujas.length" class="empty-state">
            Escribí una pregunta. Podés pedir datos, o pedir un cambio: en ese caso te va a
            proponer la acción y vos la confirmás.
          </div>
          <div v-for="b in burbujas" :key="b.id" :class="['msg', `msg--${b.role}`]">
            <div v-if="b.role === 'assistant' && !b.texto && !b.ficha?.bloques?.length && !b.error" class="msg__vacio" />
            <template v-else>
              <!-- La ficha va antes del texto: es la fuente, el texto es comentario. -->
              <AiDataCard v-if="b.ficha && b.ficha.bloques.length" :ficha="b.ficha" />
              <p v-if="b.texto" class="msg__texto">{{ b.texto }}</p>
              <p v-if="b.error" class="msg__error">{{ b.error }}</p>
              <p v-if="b.consulto === false && b.herramientas?.length === 0" class="msg__aviso">
                No consultó la base en esta respuesta, así que no te puede decir nada de tus
                datos.
              </p>
            </template>
          </div>
          <div v-if="enviando" class="msg msg--assistant"><span class="spinner" /> Pensando…</div>
        </div>

        <form class="chat__form" @submit.prevent="enviar">
          <input
            v-model="texto"
            :disabled="enviando"
            placeholder="Preguntale al asistente…"
            aria-label="Mensaje para el asistente"
          />
          <button class="btn btn--primary" :disabled="enviando || !texto.trim()" type="submit">
            Enviar
          </button>
        </form>
      </div>
    </template>

    <AiProposalDialog
      :open="aConfirmar !== null"
      :propuesta="aConfirmar"
      :busy="aplicando"
      @close="aConfirmar = null"
      @confirmar="confirmar"
    />
  </div>
</template>

<style scoped>
.page-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.aviso {
  border-left: 3px solid;
}
.aviso--off {
  border-left-color: var(--color-border-strong, #475569);
  background: rgba(148, 163, 184, 0.06);
}
.aviso--warn {
  border-left-color: var(--color-warning, #f59e0b);
  background: rgba(245, 158, 11, 0.1);
}
.aviso__titulo {
  font-weight: 600;
  margin-bottom: 6px;
}
.aviso__texto {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary, #cbd5e1);
}
.ayuda {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.15);
}
.switchIA {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  cursor: pointer;
}
.switchIA em {
  font-style: normal;
  font-size: 13px;
  color: var(--color-text-secondary, #cbd5e1);
}
.switchIA input {
  position: absolute;
  opacity: 0;
}
.switchIA span {
  display: block;
  width: 42px;
  height: 24px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.35);
  position: relative;
  transition: 0.15s;
}
.switchIA span::after {
  content: "";
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  top: 3px;
  border-radius: 50%;
  background: #fff;
  transition: 0.15s;
}
.switchIA input:checked + span {
  background: var(--color-primary, #3b82f6);
}
.switchIA input:checked + span::after {
  transform: translateX(18px);
}
.lista-prop {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.prop-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 10px;
  background: rgba(245, 158, 11, 0.07);
}
.prop-item__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.prop-item__info span {
  font-size: 12px;
}
.prop-item__acciones {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.chat__scroll {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 58vh;
  overflow-y: auto;
  padding: 4px 2px 12px;
}
.msg {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 92%;
}
.msg--user {
  align-self: flex-end;
  align-items: flex-end;
}
.msg--user .msg__texto {
  background: var(--color-primary, #3b82f6);
  color: #fff;
  padding: 10px 14px;
  border-radius: 14px 14px 4px 14px;
  margin: 0;
  max-width: 100%;
}
.msg--assistant {
  align-self: flex-start;
}
.msg__texto {
  margin: 0;
  padding: 10px 14px;
  border-radius: 14px 14px 14px 4px;
  background: rgba(148, 163, 184, 0.1);
  color: var(--color-text-primary, #e5edf7);
  max-width: 100%;
}
.msg__error {
  margin: 0;
  font-size: 13px;
  color: var(--color-danger, #ef4444);
}
.msg__aviso {
  margin: 0;
  font-size: 12px;
  color: var(--color-warning, #f59e0b);
}
.msg__vacio {
  min-height: 2px;
}
.chat__form {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.15);
}
.chat__form input {
  flex: 1;
  background: #10283f;
  color: #e5edf7;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 10px;
  padding: 10px 12px;
  color-scheme: dark;
}
.chat__form input:disabled {
  opacity: 0.6;
}
@media (max-width: 640px) {
  .prop-item {
    flex-direction: column;
    align-items: stretch;
  }
  .prop-item__acciones {
    justify-content: flex-end;
  }
}
</style>
