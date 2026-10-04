<script setup lang="ts">
/**
 * Confirmacion de una propuesta. El unico lugar donde se puede ejecutar una accion de la IA.
 *
 * Lo que este dialogo tiene que hacer bien:
 *
 * 1. Mostrar **que va a pasar**, no quepidio el modelo. Con la herramienta, en castellano.
 * 2. Dejar **editar** los valores. La persona puede corregirlo, y lo que se escribe es lo
 *    corregido: por eso los campos son editables y se manda lo que quedo en pantalla.
 * 3. Marcar el **riesgo** antes de confirmar. Un repuesto con precio o un cambio de estado
 *    que le avisa al cliente se tienen que ver antes de apretar, no despues.
 * 4. No dejar aplicar dos veces. El backend tiene el candado, pero el boton se deshabilita
 *    mientras corre para que el operador no se confunda con un error.
 */
import { computed, ref, watch } from "vue";
import Modal from "../Modal.vue";
import { apiGet, apiPost } from "../../lib/api";
import type { Propuesta } from "../../lib/ai";

/** Una linea del calculo, tal como lo devuelve el backend. */
interface LineaCalculo {
  descripcion: string;
  tipo: string;
  cantidad: string;
  precio_unitario: string | null;
  total_linea: string | null;
  pendiente: string | null;
  revisar: string | null;
}

interface CalculoPresupuesto {
  items: LineaCalculo[];
  subtotal_repuestos: string;
  subtotal_manos_de_obra: string;
  total: string;
  pendientes: string[];
  avisos: string[];
  puede_generar: boolean;
  motivos_de_dominio: string[];
}

const props = defineProps<{ open: boolean; propuesta: Propuesta | null; busy?: boolean }>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "confirmar", argumentos: Record<string, unknown>): void;
}>();

const editados = ref<Record<string, unknown>>({});

watch(
  () => props.propuesta,
  (p) => {
    // Se parte siempre de lo que propuso el modelo, nunca de una edicion anterior: si se
    // abre otra propuesta, no puede quedar el valor de la anterior pegado.
    editados.value = p ? { ...p.argumentos_propuestos } : {};
  },
  { immediate: true },
);

const ETIQUETAS: Record<string, string> = {
  crear_cliente: "Dar de alta un cliente",
  crear_equipo: "Registrar un equipo",
  crear_ot: "Abrir una orden de trabajo",
  actualizar_ot: "Modificar una orden de trabajo",
  agregar_diagnostico: "Guardar el diagnóstico",
  agregar_trabajo: "Sumar trabajo a una orden",
  agregar_repuesto: "Sumar un repuesto a una orden",
  generar_presupuesto: "Generar el presupuesto de una orden",
  preparar_comunicacion_cliente: "Preparar un aviso para el cliente",
};

const CAMPOS: Record<string, string> = {
  nombre: "Nombre",
  documento: "Documento",
  telefono: "Teléfono",
  whatsapp: "WhatsApp",
  email: "Email",
  direccion: "Dirección",
  notas: "Notas",
  cliente_id: "Id del cliente",
  equipo_id: "Id del equipo",
  categoria: "Categoría",
  marca: "Marca",
  modelo: "Modelo",
  numero_de_serie: "N° de serie",
  descripcion: "Descripción",
  falla_reportada: "Falla reportada",
  condicion_fisica: "Condición física",
  accesorios: "Accesorios",
  entrega_estimada: "Entrega estimada",
  estado_id: "Id del estado",
  estado: "Estado",
  nota: "Observación",
  diagnostico: "Diagnóstico",
  notas_tecnicas: "Notas técnicas",
  cantidad: "Cantidad",
  precio_unitario: "Precio unitario",
  costo_unitario: "Costo unitario",
  orden: "Id de la orden",
  mensaje: "Mensaje para el cliente",
  canal: "Canal",
};

/**
 * Campos que se editan en un area de texto y no en una linea.
 *
 * Un mensaje de WhatsApp con dos saltos de linea en un `<input>` se ve como una sola renglon
 * larguisimo y no se puede leer. Es el unico campo del sistema cuyo valor es texto para otra
 * persona, asi que el tratamiento lo merece.
 */
const CAMPOS_MULTILINEA = new Set(["mensaje", "diagnostico", "notas_tecnicas"]);

const titulo = computed(() =>
  props.propuesta ? (ETIQUETAS[props.propuesta.tool] ?? props.propuesta.tool) : "",
);

const campos = computed(() =>
  Object.entries(props.propuesta?.argumentos_propuestos ?? {}).map(([clave, valor]) => ({
    clave,
    etiqueta: CAMPOS[clave] ?? clave,
    valor,
  })),
);

const esNumero = (clave: string) =>
  ["precio_unitario", "costo_unitario", "cantidad", "orden", "cliente_id", "equipo_id", "estado_id"].includes(
    clave,
  );

function editado(clave: string): string {
  const v = editados.value[clave];
  return v === null || v === undefined ? "" : String(v);
}

function cambiar(clave: string, evento: Event) {
  const bruto = (evento.target as HTMLInputElement).value;
  editados.value = { ...editados.value, [clave]: esNumero(clave) && bruto !== "" ? Number(bruto) : bruto };
}

const riesgos = computed(() => {
  const r = props.propuesta?.riesgo;
  if (r === "financiero") return "Mueve plata: los importes van a la cuenta del cliente.";
  if (r === "comunicacion") return "Se le avisa al cliente y eso no se puede deshacer.";
  return null;
});

function confirmar() {
  emit("confirmar", { ...editados.value });
}

/**
 * Los importes del presupuesto, para que la persona vea **cuanto** va a quedar antes de
 * confirmar. No es la propuesta: es el calculo del backend con los datos de ahora. Se pide
 * al abrir el dialogo y no se guarda, asi que no hay forma de que quede viejo sin que se note,
 * y si la orden cambio entre la propuesta y la confirmacion, muestra el estado actual.
 *
 * Sin esto, confirmar una propuesta que mueve plata es apretar "Confirmar" al lado de un
 * "Id de la orden: 1" y enterarse el total despues. El riesgo se avisa; el numero no.
 */
const calculo = ref<CalculoPresupuesto | null>(null);
const calculoFallido = ref(false);

async function cargarCalculo() {
  calculo.value = null;
  calculoFallido.value = false;
  const orden = props.propuesta?.argumentos_propuestos?.orden;
  if (props.propuesta?.tool !== "generar_presupuesto" || orden === undefined) return;
  try {
    calculo.value = await apiGet<CalculoPresupuesto>(`/work-orders/${orden}/quotes/preview`);
  } catch {
    // Si el calculo no se puede pedir, el dialogo sigue siendo utilizable: los campos
    // editables y el boton no dependen de el. Se marca para que el silencio no se lea como
    // "no hay nada que ver".
    calculoFallido.value = true;
  }
}

watch(() => props.propuesta, () => void cargarCalculo(), { immediate: true });

const tieneAvisos = computed(
  () =>
    (calculo.value?.pendientes.length ?? 0) + (calculo.value?.avisos.length ?? 0) > 0,
);

/** Un aviso del preview, tal como lo devuelve el backend. */
interface AvisoPrevio {
  channel: string;
  recipient: string;
  subject: string | null;
  body: string;
  skipped: boolean;
  reason: string | null;
}

/**
 * El aviso tal como quedaría, con la plantilla ya resuelta. Se pide al abrir el dialogo.
 *
 * Sin esto, quien confirma ve el texto que escribió el modelo pero no a quién le llega ni cómo
 * quedaron los `{{nombre}}`. Y el mensaje se va a un cliente, que no puede deshacer lo que le
 * mandaron: es el caso donde ver antes importa más.
 */
const avisos = ref<AvisoPrevio[]>([]);
const avisoFallido = ref(false);

async function cargarAviso() {
  avisos.value = [];
  avisoFallido.value = false;
  const args = props.propuesta?.argumentos_propuestos ?? {};
  if (props.propuesta?.tool !== "preparar_comunicacion_cliente" || args.orden === undefined) return;
  try {
    const respuesta = await apiPost<{ items: AvisoPrevio[] }>(
      `/work-orders/${args.orden}/communication-preview`,
      {
        mensaje: args.mensaje ?? null,
        canal: args.canal ?? null,
      },
    );
    avisos.value = respuesta.items;
  } catch {
    avisoFallido.value = true;
  }
}

watch(() => props.propuesta, () => void cargarAviso(), { immediate: true });

const avisosMandables = computed(() => avisos.value.filter((a) => !a.skipped));
const avisosSinDestino = computed(() => avisos.value.filter((a) => a.skipped));

/**
 * La cantidad viene como texto desde el backend porque la columna es `Numeric(10, 3)`, y eso
 * muestra "1.000" para una fuente que va una sola vez. Se recorta solo cuando no hay parte
 * decimal: 0.75 tiene que seguir mostrando 0.75, no 0.75 ni 1.
 */
function cantidad(texto: string): string {
  return texto.includes(".") ? texto.replace(/0+$/, "").replace(/\.$/, "") : texto;
}

/** Mismo formato de plata que usa el resto de la aplicacion. */
function plata(texto: string | null): string {
  if (texto === null) return "sin precio";
  return `$ ${Number(texto).toLocaleString("es-AR", { minimumFractionDigits: 2 })}`;
}
</script>

<template>
  <Modal :open="open" :title="titulo" width="620px" @close="emit('close')">
    <div v-if="propuesta" class="prop">
      <!-- El riesgo va primero: es lo que hay que saber antes de confirmar. -->
      <div v-if="riesgos || propuesta.notifica_cliente" class="prop__riesgo">
        <span v-if="propuesta.riesgo === 'financiero'" class="badge badge--warning">financiero</span>
        <span v-else-if="propuesta.riesgo === 'comunicacion'" class="badge badge--warning">comunicación</span>
        <p v-if="riesgos">{{ riesgos }}</p>
        <p v-if="propuesta.notifica_cliente && propuesta.riesgo !== 'comunicacion'">
          Al aplicar se le avisa al cliente.
        </p>
      </div>

      <p class="prop__intro">
        Esto es lo que propuso el asistente. <strong>Revisalo y corregí lo que haga falta</strong>:
        se va a guardar exactamente lo que dejes acá.
      </p>

      <!--
        Los importes van antes de los campos. Es lo que la persona tiene que mirar antes de
        apretar "Confirmar", asi que no puede quedar abajo, debajo de algo que hay que leer
        para entender el dialogo.
      -->
      <div v-if="calculo" class="prop__calculo">
        <p class="prop__calculo-titulo">Queda así el presupuesto</p>
        <table class="prop__tabla">
          <thead>
            <tr>
              <th scope="col">Concepto</th>
              <th scope="col" class="num">Cant.</th>
              <th scope="col" class="num">Unitario</th>
              <th scope="col" class="num">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(linea, i) in calculo.items" :key="i" :class="{ 'es-pendiente': !linea.total_linea }">
              <td>
                {{ linea.descripcion }}
                <span v-if="linea.tipo === 'PART'" class="prop__tipo">repuesto</span>
                <span v-else class="prop__tipo">mano de obra</span>
              </td>
              <td class="num">{{ cantidad(linea.cantidad) }}</td>
              <td class="num">{{ plata(linea.precio_unitario) }}</td>
              <td class="num">{{ plata(linea.total_linea) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="3" class="num">Repuestos</td>
              <td class="num">{{ plata(calculo.subtotal_repuestos) }}</td>
            </tr>
            <tr>
              <td colspan="3" class="num">Mano de obra</td>
              <td class="num">{{ plata(calculo.subtotal_manos_de_obra) }}</td>
            </tr>
            <tr class="prop__total">
              <td colspan="3" class="num">Total</td>
              <td class="num">{{ plata(calculo.total) }}</td>
            </tr>
          </tfoot>
        </table>
        <p v-if="tieneAvisos" class="prop__aviso">
          <span v-for="(a, i) in [...calculo.pendientes, ...calculo.avisos]" :key="i">• {{ a }}</span>
        </p>
      </div>
      <p v-else-if="calculoFallido" class="prop__aviso">
        No se pudo calcular el presupuesto para mostrarlo. Revisá la orden antes de confirmar.
      </p>

      <!--
        El aviso al cliente va antes de los campos, y con una aclaración explícita: confirmar
        NO lo manda. Sin esa frase, "Confirmar y aplicar" al lado de un WhatsApp se lee como
        "se envía ahora", que es justo la confusión que este sub-issue quiere evitar.
      -->
      <div v-if="avisosMandables.length" class="prop__calculo">
        <p class="prop__calculo-titulo">Así le llega al cliente</p>
        <p class="prop__nota-envio">
          Confirmar lo deja <strong>pendiente</strong> en la orden. No se envía solo: lo mandás vos.
        </p>
        <div v-for="(aviso, i) in avisosMandables" :key="i" class="prop__aviso-bloque">
          <p class="prop__aviso-canal">
            <span class="prop__tipo">{{ aviso.channel === "WHATSAPP" ? "WhatsApp" : "Email" }}</span>
            <span class="prop__aviso-destino">{{ aviso.recipient }}</span>
          </p>
          <p v-if="aviso.subject" class="prop__aviso-asunto"><strong>{{ aviso.subject }}</strong></p>
          <p class="prop__aviso-texto">{{ aviso.body }}</p>
        </div>
      </div>
      <div v-else-if="avisosSinDestino.length" class="prop__calculo">
        <p class="prop__calculo-titulo">No se va a poder enviar</p>
        <p v-for="(aviso, i) in avisosSinDestino" :key="i" class="prop__aviso">
          • {{ aviso.reason }}
        </p>
      </div>
      <p v-else-if="avisoFallido" class="prop__aviso">
        No se pudo preparar la vista previa del aviso. Revisá la orden antes de confirmar.
      </p>

      <div class="prop__campos">
        <label v-for="c in campos" :key="c.clave" class="field" :class="{ 'field--ancho': CAMPOS_MULTILINEA.has(c.clave) }">
          <span>{{ c.etiqueta }}</span>
          <textarea
            v-if="CAMPOS_MULTILINEA.has(c.clave)"
            rows="5"
            :value="editado(c.clave)"
            @input="cambiar(c.clave, $event)"
          ></textarea>
          <input
            v-else
            :value="editado(c.clave)"
            :type="esNumero(c.clave) ? 'number' : 'text'"
            :step="c.clave === 'cantidad' ? 'any' : undefined"
            @input="cambiar(c.clave, $event)"
          />
        </label>
      </div>

      <div class="prop__pie">
        <span class="text-muted">Propuesta N° {{ propuesta.id }}</span>
        <div class="prop__acciones">
          <button class="btn btn--ghost" :disabled="busy" @click="emit('close')">Cancelar</button>
          <button class="btn btn--primary" :disabled="busy" @click="confirmar">
            {{ busy ? "Aplicando…" : "Confirmar y aplicar" }}
          </button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.prop {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 20px 20px;
}
.prop__riesgo {
  padding: 12px 14px;
  border: 1px solid rgba(245, 158, 11, 0.4);
  border-radius: 10px;
  background: rgba(245, 158, 11, 0.1);
}
.prop__riesgo p {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--color-text-primary, #e5edf7);
}
.prop__intro {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary, #cbd5e1);
}
/* La tabla del calculo va en un panel aparte y con fondo propio: el dialogo ya tiene un
   bloque de riesgo, una intro y los campos, y sin esta separacion la tabla se lee como un
   campo mas. */
.prop__calculo {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.5);
}
.prop__calculo-titulo {
  margin: 0 0 8px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted, #94a3b8);
}
.prop__tabla {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.prop__tabla th,
.prop__tabla td {
  padding: 6px 4px;
  text-align: left;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}
.prop__tabla th {
  font-weight: 500;
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
}
.prop__tabla .num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.prop__tabla tbody tr.es-pendiente td {
  color: var(--color-text-muted, #94a3b8);
}
.prop__tabla tfoot td {
  border-bottom: none;
  color: var(--color-text-secondary, #cbd5e1);
}
.prop__tabla tr.prop__total td {
  color: var(--color-text-primary, #e5edf7);
  font-weight: 600;
  border-top: 1px solid rgba(148, 163, 184, 0.35);
}
.prop__tipo {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 11px;
  background: rgba(148, 163, 184, 0.18);
  color: var(--color-text-muted, #94a3b8);
}
.prop__aviso {
  margin: 10px 0 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #fbbf24;
}
/* El aviso al cliente se muestra como un bloque de texto legible, no como una fila de tabla:
   lo que se lee es el mensaje, y tiene que poder copiarse tal como va a salir. */
.prop__nota-envio {
  margin: 0 0 10px;
  font-size: 12px;
  color: #fbbf24;
}
.prop__aviso-bloque {
  padding: 10px 0;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
}
.prop__aviso-canal {
  margin: 0 0 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.prop__aviso-destino {
  color: var(--color-text-secondary, #cbd5e1);
  font-variant-numeric: tabular-nums;
}
.prop__aviso-asunto {
  margin: 0 0 6px;
  font-size: 13px;
}
.prop__aviso-texto {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  color: var(--color-text-primary, #e5edf7);
}
.prop__campos {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.prop__campos .field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.prop__campos .field > span {
  color: var(--color-text-muted, #94a3b8);
}
.prop__campos input {
  background: #10283f;
  color: #e5edf7;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 8px;
  padding: 8px 10px;
  color-scheme: dark;
  width: 100%;
}
.prop__campos textarea {
  background: #10283f;
  color: #e5edf7;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 8px;
  padding: 8px 10px;
  color-scheme: dark;
  width: 100%;
  font: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
}
/* Los campos de texto largo ocupan todo el ancho: partir un mensaje en dos columnas lo deja
   ilegible. */
.prop__campos .field--ancho {
  grid-column: 1 / -1;
}
.prop__pie {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 4px;
  border-top: 1px solid rgba(148, 163, 184, 0.15);
}
.prop__acciones {
  display: flex;
  gap: 8px;
}
@media (max-width: 600px) {
  .prop__campos {
    grid-template-columns: 1fr;
  }
  .prop__pie {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
