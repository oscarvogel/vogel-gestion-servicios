<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import Modal from "../components/Modal.vue";
import { apiGet, apiPost, apiPatch } from "../lib/api";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";

interface Permission {
  id: number;
  code: string;
  namespace: string;
  description: string | null;
}

interface Role {
  id: number;
  company_id: number | null;
  name: string;
  description: string | null;
  is_system: boolean;
  active: boolean;
  permission_codes: string[];
}

const session = useSessionStore();
const toasts = useToastStore();

const roles = ref<Role[]>([]);
const permissions = ref<Permission[]>([]);
const loading = ref(false);
const showForm = ref(false);
const editing = ref<Role | null>(null);

const form = ref({
  name: "",
  description: "",
  active: true,
  permission_ids: [] as number[],
});

const canManage = computed(() => session.hasPermission("roles.manage"));

async function load() {
  loading.value = true;
  try {
    const [rolesData, permissionsData] = await Promise.all([
      apiGet<{ items: Role[] }>("/roles"),
      apiGet<Permission[]>("/roles/permissions"),
    ]);
    roles.value = rolesData.items;
    permissions.value = permissionsData;
  } catch (err) {
    toasts.push("No se pudieron cargar los roles", "error");
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function openCreate() {
  editing.value = null;
  form.value = {
    name: "",
    description: "",
    active: true,
    permission_ids: [],
  };
  showForm.value = true;
}

function openEdit(role: Role) {
  editing.value = role;
  form.value = {
    name: role.name,
    description: role.description ?? "",
    active: role.active,
    permission_ids: permissions.value
      .filter((p) => role.permission_codes.includes(p.code))
      .map((p) => p.id),
  };
  showForm.value = true;
}

async function save() {
  if (!form.value.name) {
    toasts.push("El nombre es obligatorio", "error");
    return;
  }
  try {
    if (editing.value) {
      await apiPatch(`/roles/${editing.value.id}`, {
        name: form.value.name,
        description: form.value.description || null,
        active: form.value.active,
        permission_ids: form.value.permission_ids,
      });
      toasts.push("Rol actualizado", "success");
    } else {
      await apiPost("/roles", {
        name: form.value.name,
        description: form.value.description || null,
        active: form.value.active,
        permission_ids: form.value.permission_ids,
      });
      toasts.push("Rol creado", "success");
    }
    showForm.value = false;
    await load();
  } catch (err: unknown) {
    const detail =
      (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail || "No se pudo guardar";
    toasts.push(detail, "error");
  }
}

const grouped = computed(() => {
  const map: Record<string, Permission[]> = {};
  for (const p of permissions.value) {
    if (!map[p.namespace]) map[p.namespace] = [];
    map[p.namespace].push(p);
  }
  return map;
});
</script>

<template>
  
    <div class="card flex flex--between" style="gap:16px;align-items:center;flex-wrap:wrap">
      <div>
        <h2 style="margin:0;font-size:20px">Roles y permisos</h2>
        <p class="text-secondary" style="margin:4px 0 0">
          {{ roles.length }} roles · {{ permissions.length }} permisos
        </p>
      </div>
      <button v-if="canManage" class="btn btn--primary" type="button" @click="openCreate">
        + Nuevo rol
      </button>
    </div>

    <div class="card">
      <table v-if="roles.length" class="table">
        <thead>
          <tr>
            <th>Rol</th>
            <th>Descripción</th>
            <th>Permisos</th>
            <th>Estado</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="role in roles" :key="role.id">
            <td>
              <strong>{{ role.name }}</strong>
              <span v-if="role.is_system" class="role-chip" style="margin-left:8px">Sistema</span>
            </td>
            <td class="text-muted">{{ role.description || '—' }}</td>
            <td>
              <span class="text-secondary" style="font-size:12px">
                {{ role.permission_codes.length }} permisos asignados
              </span>
              <div class="flex gap-8" style="flex-wrap:wrap;margin-top:6px">
                <span v-for="code in role.permission_codes.slice(0,4)" :key="code" class="role-chip">{{ code }}</span>
                <span v-if="role.permission_codes.length > 4" class="text-muted">+{{ role.permission_codes.length - 4 }}</span>
              </div>
            </td>
            <td>
              <span :class="['badge', role.active ? 'badge--success' : 'badge--muted']">
                {{ role.active ? 'Activo' : 'Inactivo' }}
              </span>
            </td>
            <td>
              <button
                v-if="canManage && !role.is_system"
                class="btn btn--ghost btn--sm"
                type="button"
                @click="openEdit(role)"
              >Editar</button>
              <span v-else-if="role.is_system" class="text-muted" style="font-size:12px">Protegido</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">{{ loading ? 'Cargando…' : 'Sin roles definidos' }}</div>
    </div>

    <Modal :open="showForm" :title="editing ? 'Editar rol' : 'Nuevo rol'" @close="showForm = false">
      <form @submit.prevent="save">
        <div class="field">
          <label>Nombre *</label>
          <input v-model="form.name" required />
        </div>
        <div class="field">
          <label>Descripción</label>
          <textarea v-model="form.description" rows="2" />
        </div>
        <div class="field" style="flex-direction:row;align-items:center;gap:8px">
          <label style="margin:0"><input type="checkbox" v-model="form.active" /> Activo</label>
        </div>

        <hr style="border:none;border-top:1px solid var(--color-border);margin:14px 0" />
        <p class="card__title">Permisos</p>
        <div v-for="(items, ns) in grouped" :key="ns" style="margin-bottom:14px">
          <strong style="font-size:13px;letter-spacing:0.06em;text-transform:uppercase">{{ ns }}</strong>
          <div class="flex" style="flex-wrap:wrap;gap:8px;margin-top:6px">
            <label
              v-for="p in items"
              :key="p.id"
              class="role-chip"
              :class="{ 'role-chip--selected': form.permission_ids.includes(p.id) }"
              style="cursor:pointer"
            >
              <input
                type="checkbox"
                :value="p.id"
                v-model="form.permission_ids"
                style="margin:0"
              />
              {{ p.code }}
            </label>
          </div>
        </div>

        <div class="flex flex--between" style="margin-top:18px">
          <button class="btn btn--ghost" type="button" @click="showForm = false">Cancelar</button>
          <button class="btn btn--primary" type="submit">Guardar</button>
        </div>
      </form>
    </Modal>
  
</template>

<style scoped>
.role-chip--selected {
  background: rgba(45, 124, 255, 0.36);
  border-color: rgba(45, 124, 255, 0.7);
}
</style>
<style scoped>
.page-wrap { display: flex; flex-direction: column; gap: 24px; }
</style>
