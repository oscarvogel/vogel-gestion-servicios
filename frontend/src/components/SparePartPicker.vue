<script setup lang="ts">
/**
 * Combo de repuestos del catalogo de Flexxus (#114).
 *
 * Es un autocomplete contra `GET /spare-parts/search`. Cuando el catalogo
 * aplica a la empresa, **elegir una opcion es obligatorio**: si el texto no
 * corresponde a ningun articulo, la linea no se guarda. Cuando el catalogo no
 * aplica (la empresa no lo tiene habilitado, o el ERP esta caido), el campo
 * se comporta como texto libre: la OT tiene que poder cargarse igual.
 *
 * El componente no decide nada de negocio: avisa que chose y que descripcion.
 * El que decide si guarda es el padre, con lo que le emite.
 *
 * El desplegable va por Teleport a `body` con posicion fija: el modal de
 * presupuesto es un contenedor con `overflow:auto`, y un menu absoluto
 * adentro quedaria recortado. Es el mismo problema que ya tienen el combo de
 * clientes y el de técnicos.
 */
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { apiGet } from "../lib/api";

export interface SparePart {
  code: string;
  description: string;
  rubro: string | null;
  marca: string | null;
  stock: number | null;
  stock_minimo: number | null;
  cost: number | null;
  cost_currency: string;
  cost_source_currency: string | null;
  sale_price: number | null;
  sale_price_currency: string;
  price_source: string | null;
  price_synced_at: string | null;
}

const props = withDefaults(
  defineProps<{
    modelValue: string;
    placeholder?: string;
    disabled?: boolean;
  }>(),
  {
    placeholder: "Buscar repuesto por código o descripción…",
    disabled: false,
  },
);

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "change", payload: { description: string; part: SparePart | null }): void;
  (e: "availability", disponible: boolean): void;
}>();

const opciones = ref<SparePart[]>([]);
const abierto = ref(false);
const cargando = ref(false);
const aviso = ref<string | null>(null);
const seleccionado = ref<SparePart | null>(null);
/** null = todavia no se consulto. false = el catalogo no aplica a esta empresa. */
const catalogoDisponible = ref<boolean | null>(null);

const inputRef = ref<HTMLInputElement | null>(null);
const menuRef = ref<HTMLElement | null>(null);
const menuStyle = ref<Record<string, string>>({});

let temporizador: ReturnType<typeof setTimeout> | null = null;
let numeroPedido = 0;
let estadoConsultado = false;

/** Compara sin mayusculas ni acentos, como hace el ERP. */
function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function formato(numero: number | null): string {
  if (numero === null || numero === undefined) return "";
  return Number(numero).toLocaleString("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Ubica el desplegable al borde de la ventana, sin salirse de la pantalla. */
function posicionarMenu() {
  const el = inputRef.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const disponibleAbajo = window.innerHeight - rect.bottom;
  const disponibleArriba = rect.top;
  // El menu se abre hacia el lado con mas espacio. No se usa un umbral fijo:
  // el menu mide hasta 260px, asi que un umbral menor lo dejaba afuera de la
  // pantalla en los campos que estan cerca del borde de abajo.
  const altoMaximo = 260;
  const haciaArriba = disponibleArriba > disponibleAbajo;
  const espacio = haciaArriba ? disponibleArriba : disponibleAbajo;
  const alto = Math.max(120, Math.min(altoMaximo, espacio - 12));
  menuStyle.value = {
    position: "fixed",
    top: haciaArriba ? `${rect.top - 4}px` : `${rect.bottom + 4}px`,
    left: `${rect.left}px`,
    width: `${rect.width}px`,
    maxHeight: `${alto}px`,
    transform: haciaArriba ? `translateY(-100%)` : "",
  };
}

function abrirMenu() {
  abierto.value = true;
  posicionarMenu();
  window.addEventListener("scroll", posicionarMenu, true);
  window.addEventListener("resize", posicionarMenu);
  document.addEventListener("mousedown", alTocarFuera);
}

function cerrarMenu() {
  if (!abierto.value) return;
  abierto.value = false;
  window.removeEventListener("scroll", posicionarMenu, true);
  window.removeEventListener("resize", posicionarMenu);
  document.removeEventListener("mousedown", alTocarFuera);
}

function alTocarFuera(event: MouseEvent) {
  const destino = event.target as Node;
  if (inputRef.value?.contains(destino)) return;
  if (menuRef.value?.contains(destino)) return;
  cerrarMenu();
}

async function consultarEstado() {
  // Una sola vez: el estado de la empresa no cambia mientras la pantalla esta
  // abierta, y no tiene sentido pegarle al backend en cada focus.
  if (estadoConsultado) return;
  estadoConsultado = true;
  try {
    const r = await apiGet<{ disponible: boolean; motivo: string | null; falla: boolean }>(
      "/spare-parts/status",
    );
    catalogoDisponible.value = r.disponible;
    emit("availability", r.disponible);
    // El aviso se muestra solo cuando el catalogo CORRESPONDE y algo falla
    // (ERP caido, sin credencial). Que la empresa no tenga el modulo es el
    // estado normal de todas menos una: ahi no se dice nada, y la pantalla se
    // ve igual que antes del modulo.
    aviso.value = r.falla ? r.motivo : null;
  } catch (_) {
    // Si ni el estado se puede consultar, se deja escribir a mano: cargar la
    // OT no puede depender de que el modulo este disponible.
    catalogoDisponible.value = false;
    emit("availability", false);
  }
}

async function buscar(texto: string) {
  const limpio = texto.trim();
  if (!limpio) {
    opciones.value = [];
    cerrarMenu();
    return;
  }
  // Si el catalogo no aplica a esta empresa, no se busca: el campo es texto
  // libre y no tiene sentido pegarle al backend en cada tecla.
  if (catalogoDisponible.value === false) {
    cerrarMenu();
    return;
  }
  const pedido = ++numeroPedido;
  cargando.value = true;
  try {
    const r = await apiGet<{
      disponible: boolean;
      aviso: string | null;
      items: SparePart[];
    }>("/spare-parts/search", { params: { q: limpio, limit: 12 } });
    // Si llego una respuesta vieja, se ignora: el operador ya escribio otra cosa.
    if (pedido !== numeroPedido) return;
    if (!r.disponible) {
      // El ERP no respondio o la empresa no tiene el modulo: se degrada a
      // texto libre. El aviso llega solo si es una falla real: el backend
      // manda `aviso: null` cuando lo que hay es que la empresa no tiene el
      // modulo habilitado.
      emit("availability", false);
      catalogoDisponible.value = false;
      aviso.value = r.aviso ?? null;
      opciones.value = [];
      cerrarMenu();
      return;
    }
    opciones.value = Array.isArray(r.items) ? r.items : [];
    if (!seleccionado.value) {
      // Si el texto ya coincide con una opcion, se toma sola: el operador
      // puede escribir el nombre exacto y no tener que hacer clic.
      const exacto = opciones.value.find(
        (o) =>
          normalizar(o.description) === normalizar(limpio) ||
          normalizar(o.code) === normalizar(limpio),
      );
      if (exacto) {
        seleccionar(exacto);
        return;
      }
    }
    if (opciones.value.length) {
      await nextTick();
      abrirMenu();
    } else {
      cerrarMenu();
    }
  } catch (_) {
    opciones.value = [];
    cerrarMenu();
  } finally {
    if (pedido === numeroPedido) cargando.value = false;
  }
}

function seleccionar(opcion: SparePart) {
  seleccionado.value = opcion;
  emit("update:modelValue", opcion.description);
  emit("change", { description: opcion.description, part: opcion });
  opciones.value = [];
  cerrarMenu();
}

function onInput(event: Event) {
  const valor = (event.target as HTMLInputElement).value;
  emit("update:modelValue", valor);
  // Si el texto se edita a mano, la eleccion anterior deja de valer: la linea
  // tendria un precio que no corresponde a lo escrito.
  if (
    seleccionado.value &&
    normalizar(seleccionado.value.description) !== normalizar(valor)
  ) {
    seleccionado.value = null;
    emit("change", { description: valor, part: null });
  }
  if (temporizador) clearTimeout(temporizador);
  temporizador = setTimeout(() => buscar(valor), 250);
}

function onFocus() {
  consultarEstado();
  if (opciones.value.length) {
    posicionarMenu();
    abrirMenu();
  }
}

onMounted(consultarEstado);
onBeforeUnmount(() => {
  if (temporizador) clearTimeout(temporizador);
  cerrarMenu();
});
</script>

<template>
  <div class="spare-picker">
    <div class="spare-picker__box">
      <input
        ref="inputRef"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        autocomplete="off"
        class="spare-picker__input"
        role="combobox"
        aria-label="Repuesto"
        :aria-expanded="abierto"
        aria-autocomplete="list"
        @input="onInput"
        @focus="onFocus"
        @keydown.esc="cerrarMenu"
      />
      <span v-if="cargando" class="spare-picker__spinner" aria-hidden="true"></span>
    </div>
    <small v-if="aviso" class="spare-picker__aviso">{{ aviso }}</small>
    <Teleport to="body">
      <div
        v-if="abierto && opciones.length"
        ref="menuRef"
        class="spare-picker__menu"
        :style="menuStyle"
        role="listbox"
        @mousedown.prevent
      >
        <button
          v-for="opcion in opciones"
          :key="opcion.code"
          type="button"
          class="spare-picker__option"
          role="option"
          @mousedown.prevent="seleccionar(opcion)"
        >
          <span class="spare-picker__code">{{ opcion.code }}</span>
          <span class="spare-picker__desc">{{ opcion.description }}</span>
          <span class="spare-picker__meta">
            <em v-if="opcion.marca">{{ opcion.marca }}</em>
            <em v-if="opcion.rubro">{{ opcion.rubro }}</em>
            <b v-if="opcion.sale_price !== null">$ {{ formato(opcion.sale_price) }}</b>
          </span>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.spare-picker {
  position: relative;
  min-width: 0;
}
.spare-picker__box {
  position: relative;
  display: flex;
  align-items: center;
}
.spare-picker__input {
  width: 100%;
  min-width: 0;
}
.spare-picker__spinner {
  position: absolute;
  right: 10px;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(148, 163, 184, 0.35);
  border-top-color: var(--color-text, #e5edf7);
  border-radius: 50%;
  animation: spare-picker-spin 0.7s linear infinite;
  pointer-events: none;
}
@keyframes spare-picker-spin {
  to {
    transform: rotate(360deg);
  }
}
.spare-picker__aviso {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: #f59e0b;
}
</style>

<!--
  El desplegable vive en `body` (Teleport), asi que sus estilos no pueden
  depender del scoped de esta vista: van aparte, con prefijo propio.
-->
<style>
.spare-picker__menu {
  position: fixed;
  /* Por encima del modal de presupuesto (z-index 145). */
  z-index: 200;
  padding: 6px;
  background: var(--surface, #152238);
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.35);
  overflow: auto;
}
.spare-picker__option {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 10px;
  width: 100%;
  text-align: left;
  padding: 9px 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.spare-picker__option:hover {
  background: rgba(59, 130, 246, 0.14);
}
.spare-picker__code {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted, #8290a5);
  align-self: center;
}
.spare-picker__desc {
  font-size: 13px;
  line-height: 1.35;
}
.spare-picker__meta {
  grid-column: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary, #94a3b8);
}
.spare-picker__meta em {
  font-style: normal;
}
.spare-picker__meta b {
  color: var(--color-text, #e5edf7);
  font-variant-numeric: tabular-nums;
}
</style>
