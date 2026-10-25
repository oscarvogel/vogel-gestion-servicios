<script setup lang="ts">
/**
 * Maestro de áreas de trabajo: la marca, la política, la garantía y a quién se liquida.
 *
 * En el legacy (CiberBrain) esto no era un campo de la orden: eran tres tablas
 * encajadas (`dbo.Areas`, `dbo.TiposTrabajos` y `dbo.Aux_PoliticasxArea`), y la garantía
 * y la empresa a liquidar salían de la **política** del área. El cierre mensual a marcas
 * sigue haciendo JOIN por ese vínculo.
 *
 * Acá se administra en un solo lugar: cada fila es una marca + política, y trae las dos
 * cosas que el cierre necesita:
 *
 * - **Empresa a liquidar**: a quién se le manda la factura. Sin empresa, el área no
 *   liquida y las órdenes que la usan no entran al cierre.
 * - **Tipo de garantía**: fuera de garantía, de terceros o propia.
 *
 * El código y la política son la clave única dentro de la empresa: dos políticas de la
 * misma marca necesitan códigos distintos.
 */
import { computed, onMounted, ref } from "vue";

import { apiGet, apiPatch, apiPost, getApiErrorMessage } from "../lib/api";
import { WorkArea, etiquetaArea, invalidarAreas, normalizar } from "../lib/work-areas";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";

interface Customer {
  id: number;
  name: string;
  customer_type: string;
}

const TIPOS_GARANTIA = [
  { valor: 0, texto: "Fuera de garantía" },
  { valor: 1, texto: "Garantía de terceros" },
  { valor: 2, texto: "Garantía propia / de service" },
];

const session = useSessionStore();
const toast = useToastStore();

const areas = ref<WorkArea[]>([]);
const loading = ref(false);
const search = ref("");
const filtroEstado = ref("");
const mostrar = ref(false);
const editing = ref<WorkArea | null>(null);
const guardando = ref(false);

const form = ref({
  area_name: "",
  policy_code: "",
  policy_description: "",
  billing_customer_id: null as number | null,
  warranty_type: 0,
  active: true,
});

// --- Empresa a liquidar ---------------------------------------------------------------
const empresaQuery = ref("");
const empresaOpen = ref(false);
const empresas = ref<Customer[]>([]);

const puedeAdministrar = computed(() => session.hasPermission("work_areas.manage"));
const activos = computed(() => areas.value.filter((a) => a.active).length);
const conEmpresa = computed(() => areas.value.filter((a) => a.billing_customer_id).length);

const filtrados = computed(() => {
  const t = normalizar(search.value);
  return areas.value.filter((a) => {
    if (filtroEstado.value === "active" && !a.active) return false;
    if (filtroEstado.value === "inactive" && a.active) return false;
    if (!t) return true;
    return (
      normalizar(etiquetaArea(a)).includes(t) ||
      normalizar(a.area_code).includes(t) ||
      normalizar(a.billing_customer_name ?? "").includes(t)
    );
  });
});

async function load() {
  loading.value = true;
  try {
    areas.value = await apiGet<WorkArea[]>("/work-areas");
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo cargar el maestro de áreas"), "error");
  } finally {
    loading.value = false;
  }
}

function nueva() {
  editing.value = null;
  form.value = {
    area_name: "",
    policy_code: "",
    policy_description: "",
    billing_customer_id: null,
    warranty_type: 0,
    active: true,
  };
  empresaQuery.value = "";
  empresas.value = [];
  mostrar.value = true;
}

function editar(area: WorkArea) {
  editing.value = area;
  form.value = {
    area_name: area.area_name,
    policy_code: area.policy_code,
    policy_description: area.policy_description ?? "",
    billing_customer_id: area.billing_customer_id,
    warranty_type: area.warranty_type,
    active: area.active,
  };
  empresaQuery.value = area.billing_customer_name ?? "";
  empresas.value = [];
  mostrar.value = true;
}

async function buscarEmpresas() {
  empresaOpen.value = true;
  try {
    const r = await apiGet<{ items: Customer[] }>("/customers", {
      params: { search: empresaQuery.value || undefined, page_size: 20 },
    });
    empresas.value = r.items;
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudieron cargar los clientes"), "error");
  }
}

function elegirEmpresa(c: Customer) {
  form.value.billing_customer_id = c.id;
  empresaQuery.value = c.name;
  empresaOpen.value = false;
}

/** La empresa escrita tiene que ser una del maestro: si no, no se guarda nada. */
function empresaValida(): boolean {
  if (!empresaQuery.value.trim()) {
    form.value.billing_customer_id = null;
    return true;
  }
  const t = normalizar(empresaQuery.value);
  const exacta = empresas.value.find((c) => normalizar(c.name) === t);
  if (exacta) {
    form.value.billing_customer_id = exacta.id;
    return true;
  }
  return form.value.billing_customer_id !== null;
}

async function guardar() {
  if (!form.value.area_name.trim()) return;
  if (!empresaValida()) {
    toast.push("Esa empresa no está en la lista de clientes: elegila o borrá el texto.", "error");
    return;
  }
  guardando.value = true;
  const payload = {
    area_name: form.value.area_name.trim(),
    policy_code: form.value.policy_code.trim().toUpperCase(),
    policy_description: form.value.policy_description.trim() || null,
    billing_customer_id: form.value.billing_customer_id,
    warranty_type: form.value.warranty_type,
    active: form.value.active,
  };
  try {
    if (editing.value) {
      const actualizada = await apiPatch<WorkArea>(`/work-areas/${editing.value.id}`, payload);
      areas.value = areas.value.map((a) => (a.id === actualizada.id ? actualizada : a));
      toast.push("Área actualizada", "success");
    } else {
      const nueva = await apiPost<WorkArea>("/work-areas", payload);
      areas.value = [...areas.value, nueva];
      toast.push("Área creada", "success");
    }
    // El picker de la recepción y el de la ficha usan la misma caché: sin esto no
    // verían el área recién creada hasta recargar la página.
    invalidarAreas();
    mostrar.value = false;
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo guardar el área"), "error");
  } finally {
    guardando.value = false;
  }
}

async function alternarActivo(area: WorkArea) {
  try {
    const actualizada = await apiPatch<WorkArea>(`/work-areas/${area.id}`, { active: !area.active });
    areas.value = areas.value.map((a) => (a.id === actualizada.id ? actualizada : a));
    invalidarAreas();
    toast.push(actualizada.active ? "Área activada" : "Área desactivada", "success");
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo cambiar el estado del área"), "error");
  }
}

onMounted(load);
</script>

<template>
  <div class="card page-header">
    <div>
      <h2 style="margin: 0">Áreas de trabajo</h2>
      <p class="text-secondary" style="margin: 4px 0 0">
        {{ activos }} activas de {{ areas.length }} · {{ conEmpresa }} con empresa a liquidar.
        Cada área es una marca y su política, y de ahí salen la garantía y a quién se le liquida.
      </p>
    </div>
    <div class="toolbar">
      <input
        v-model="search"
        class="toolbar__search"
        placeholder="Buscar marca, política o empresa…"
        aria-label="Buscar área"
      />
      <div class="toolbar__filters">
        <button
          :class="['toolbar__chip', { 'is-active': filtroEstado === '' }]"
          type="button"
          @click="filtroEstado = ''"
        >
          Todas
        </button>
        <button
          :class="['toolbar__chip', { 'is-active': filtroEstado === 'active' }]"
          type="button"
          @click="filtroEstado = 'active'"
        >
          Activas ({{ activos }})
        </button>
        <button
          :class="['toolbar__chip', { 'is-active': filtroEstado === 'inactive' }]"
          type="button"
          @click="filtroEstado = 'inactive'"
        >
          Desactivadas ({{ areas.length - activos }})
        </button>
      </div>
      <button v-if="puedeAdministrar" class="btn btn--primary" type="button" @click="nueva">
        + Nueva área
      </button>
    </div>
  </div>

  <div class="card work-orders-list">
    <table v-if="filtrados.length" class="table table--cards-mobile">
      <thead>
        <tr>
          <th>Área</th>
          <th>Política</th>
          <th>Empresa a liquidar</th>
          <th>Garantía</th>
          <th>Estado</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="a in filtrados" :key="a.id">
          <td data-label="Área">
            <strong>{{ a.area_name }}</strong>
            <div class="text-muted">Código {{ a.area_code }}</div>
          </td>
          <td data-label="Política">
            <span v-if="a.policy_code">{{ a.policy_code }}</span>
            <span v-else class="text-muted">Principal</span>
            <div v-if="a.policy_description" class="text-muted">{{ a.policy_description }}</div>
          </td>
          <td data-label="Empresa a liquidar">
            <span v-if="a.billing_customer_name">{{ a.billing_customer_name }}</span>
            <span v-else class="text-muted">Nadie</span>
          </td>
          <td data-label="Garantía">
            <span :class="['badge', a.warranty_type === 0 ? 'badge--muted' : 'badge--success']">
              {{ a.warranty_label }}
            </span>
          </td>
          <td data-label="Estado">
            <span :class="['badge', a.active ? 'badge--success' : 'badge--muted']">
              {{ a.active ? "Activa" : "Desactivada" }}
            </span>
          </td>
          <td data-label="Acciones" class="mobile-card-actions">
            <template v-if="puedeAdministrar">
              <div class="toolbar">
                <button class="btn btn--ghost btn--sm" type="button" @click="editar(a)">Editar</button>
                <button class="btn btn--ghost btn--sm" type="button" @click="alternarActivo(a)">
                  {{ a.active ? "Desactivar" : "Activar" }}
                </button>
              </div>
            </template>
            <span v-else class="text-muted">—</span>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state">
      <template v-if="loading">Cargando áreas…</template>
      <template v-else-if="search">Ningún área coincide con “{{ search }}”.</template>
      <template v-else>Todavía no hay áreas en esta empresa.</template>
    </div>
  </div>

  <div v-if="mostrar" class="modal-backdrop" @click.self="mostrar = false">
    <div class="modal area-modal">
      <div class="flex flex--between">
        <h2>{{ editing ? "Editar área" : "Nueva área" }}</h2>
        <button class="btn btn--ghost" type="button" @click="mostrar = false">×</button>
      </div>
      <form @submit.prevent="guardar">
        <div class="field">
          <label for="area-nombre">Marca / área *</label>
          <input
            id="area-nombre"
            v-model="form.area_name"
            required
            maxlength="120"
            placeholder="Ej.: WHIRLPOOL GARANTIAS"
          />
        </div>
        <div class="field__row">
          <div class="field">
            <label for="area-politica">Política (código)</label>
            <input
              id="area-politica"
              v-model="form.policy_code"
              maxlength="20"
              placeholder="Ej.: AGU"
            />
            <small class="text-muted">Vacío = política principal del área.</small>
          </div>
          <div class="field">
            <label for="area-garantia">Tipo de garantía *</label>
            <select id="area-garantia" v-model.number="form.warranty_type">
              <option v-for="t in TIPOS_GARANTIA" :key="t.valor" :value="t.valor">{{ t.texto }}</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label for="area-descripcion">Descripción de la política</label>
          <input id="area-descripcion" v-model="form.policy_description" maxlength="150" />
        </div>
        <div class="field empresa-picker">
          <label for="area-empresa">Empresa a liquidar</label>
          <input
            id="area-empresa"
            v-model="empresaQuery"
            autocomplete="off"
            placeholder="Buscar la marca o empresa…"
            @focus="buscarEmpresas"
            @input="form.billing_customer_id = null; buscarEmpresas()"
          />
          <div v-if="empresaOpen && empresas.length" class="empresa-picker__menu">
            <button
              v-for="c in empresas"
              :key="c.id"
              type="button"
              class="empresa-picker__option"
              @mousedown.prevent="elegirEmpresa(c)"
            >
              <strong>{{ c.name }}</strong>
              <span>{{ c.customer_type === "COMPANY" ? "Empresa" : "Persona" }}</span>
            </button>
          </div>
          <small class="text-muted">
            Sin empresa a liquidar, las órdenes de esta área no entran al cierre a marcas.
          </small>
        </div>
        <div class="field area-activo">
          <label class="area-activo__label">
            <input v-model="form.active" type="checkbox" />
            Área activa (se puede elegir al armar una orden)
          </label>
        </div>
        <div class="flex flex--between" style="margin-top: 18px">
          <button class="btn btn--ghost" type="button" @click="mostrar = false">Cancelar</button>
          <button class="btn btn--primary" type="submit" :disabled="guardando || !form.area_name.trim()">
            {{ guardando ? "Guardando…" : editing ? "Guardar cambios" : "Crear área" }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.area-modal {
  width: min(620px, 100%);
  max-height: 92vh;
  overflow: auto;
}
.empresa-picker {
  position: relative;
}
.empresa-picker__menu {
  position: absolute;
  z-index: 30;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  margin-top: 6px;
  padding: 6px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.35);
  max-height: 240px;
  overflow: auto;
}
.empresa-picker__option {
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
.empresa-picker__option:hover {
  background: rgba(59, 130, 246, 0.14);
}
.empresa-picker__option span {
  font-size: 12px;
  color: var(--color-text-muted);
}
.area-activo__label {
  display: flex;
  align-items: center;
  gap: 9px;
  text-transform: none;
  letter-spacing: 0;
  font-size: 13px;
  color: var(--color-text-primary);
}
.area-activo__label input {
  width: auto;
}
</style>
