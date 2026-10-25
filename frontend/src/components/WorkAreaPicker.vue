<script setup lang="ts">
/**
 * Combo de área de trabajo (marca + política).
 *
 * El área es lo que decide la garantía de la orden y a qué empresa se liquida. Por eso
 * el picker muestra las dos cosas abajo del campo: el operador tiene que ver a quién
 * está mandando la plata antes de confirmar.
 *
 * - Se escribe y filtra por "contiene", ignorando mayúsculas y acentos.
 * - **No se aceptan valores sueltos**: si el texto no coincide con un área del maestro,
 *   el campo queda marcado como inválido y la orden no se manda. Es preferible frenar
 *   la recepción a crear una orden que en realidad no tiene garantía asignada.
 * - Con "sin área" no hay nada que elegir: la orden se crea igual, pero no entra al
 *   cierre hasta que se le ponga un área.
 */
import { computed, onMounted, ref, watch } from "vue";

import { WorkArea, cargarAreas, etiquetaArea, normalizar } from "../lib/work-areas";

const props = withDefaults(
  defineProps<{
    modelValue?: number | null;
    disabled?: boolean;
    placeholder?: string;
    /** Muestra el botón de limpiar. */
    clearable?: boolean;
  }>(),
  {
    modelValue: null,
    disabled: false,
    placeholder: "Buscar marca o política…",
    clearable: true,
  },
);

const emit = defineEmits<{
  (e: "update:modelValue", value: number | null): void;
  /**
   * `coincide` dice si el texto escrito corresponde a un área del maestro.
   * Con `coincide: false` y texto escrito, la orden no se debe mandar.
   */
  (e: "change", payload: { area: WorkArea | null; coincide: boolean }): void;
}>();

const areas = ref<WorkArea[]>([]);
const texto = ref("");
const abierto = ref(false);
const cargando = ref(false);
// El área elegida en esta sesión. Se guarda aparte del `modelValue` porque el padre
// puede tardar en aplicarlo (o no estar enlazado): la consecuencia que se muestra
// abajo —la garantía y a quién se liquida— no puede depender de eso.
const seleccionado = ref<WorkArea | null>(null);

const areaElegida = computed(
  () => seleccionado.value ?? areas.value.find((a) => a.id === props.modelValue) ?? null,
);

/** El texto escrito coincide con un área del maestro (exacta, sin acentos ni mayúsculas). */
const coincide = computed(() => {
  if (!texto.value.trim()) return true;
  const t = normalizar(texto.value);
  return areas.value.some((a) => normalizar(etiquetaArea(a)) === t);
});

const opciones = computed(() => {
  const t = normalizar(texto.value);
  const lista = t
    ? areas.value.filter(
        (a) =>
          normalizar(etiquetaArea(a)).includes(t) ||
          normalizar(a.area_code).includes(t) ||
          // También por la empresa a liquidar: en la planta se conoce la marca, no el
          // código de la política.
          normalizar(a.billing_customer_name ?? "").includes(t),
      )
    : areas.value;
  return lista.slice(0, 40);
});

/** Lo que el operador necesita ver: la garantía y a quién se liquida. */
const consecuencia = computed(() => {
  const a = areaElegida.value;
  if (!a) return null;
  const partes = [a.warranty_label];
  partes.push(a.billing_customer_name ? `Se liquida a ${a.billing_customer_name}` : "Sin empresa a liquidar");
  return partes.join(" · ");
});

const sinEmpresa = computed(
  () => !!areaElegida.value && !areaElegida.value.billing_customer_id,
);

const inactiva = computed(() => !!areaElegida.value && !areaElegida.value.active);

async function cargar() {
  cargando.value = true;
  try {
    areas.value = await cargarAreas();
    if (props.modelValue) {
      const a = areas.value.find((x) => x.id === props.modelValue);
      if (a) {
        texto.value = etiquetaArea(a);
        seleccionado.value = a;
      }
    }
  } finally {
    cargando.value = false;
  }
}

onMounted(cargar);

// Cuando el padre cambia el area (por ejemplo, al abrir otra orden), el texto tiene
// que seguirlo: si no, el campo muestra el area anterior mientras la de abajo es otra.
watch(
  () => props.modelValue,
  (nuevo, viejo) => {
    if (nuevo === viejo) return;
    if (nuevo === null) {
      texto.value = "";
      seleccionado.value = null;
      return;
    }
    const a = areas.value.find((x) => x.id === nuevo);
    if (a) {
      texto.value = etiquetaArea(a);
      seleccionado.value = a;
    }
  },
);

function elegir(a: WorkArea) {
  texto.value = etiquetaArea(a);
  seleccionado.value = a;
  abierto.value = false;
  emit("update:modelValue", a.id);
  emit("change", { area: a, coincide: true });
}

function escribir(ev: Event) {
  texto.value = (ev.target as HTMLInputElement).value;
  const t = normalizar(texto.value);
  const exacto = areas.value.find((a) => normalizar(etiquetaArea(a)) === t);
  if (exacto) {
    seleccionado.value = exacto;
    emit("update:modelValue", exacto.id);
    emit("change", { area: exacto, coincide: true });
  } else {
    // Texto que no es un área del maestro: no se guarda nada.
    seleccionado.value = null;
    emit("update:modelValue", null);
    emit("change", { area: null, coincide: false });
  }
  abierto.value = true;
}

function limpiar() {
  texto.value = "";
  seleccionado.value = null;
  abierto.value = false;
  emit("update:modelValue", null);
  emit("change", { area: null, coincide: true });
}

/** Expuesto para que el padre limpie el campo cuando reinicia el formulario. */
defineExpose({ limpiar, areaElegida });
</script>

<template>
  <div class="area-picker">
    <div class="customer-picker__input">
      <input
        :value="texto"
        :placeholder="placeholder"
        :disabled="disabled"
        autocomplete="off"
        role="combobox"
        aria-expanded="abierto"
        aria-label="Área de trabajo"
        @input="escribir"
        @focus="abierto = true"
        @blur="abierto = false"
      />
      <button
        v-if="clearable && texto"
        type="button"
        class="area-picker__clear"
        title="Quitar el área"
        :disabled="disabled"
        @mousedown.prevent="limpiar"
      >
        ×
      </button>
    </div>

    <div v-if="abierto && opciones.length" class="customer-picker__menu">
      <button
        v-for="a in opciones"
        :key="a.id"
        type="button"
        class="customer-picker__option area-picker__option"
        @mousedown.prevent="elegir(a)"
      >
        <span class="area-picker__option-name">
          {{ etiquetaArea(a) }}
          <em v-if="!a.active" class="area-picker__inactiva">inactiva</em>
        </span>
        <span class="area-picker__option-meta">
          {{ a.warranty_label }}
          <template v-if="a.billing_customer_name"> · {{ a.billing_customer_name }}</template>
        </span>
      </button>
    </div>

    <p v-if="texto && !coincide" class="area-picker__error">
      Ese área no está en el maestro. Elegí una de la lista o borrá el texto.
    </p>
    <p v-else-if="consecuencia" class="area-picker__hint" :class="{ 'area-picker__hint--warn': sinEmpresa || inactiva }">
      {{ consecuencia }}
      <template v-if="inactiva"> · el área está desactivada</template>
      <template v-else-if="sinEmpresa"> · sin empresa a liquidar, la orden no entra al cierre</template>
    </p>
    <p v-else-if="cargando" class="area-picker__hint">Cargando el maestro de áreas…</p>
  </div>
</template>

<style scoped>
.area-picker {
  position: relative;
}
.customer-picker__input {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}
.area-picker input {
  width: 100%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  color: var(--color-text-primary);
  outline: none;
  transition: border 0.18s ease, background 0.18s ease;
}
.area-picker input:focus {
  border-color: var(--color-primary);
  background: var(--color-surface-elevated);
}
.area-picker input::placeholder {
  color: var(--color-text-muted);
}
.area-picker__clear {
  align-self: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
}
.area-picker__clear:hover {
  border-color: var(--color-primary);
  color: var(--color-text-primary);
}
.customer-picker__menu {
  position: absolute;
  z-index: 30;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  margin-top: 6px;
  padding: 6px;
  background: var(--surface, #152238);
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.35);
  max-height: 260px;
  overflow: auto;
}
.customer-picker__option {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  text-align: left;
  padding: 10px 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.customer-picker__option:hover {
  background: rgba(59, 130, 246, 0.14);
}
.area-picker__option-name {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 7px;
}
.area-picker__inactiva {
  font-style: normal;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.18);
  color: var(--text-secondary, #8290a5);
}
.area-picker__option-meta {
  flex: none;
  font-size: 11px;
  color: var(--text-secondary, #8290a5);
  text-align: right;
}
.area-picker__hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-secondary, #8290a5);
}
.area-picker__hint--warn {
  color: var(--color-warning-text, #fbbf24);
}
.area-picker__error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-danger, #f87171);
}
</style>
