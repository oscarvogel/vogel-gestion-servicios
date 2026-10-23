<script setup lang="ts">
/**
 * Maestro de técnicos de la empresa.
 *
 * El legacy (CiberBrain) no tenía un maestro de técnicos: en cada orden los "intervinientes"
 * eran personas sueltas. El importador armó uno con esos nombres para poder consultar el
 * histórico, pero no había forma de dar de alta a nadie ni de asignarlo a una orden.
 *
 * Acá se administra: alta, renombre y activar/desactivar. Los desactivados siguen en las
 * órdenes donde ya estaban (el histórico no se toca), pero no se pueden asignar.
 */
import { computed, onMounted, ref } from "vue";

import { apiGet, apiPatch, apiPost, getApiErrorMessage } from "../lib/api";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";

interface Technician {
  id: number;
  name: string;
  active: boolean;
  legacy_code: number | null;
}

const session = useSessionStore();
const toast = useToastStore();

const technicians = ref<Technician[]>([]);
const search = ref("");
const newName = ref("");
const creating = ref(false);
const editingId = ref<number | null>(null);
const editingName = ref("");
const loading = ref(false);

/** Compara sin mayúsculas ni acentos: "britéz" encuentra a "Britez". */
function normalizar(texto: string): string {
  return texto
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim();
}

const filtrados = computed<Technician[]>(() => {
  const query = normalizar(search.value);
  if (!query) return technicians.value;
  return technicians.value.filter((t) => normalizar(t.name).includes(query));
});

const activos = computed(() => technicians.value.filter((t) => t.active).length);
const puedeAdministrar = computed(() => session.hasPermission("technicians.manage"));

async function load() {
  loading.value = true;
  try {
    technicians.value = await apiGet<Technician[]>("/technicians");
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo cargar el maestro de técnicos"), "error");
  } finally {
    loading.value = false;
  }
}

async function crear() {
  const nombre = newName.value.trim();
  if (!nombre || creating.value) return;
  creating.value = true;
  try {
    const tecnico = await apiPost<Technician>("/technicians", { name: nombre });
    technicians.value = [...technicians.value, tecnico].sort((a, b) =>
      a.name.localeCompare(b.name, "es"),
    );
    newName.value = "";
    toast.push(`Técnico ${tecnico.name} agregado`, "success");
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo agregar el técnico"), "error");
  } finally {
    creating.value = false;
  }
}

function empezarEdicion(tecnico: Technician) {
  editingId.value = tecnico.id;
  editingName.value = tecnico.name;
}

function cancelarEdicion() {
  editingId.value = null;
  editingName.value = "";
}

async function guardarEdicion(tecnico: Technician) {
  const nombre = editingName.value.trim();
  if (!nombre) return;
  try {
    const actualizado = await apiPatch<Technician>(`/technicians/${tecnico.id}`, { name: nombre });
    technicians.value = technicians.value.map((t) => (t.id === tecnico.id ? actualizado : t));
    cancelarEdicion();
    toast.push("Nombre actualizado", "success");
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo actualizar el técnico"), "error");
  }
}

async function alternarActivo(tecnico: Technician) {
  try {
    const actualizado = await apiPatch<Technician>(`/technicians/${tecnico.id}`, {
      active: !tecnico.active,
    });
    technicians.value = technicians.value.map((t) => (t.id === tecnico.id ? actualizado : t));
    toast.push(
      actualizado.active
        ? `${actualizado.name} quedó activo`
        : `${actualizado.name} quedó desactivado`,
      "success",
    );
  } catch (e) {
    toast.push(getApiErrorMessage(e, "No se pudo cambiar el estado del técnico"), "error");
  }
}

onMounted(load);
</script>

<template>
  <div class="card page-header">
    <div>
      <h2 style="margin: 0">Técnicos</h2>
      <p class="text-secondary" style="margin: 4px 0 0">
        {{ activos }} activos de {{ technicians.length }} · los técnicos de esta empresa son los que se pueden asignar a las órdenes de trabajo.
      </p>
    </div>
    <div class="toolbar">
      <input
        v-model="search"
        class="toolbar__search"
        placeholder="Buscar técnico…"
        aria-label="Buscar técnico"
      />
    </div>
  </div>

  <div v-if="puedeAdministrar" class="card">
    <form class="field__row" @submit.prevent="crear">
      <div class="field" style="flex: 1">
        <label for="nuevo-tecnico">Agregar un técnico</label>
        <input
          id="nuevo-tecnico"
          v-model="newName"
          placeholder="Nombre y apellido"
          maxlength="150"
        />
      </div>
      <button class="btn btn--primary" type="submit" :disabled="creating || !newName.trim()">
        {{ creating ? "Agregando…" : "+ Agregar" }}
      </button>
    </form>
    <small class="text-muted">
      El nombre no se puede repetir: si ya existe una persona con ese nombre, se avisa.
    </small>
  </div>

  <div class="card work-orders-list">
    <table v-if="filtrados.length" class="table table--cards-mobile">
      <thead>
        <tr>
          <th>Técnico</th>
          <th>Origen</th>
          <th>Estado</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in filtrados" :key="t.id">
          <td data-label="Técnico">
            <template v-if="editingId === t.id">
              <input v-model="editingName" maxlength="150" @keyup.enter="guardarEdicion(t)" />
            </template>
            <strong v-else>{{ t.name }}</strong>
          </td>
          <td data-label="Origen">
            <span class="text-muted">{{ t.legacy_code === null ? "Cargado a mano" : `Legacy #${t.legacy_code}` }}</span>
          </td>
          <td data-label="Estado">
            <span class="status-pill" :style="t.active
              ? 'background:#10B98122;color:#10B981;border-color:#10B98166'
              : 'background:#64748B22;color:#64748B;border-color:#64748B66'">
              {{ t.active ? "Activo" : "Desactivado" }}
            </span>
          </td>
          <td data-label="Acciones" class="mobile-card-actions">
            <template v-if="puedeAdministrar">
              <div v-if="editingId === t.id" class="toolbar">
                <button class="btn btn--primary btn--sm" @click="guardarEdicion(t)">Guardar</button>
                <button class="btn btn--ghost btn--sm" @click="cancelarEdicion">Cancelar</button>
              </div>
              <div v-else class="toolbar">
                <button class="btn btn--ghost btn--sm" @click="empezarEdicion(t)">Renombrar</button>
                <button class="btn btn--ghost btn--sm" @click="alternarActivo(t)">
                  {{ t.active ? "Desactivar" : "Activar" }}
                </button>
              </div>
            </template>
            <span v-else class="text-muted">—</span>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state">
      <template v-if="loading">Cargando técnicos…</template>
      <template v-else-if="search">Ningún técnico coincide con “{{ search }}”.</template>
      <template v-else>Todavía no hay técnicos en esta empresa.</template>
    </div>
  </div>
</template>
