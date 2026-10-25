<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { apiGet, apiPatch, apiPost, getApiErrorMessage } from "../lib/api";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";
import Modal from "../components/Modal.vue";

interface OtStatus {
  id: number;
  name: string;
  color: string;
  sort_order: number;
  active: boolean;
  is_initial: boolean;
  is_final: boolean;
  marks_quoted: boolean;
  marks_awaiting_quote_approval: boolean;
  marks_repair: boolean;
  marks_waiting_parts: boolean;
  marks_completed: boolean;
  notify_whatsapp: boolean;
  notify_email: boolean;
  notifications_active: boolean;
  notification_template: string | null;
  notification_email_subject: string | null;
  marks_delivered: boolean;
}
type NewStatus = Omit<OtStatus, "id">;
type FlagKey =
  | "is_initial" | "is_final" | "marks_quoted" | "marks_awaiting_quote_approval"
  | "marks_repair" | "marks_waiting_parts" | "marks_completed" | "marks_delivered";

const session = useSessionStore();
const toast = useToastStore();
const statuses = ref<OtStatus[]>([]);
const loading = ref(false);
const showNew = ref(false);

// `exclusive`: el backend deja el flag en un solo estado (EXCLUSIVE_STATUS_FLAGS e is_initial en
// work_orders.py) y lo saca en silencio del anterior; por eso la pantalla muestra donde esta hoy.
const FLAGS: { key: FlagKey; label: string; hint: string; exclusive: boolean; danger?: boolean }[] = [
  { key: "is_initial", label: "Inicial", hint: "Estado con el que arranca toda OT nueva.", exclusive: true },
  { key: "marks_quoted", label: "Presupuesto generado", hint: "La OT pasa sola a este estado al emitir un presupuesto.", exclusive: true },
  { key: "marks_awaiting_quote_approval", label: "Espera aprobación", hint: "Presupuesto enviado, sin respuesta del cliente. Cuenta en “Requieren atención”.", exclusive: true },
  { key: "marks_repair", label: "En reparación", hint: "Equipo en el banco del taller. Lo cuenta el Dashboard.", exclusive: true },
  { key: "marks_waiting_parts", label: "Espera repuesto", hint: "OT frenada por un repuesto. Cuenta en “Requieren atención”.", exclusive: true },
  { key: "marks_completed", label: "Finaliza trabajo", hint: "Registra la finalización técnica: la OT queda lista para entregar.", exclusive: true },
  { key: "marks_delivered", label: "Entrega equipo", hint: "Registra la entrega real al cliente.", exclusive: true },
  { key: "is_final", label: "Final", hint: "Cierra el ciclo: la OT ya no puede cambiar de estado, ni presupuestarse, ni cambiar la entrega prevista.", exclusive: false, danger: true },
];

// --- Cambios sin guardar ---------------------------------------------------------------
// Se guarda la ultima version confirmada por el backend de cada fila. Guardar una fila nunca
// recarga las demas: antes se recargaba todo y se perdia lo que estaba editado en otra.
const saved = ref<Record<number, OtStatus>>({});
// Claves ordenadas: la respuesta del PATCH puede traerlas en otro orden que la fila.
const snapshot = (st: OtStatus) => JSON.stringify(st, Object.keys(st).sort());
const isDirty = (st: OtStatus) => !saved.value[st.id] || snapshot(saved.value[st.id]) !== snapshot(st);
const dirtyRows = computed(() => statuses.value.filter(isDirty));

function ordenar() {
  statuses.value.sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
}

async function load() {
  loading.value = true;
  try {
    statuses.value = await apiGet<OtStatus[]>("/work-orders/statuses");
    saved.value = Object.fromEntries(statuses.value.map((st) => [st.id, { ...st }]));
  } catch (e) {
    toast.push(getApiErrorMessage(e), "error");
  } finally {
    loading.value = false;
  }
}

/** Lo que el backend hace con los flags exclusivos, aplicado aca sin recargar. */
function quitarFlagsDeOtros(fuente: OtStatus) {
  for (const f of FLAGS) {
    if (!f.exclusive || !fuente[f.key]) continue;
    for (const otro of statuses.value) {
      if (otro.id === fuente.id) continue;
      otro[f.key] = false;
      if (saved.value[otro.id]) saved.value[otro.id][f.key] = false;
    }
  }
}

// Los avisos estan activos cuando hay al menos un canal: tildado "activo" sin canal el
// backend no manda nada, y la pantalla lo mostraba como si mandara.
const conAviso = <T extends Pick<OtStatus, "notify_whatsapp" | "notify_email">>(st: T) => ({
  ...st,
  notifications_active: st.notify_whatsapp || st.notify_email,
});

const guardando = ref<number | null>(null);
async function save(st: OtStatus, avisar = true) {
  guardando.value = st.id;
  try {
    const r = await apiPatch<OtStatus>(`/work-orders/statuses/${st.id}`, conAviso(st));
    Object.assign(st, r);
    saved.value[st.id] = { ...r };
    quitarFlagsDeOtros(r);
    ordenar();
    if (avisar) toast.push(`“${r.name}” guardado`, "success");
    return true;
  } catch (e) {
    toast.push(getApiErrorMessage(e), "error");
    return false;
  } finally {
    guardando.value = null;
  }
}

async function saveAll() {
  const pendientes = [...dirtyRows.value];
  let ok = 0;
  for (const st of pendientes) if (await save(st, false)) ok++;
  if (ok) toast.push(ok === 1 ? "1 estado guardado" : `${ok} estados guardados`, "success");
}

// --- Orden -----------------------------------------------------------------------------
// Las flechas solo tocan el orden (PATCH parcial): no se lleva otros cambios sin guardar de
// la fila. Si los dos tienen el mismo numero, el que se mueve queda pegado al vecino.
async function mover(st: OtStatus, dir: -1 | 1) {
  const i = statuses.value.indexOf(st);
  const vecino = statuses.value[i + dir];
  if (!vecino) return;
  let a = vecino.sort_order;
  let b = st.sort_order;
  if (a === b) a = b + dir;
  try {
    await Promise.all([
      apiPatch(`/work-orders/statuses/${st.id}`, { sort_order: a }),
      apiPatch(`/work-orders/statuses/${vecino.id}`, { sort_order: b }),
    ]);
    st.sort_order = a;
    vecino.sort_order = b;
    if (saved.value[st.id]) saved.value[st.id].sort_order = a;
    if (saved.value[vecino.id]) saved.value[vecino.id].sort_order = b;
    ordenar();
  } catch (e) {
    toast.push(getApiErrorMessage(e), "error");
  }
}

// --- Flags: donde esta hoy cada uno ------------------------------------------------------
function duenio(key: FlagKey, excepto?: number) {
  return statuses.value.find((o) => o.id !== excepto && o[key]) ?? null;
}
function notaFlag(f: (typeof FLAGS)[number], marcado: boolean, id?: number): string {
  if (!f.exclusive) return "";
  const otro = duenio(f.key, id);
  if (!otro) return "";
  return marcado ? `Se va a quitar de “${otro.name}” al guardar.` : `Hoy en: “${otro.name}”.`;
}
function flagsSummary(st: OtStatus) {
  const on = FLAGS.filter((f) => st[f.key]).map((f) => f.label);
  return on.length ? on.join(" · ") : "Sin marcas";
}
function notifSummary(st: OtStatus) {
  const c = [st.notify_whatsapp && "WhatsApp", st.notify_email && "Email"].filter(Boolean);
  return c.length ? c.join(" · ") : "Sin aviso";
}

// --- Mensaje: variables y vista previa ---------------------------------------------------
// Copia de DEFAULT_TEMPLATE y PLACEHOLDER de backend/app/services/notifications/templates.py:
// con el mensaje vacio el backend manda ese texto.
const DEFAULT_TEMPLATE = "Hola {{cliente}}, tu orden de trabajo N° {{numero_ot}} ({{equipo}}) pasó a: {{estado}}.";
const PLACEHOLDER = /\{\{\s*([a-z_]+)\s*\}\}/g;
const templateVariables = ref<string[]>([]);
async function loadVariables() {
  try {
    templateVariables.value = (await apiGet<{ variables: string[] }>("/work-orders/notifications/variables")).variables;
  } catch {
    templateVariables.value = ["cliente", "numero_ot", "equipo", "estado"];
  }
}

function ejemplo(st: OtStatus): Record<string, string> {
  return {
    cliente: "Lucía Benítez",
    telefono: "351 555-1234",
    email_cliente: "lucia@ejemplo.com",
    numero_ot: "4318",
    equipo: "Lavarropas Drean 7 kg",
    equipo_serie: "SN 0042817",
    falla: "No centrifuga",
    estado: st.name || "Nuevo estado",
    estado_anterior: "Recibido",
    fecha_recepcion: "24/10/2026 10:30",
    fecha_prevista: "31/10/2026 18:00",
    fecha_finalizacion: "30/10/2026 16:15",
    fecha_entrega: "31/10/2026 11:00",
    empresa: session.activeCompany?.name ?? "Tu empresa",
    empresa_telefono: "351 400-0000",
    empresa_email: "taller@ejemplo.com",
  };
}

/** Partes del mensaje ya resuelto; `malo` marca una variable que no existe. */
function vistaPrevia(st: OtStatus, texto: string | null) {
  const plantilla = (texto ?? "").trim() || DEFAULT_TEMPLATE;
  const datos = ejemplo(st);
  const partes: { texto: string; malo: boolean }[] = [];
  let desde = 0;
  for (const m of plantilla.matchAll(PLACEHOLDER)) {
    partes.push({ texto: plantilla.slice(desde, m.index), malo: false });
    const conocida = templateVariables.value.includes(m[1]);
    partes.push({ texto: conocida ? (datos[m[1]] ?? `[${m[1]}]`) : m[0], malo: !conocida });
    desde = m.index! + m[0].length;
  }
  partes.push({ texto: plantilla.slice(desde), malo: false });
  return partes;
}
function variablesMalas(texto: string | null) {
  return [...(texto ?? "").matchAll(PLACEHOLDER)].map((m) => m[1]).filter((v) => !templateVariables.value.includes(v));
}

const listaMalas = (texto: string | null) => variablesMalas(texto).map((v) => `{{${v}}}`).join(", ");

const mensajes: Record<number, HTMLTextAreaElement | null> = {};
async function insertar(st: OtStatus, variable: string) {
  const el = mensajes[st.id];
  const actual = st.notification_template ?? "";
  const pos = el ? el.selectionStart : actual.length;
  const fin = el ? el.selectionEnd : actual.length;
  const token = `{{${variable}}}`;
  st.notification_template = actual.slice(0, pos) + token + actual.slice(fin);
  await nextTick();
  el?.focus();
  el?.setSelectionRange(pos + token.length, pos + token.length);
}

// --- Alta --------------------------------------------------------------------------------
const fresh = (): NewStatus => ({
  name: "", color: "#3B82F6", sort_order: (statuses.value.at(-1)?.sort_order ?? 0) + 10, active: true,
  is_initial: false, is_final: false, marks_quoted: false, marks_awaiting_quote_approval: false,
  marks_repair: false, marks_waiting_parts: false, marks_completed: false, marks_delivered: false,
  notify_whatsapp: false, notify_email: false, notifications_active: false,
  notification_template: null, notification_email_subject: null,
});
const newStatus = ref<NewStatus>(fresh());
function abrirNuevo() {
  newStatus.value = fresh();
  showNew.value = true;
}
async function create() {
  try {
    const r = await apiPost<OtStatus>("/work-orders/statuses", conAviso(newStatus.value));
    statuses.value.push(r);
    saved.value[r.id] = { ...r };
    quitarFlagsDeOtros(r);
    ordenar();
    showNew.value = false;
    toast.push(`Estado “${r.name}” creado`, "success");
  } catch (e) {
    toast.push(getApiErrorMessage(e), "error");
  }
}

onMounted(async () => {
  await load();
  await loadVariables();
});
</script>

<template>
  <div class="estados">
    <header class="heading">
      <div>
        <h1>Estados de órdenes de trabajo</h1>
        <p>Flujo propio de {{ session.activeCompany?.name }}. Así se ven los estados en el listado, en el detalle de las OT y en el Dashboard.</p>
      </div>
      <button class="btn btn--primary desktop-primary-action" type="button" @click="abrirNuevo">+ Nuevo estado</button>
      <button class="mobile-fab" type="button" aria-label="Nuevo estado" @click="abrirNuevo">+<span>Estado</span></button>
    </header>

    <div v-if="dirtyRows.length" class="pendientes" role="status">
      <span><i class="dot" style="--dot: var(--dot-amber)" />{{ dirtyRows.length === 1 ? "Tenés 1 estado sin guardar" : `Tenés ${dirtyRows.length} estados sin guardar` }}</span>
      <button class="btn btn--primary" type="button" :disabled="guardando !== null" @click="saveAll">Guardar todos</button>
    </div>

    <div v-if="loading" class="text-muted">Cargando estados…</div>
    <div v-else class="lista">
      <article v-for="(st, i) in statuses" :key="st.id" :class="['fila', { 'fila--inactiva': !st.active, 'fila--cambios': isDirty(st) }]">
        <div class="fila__main">
          <div class="orden" role="group" :aria-label="`Orden de ${st.name}`">
            <button type="button" class="orden__btn" :disabled="i === 0" :aria-label="`Subir ${st.name}`" @click="mover(st, -1)">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6" /></svg>
            </button>
            <button type="button" class="orden__btn" :disabled="i === statuses.length - 1" :aria-label="`Bajar ${st.name}`" @click="mover(st, 1)">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
            </button>
          </div>
          <input v-model="st.color" class="color" type="color" :aria-label="`Color de ${st.name}`" />
          <div class="field nombre">
            <label :for="`nombre-${st.id}`">Nombre</label>
            <input :id="`nombre-${st.id}`" v-model="st.name" />
          </div>
          <div class="muestra">
            <small>Se ve así</small>
            <span class="status-chip" :style="{ '--dot': st.color }">{{ st.name || "Sin nombre" }}</span>
          </div>
          <label class="check"><input v-model="st.active" type="checkbox" /> Activo</label>
          <button v-if="isDirty(st)" class="btn btn--primary" type="button" :disabled="guardando === st.id || !st.name.trim()" @click="save(st)">
            {{ guardando === st.id ? "Guardando…" : "Guardar cambios" }}
          </button>
          <span v-else class="guardado">Guardado</span>
        </div>
        <p v-if="!st.active" class="inactiva">Inactivo: no se puede elegir para una OT nueva.</p>

        <details class="mas">
          <summary>Qué hace este estado <span>{{ flagsSummary(st) }}</span></summary>
          <div class="flags">
            <label v-for="f in FLAGS" :key="f.key" :class="['flag', { 'flag--peligro': f.danger }]">
              <input v-model="st[f.key]" type="checkbox" />
              <span class="flag__texto">
                <strong><i v-if="f.danger" class="dot" style="--dot: var(--dot-red)" />{{ f.label }}</strong>
                <small>{{ f.hint }}</small>
                <small v-if="notaFlag(f, st[f.key], st.id)" :class="['flag__duenio', { 'flag__duenio--mueve': st[f.key] }]">{{ notaFlag(f, st[f.key], st.id) }}</small>
              </span>
            </label>
          </div>
        </details>

        <details class="mas">
          <summary>Aviso al cliente <span>{{ notifSummary(st) }}</span></summary>
          <div class="aviso">
            <div class="canales">
              <label class="check"><input v-model="st.notify_whatsapp" type="checkbox" /> WhatsApp</label>
              <label class="check"><input v-model="st.notify_email" type="checkbox" /> Email</label>
            </div>
            <p v-if="!st.notify_whatsapp && !st.notify_email" class="aviso__vacio">Elegí un canal para avisarle al cliente cuando su OT pase a este estado.</p>
            <template v-else>
              <div class="field">
                <label :for="`mensaje-${st.id}`">Mensaje <span class="opcional">· si lo dejás vacío se manda el mensaje por defecto</span></label>
                <textarea
                  :id="`mensaje-${st.id}`"
                  :ref="(el) => (mensajes[st.id] = el as HTMLTextAreaElement | null)"
                  v-model="st.notification_template"
                  rows="3"
                  :placeholder="DEFAULT_TEMPLATE"
                />
              </div>
              <div class="variables">
                <small>Insertar:</small>
                <button v-for="v in templateVariables" :key="v" type="button" class="variable" @click="insertar(st, v)">{{ v }}</button>
              </div>
              <p v-if="variablesMalas(st.notification_template).length" class="aviso__error">
                No existe: {{ listaMalas(st.notification_template) }}. Se va a mandar tal cual.
              </p>
              <div class="previa">
                <small>Vista previa con datos de ejemplo</small>
                <p><template v-for="(p, k) in vistaPrevia(st, st.notification_template)" :key="k"><mark v-if="p.malo">{{ p.texto }}</mark><template v-else>{{ p.texto }}</template></template></p>
              </div>
              <div v-if="st.notify_email" class="field">
                <label :for="`asunto-${st.id}`">Asunto del email</label>
                <input :id="`asunto-${st.id}`" v-model="st.notification_email_subject" placeholder="Tu orden de trabajo {{numero_ot}}" />
              </div>
            </template>
          </div>
        </details>
      </article>
    </div>

    <Modal :open="showNew" title="Nuevo estado de OT" @close="showNew = false">
      <div class="nuevo">
        <div class="nuevo__fila">
          <input v-model="newStatus.color" class="color" type="color" aria-label="Color" />
          <div class="field nombre">
            <label for="nuevo-nombre">Nombre *</label>
            <input id="nuevo-nombre" v-model="newStatus.name" autofocus />
          </div>
        </div>
        <span class="status-chip" :style="{ '--dot': newStatus.color }">{{ newStatus.name || "Sin nombre" }}</span>
        <div class="flags">
          <label v-for="f in FLAGS" :key="f.key" :class="['flag', { 'flag--peligro': f.danger }]">
            <input v-model="newStatus[f.key]" type="checkbox" />
            <span class="flag__texto">
              <strong><i v-if="f.danger" class="dot" style="--dot: var(--dot-red)" />{{ f.label }}</strong>
              <small>{{ f.hint }}</small>
              <small v-if="notaFlag(f, newStatus[f.key])" :class="['flag__duenio', { 'flag__duenio--mueve': newStatus[f.key] }]">{{ notaFlag(f, newStatus[f.key]) }}</small>
            </span>
          </label>
        </div>
        <div class="nuevo__acciones">
          <button class="btn" type="button" @click="showNew = false">Cancelar</button>
          <button class="btn btn--primary" type="button" :disabled="!newStatus.name.trim()" @click="create">Crear estado</button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.estados { display:flex; flex-direction:column; gap:20px; }
.heading { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }
.heading h1 { margin:0 0 6px; font-size:28px; font-weight:700; }
.heading p { margin:0; font-size:15px; color:var(--color-text-secondary); }
.pendientes { position:sticky; top:calc(var(--topbar-height) + 8px); z-index:5; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 16px; border:1px solid var(--color-border-strong); border-radius:var(--radius-lg); background:var(--color-chip); font-size:14px; }
.pendientes span { display:flex; align-items:center; gap:8px; }
.lista { display:flex; flex-direction:column; gap:10px; }
.fila { display:flex; flex-direction:column; gap:6px; padding:16px 18px; border:1px solid var(--color-border); border-radius:var(--radius-lg); background:var(--color-surface); transition:border-color .15s ease, opacity .15s ease; }
.fila--cambios { border-color:var(--dot-amber); }
.fila--inactiva { opacity:.6; }
.fila--inactiva:focus-within, .fila--inactiva:hover { opacity:1; }
.fila__main { display:flex; flex-wrap:wrap; align-items:flex-end; gap:12px 14px; }
.orden { display:flex; flex-direction:column; align-self:center; }
.orden__btn { display:grid; place-items:center; width:28px; height:22px; padding:0; border:0; border-radius:var(--radius-sm); background:transparent; color:var(--color-text-secondary); cursor:pointer; }
.orden__btn:hover:not(:disabled) { background:var(--color-surface-hover); color:var(--color-text-primary); }
.orden__btn:disabled { color:var(--color-border-strong); cursor:default; }
.color { width:44px; height:44px; padding:3px; flex:none; border:1px solid var(--color-border-strong); border-radius:var(--radius-md); background:var(--color-field); cursor:pointer; }
.nombre { flex:1 1 220px; min-width:0; margin:0; }
.muestra { display:flex; flex-direction:column; gap:6px; min-width:140px; }
.muestra small { font-size:12px; color:var(--color-text-muted); }
.check { display:flex; align-items:center; gap:8px; min-height:44px; font-size:14px; white-space:nowrap; }
.guardado { min-height:44px; display:flex; align-items:center; font-size:13px; color:var(--color-text-muted); }
.inactiva { margin:0; font-size:12px; color:var(--color-text-muted); }
.mas summary { cursor:pointer; padding:6px 0; font-size:14px; font-weight:600; }
.mas summary span { margin-left:8px; font-weight:400; color:var(--color-text-muted); }
.flags { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; padding:8px 0 4px; }
.flag { display:flex; gap:10px; align-items:flex-start; padding:10px 12px; border:1px solid var(--color-border); border-radius:var(--radius-md); cursor:pointer; }
.flag:hover { background:var(--color-surface-hover); }
.flag input { margin-top:3px; flex:none; }
.flag--peligro:has(input:checked) { border-color:var(--dot-red); }
.flag__texto { display:flex; flex-direction:column; gap:3px; }
.flag__texto strong { display:flex; align-items:center; gap:6px; font-size:14px; font-weight:600; }
.flag__texto small { font-size:12px; line-height:1.4; color:var(--color-text-muted); }
.flag__duenio { color:var(--color-text-secondary) !important; }
.flag__duenio--mueve { color:var(--color-warning-text) !important; }
.aviso { display:flex; flex-direction:column; gap:12px; padding:8px 0 4px; }
.aviso .field { margin:0; }
.canales { display:flex; gap:20px; }
.aviso__vacio { margin:0; font-size:13px; color:var(--color-text-secondary); }
.aviso__error { margin:0; font-size:13px; color:var(--dot-red); }
.opcional { font-weight:400; color:var(--color-text-muted); }
.variables { display:flex; flex-wrap:wrap; align-items:center; gap:6px; }
.variables small { font-size:12px; color:var(--color-text-muted); margin-right:2px; }
.variable { padding:3px 10px; border:1px solid var(--color-border-strong); border-radius:999px; background:var(--color-chip); color:var(--color-link); font-family:var(--font-mono); font-size:12px; cursor:pointer; }
.variable:hover { border-color:var(--color-primary); }
.previa { padding:12px 14px; border-radius:var(--radius-md); background:var(--color-bg); border:1px solid var(--color-border); }
.previa small { font-size:12px; color:var(--color-text-muted); }
.previa p { margin:6px 0 0; font-size:14px; line-height:1.5; white-space:pre-wrap; }
.previa mark { background:transparent; color:var(--dot-red); text-decoration:underline wavy; }
.nuevo { display:flex; flex-direction:column; gap:14px; }
.nuevo__fila { display:flex; align-items:flex-end; gap:12px; }
.nuevo__acciones { display:flex; justify-content:flex-end; gap:8px; padding-top:6px; }
@media (max-width:600px) {
  .heading h1 { font-size:22px; }
  .fila { padding:14px; }
  .muestra { display:none; }
  .flags { grid-template-columns:1fr; }
  .pendientes { flex-direction:column; align-items:stretch; }
}
</style>
