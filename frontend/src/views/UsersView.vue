<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import Modal from "../components/Modal.vue";
import { apiGet, apiPost, apiPatch } from "../lib/api";
import { useSessionStore, type CompanyOption } from "../stores/session";
import { useToastStore } from "../stores/toasts";

interface UserItem {
  id: number;
  email: string;
  full_name: string;
  active: boolean;
  is_superadmin: boolean;
  created_at: string;
  memberships: Array<{
    company_id: number;
    company_name: string;
    company_slug: string | null;
    company_active: boolean;
    is_admin: boolean;
    role: string;
    active: boolean;
  }>;
}

const session = useSessionStore();
const toasts = useToastStore();
const route = useRoute();
const router = useRouter();

const items = ref<UserItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const search = ref("");
const activeFilter = ref<"" | "active" | "inactive">("");
const loading = ref(false);
const showForm = ref(false);
const editing = ref<UserItem | null>(null);

const form = ref({
  email: "",
  full_name: "",
  password: "",
  memberships: [] as Array<{
    company_id: number;
    role: "ADMIN" | "MEMBER";
    is_admin: boolean;
    active: boolean;
  }>,
});

const companies = ref<CompanyOption[]>([]);
const companyId = ref<number | "all">("all");

const canManage = computed(() => session.hasPermission("users.create"));
const selectedCompany = computed(() =>
  companyId.value === "all"
    ? null
    : companies.value.find((company) => company.id === companyId.value) ?? null,
);

async function loadCompanies() {
  try {
    companies.value = await session.loadCompanies();
  } catch (_) {
    companies.value = [];
  }
}

async function load() {
  if (!session.hasPermission("users.view")) {
    items.value = [];
    return;
  }
  loading.value = true;
  try {
    const params: Record<string, string | number> = {
      page: page.value,
      page_size: pageSize.value,
    };
    if (search.value) params.search = search.value;
    if (activeFilter.value === "active") params.active = true;
    if (activeFilter.value === "inactive") params.active = false;
    if (session.isSuperAdmin && companyId.value !== "all") {
      params.company_id = companyId.value as number;
    }
    const data = await apiGet<{
      items: UserItem[];
      total: number;
      page: number;
      page_size: number;
    }>("/users", { params });
    items.value = data.items;
    total.value = data.total;
  } catch (err) {
    toasts.push("No se pudo cargar usuarios", "error");
  } finally {
    loading.value = false;
  }
}

watch([search, activeFilter, companyId], () => {
  page.value = 1;
  if (session.isSuperAdmin) {
    const query =
      companyId.value === "all" ? {} : { company_id: String(companyId.value) };
    router.replace({ name: "users", query });
  }
  load();
});
watch(page, load);

onMounted(async () => {
  await loadCompanies();
  const requestedCompanyId = Number(route.query.company_id);
  if (
    session.isSuperAdmin &&
    Number.isInteger(requestedCompanyId) &&
    companies.value.some((company) => company.id === requestedCompanyId)
  ) {
    companyId.value = requestedCompanyId;
  }
  await load();
});

function openCreate() {
  editing.value = null;
  const memberships: Array<{
    company_id: number;
    role: "ADMIN" | "MEMBER";
    is_admin: boolean;
    active: boolean;
  }> = [];

  if (session.isSuperAdmin && companyId.value !== "all") {
    memberships.push({
      company_id: companyId.value as number,
      role: "MEMBER",
      is_admin: false,
      active: true,
    });
  } else if (!session.isSuperAdmin && session.activeCompany) {
    memberships.push({
      company_id: session.activeCompany.id,
      role: "MEMBER",
      is_admin: false,
      active: true,
    });
  }

  form.value = {
    email: "",
    full_name: "",
    password: "",
    memberships,
  };
  showForm.value = true;
}

function openEdit(item: UserItem) {
  editing.value = item;
  form.value = {
    email: item.email,
    full_name: item.full_name,
    password: "",
    memberships: item.memberships.map((m) => ({
      company_id: m.company_id,
      role: m.role as "ADMIN" | "MEMBER",
      is_admin: m.is_admin,
      active: m.active,
    })),
  };
  showForm.value = true;
}

async function save() {
  if (!form.value.email || !form.value.full_name) {
    toasts.push("Email y nombre son obligatorios", "error");
    return;
  }
  if (!editing.value && !form.value.password) {
    toasts.push("La contraseña inicial es obligatoria", "error");
    return;
  }
  if (!editing.value && form.value.memberships.length === 0) {
    toasts.push("Debe asignar al menos una empresa al usuario", "error");
    return;
  }
  const companyIds = form.value.memberships.map((m) => m.company_id);
  if (new Set(companyIds).size !== companyIds.length) {
    toasts.push("No puede asignar dos veces la misma empresa", "error");
    return;
  }
  try {
    if (editing.value) {
      const payload: Record<string, unknown> = {
        email: form.value.email,
        full_name: form.value.full_name,
      };
      if (form.value.password) payload.password = form.value.password;
      await apiPatch(`/users/${editing.value.id}`, payload);
      const existingCompanyIds = new Set(
        editing.value.memberships.map((membership) => membership.company_id),
      );
      const newMemberships = form.value.memberships.filter(
        (membership) => !existingCompanyIds.has(membership.company_id),
      );
      for (const membership of newMemberships) {
        await apiPost(`/users/${editing.value.id}/memberships`, membership);
      }
      toasts.push("Usuario actualizado", "success");
    } else {
      await apiPost("/users", {
        email: form.value.email,
        full_name: form.value.full_name,
        password: form.value.password,
        memberships: form.value.memberships,
      });
      toasts.push("Usuario creado", "success");
    }
    showForm.value = false;
    await load();
  } catch (err: unknown) {
    const rawDetail =
      (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
    const detail =
      rawDetail === "Email already in use"
        ? "El correo electrónico ya está registrado."
        : rawDetail || "No se pudo guardar el usuario";
    toasts.push(detail, "error");
  }
}

async function toggleActive(item: UserItem) {
  try {
    await apiPost(`/users/${item.id}/${item.active ? "disable" : "enable"}`);
    toasts.push(item.active ? "Usuario desactivado" : "Usuario activado", "success");
    await load();
  } catch (err) {
    toasts.push("No se pudo cambiar el estado", "error");
  }
}

function addMembership() {
  const used = new Set(form.value.memberships.map((membership) => membership.company_id));
  const company = companies.value.find((candidate) => !used.has(candidate.id));
  if (!company) {
    toasts.push("No hay más empresas disponibles para asignar", "error");
    return;
  }
  form.value.memberships.push({
    company_id: company.id,
    role: "MEMBER",
    is_admin: false,
    active: true,
  });
}

function removeMembership(index: number) {
  const membership = form.value.memberships[index];
  if (
    editing.value?.memberships.some(
      (existing) => existing.company_id === membership.company_id,
    )
  ) {
    toasts.push(
      "La baja de una membresía existente se gestiona desde el padrón de la empresa",
      "error",
    );
    return;
  }
  form.value.memberships.splice(index, 1);
}

function isExistingMembership(companyId: number) {
  return Boolean(
    editing.value?.memberships.some(
      (membership) => membership.company_id === companyId,
    ),
  );
}
</script>

<template>
  
    <div class="card flex flex--between" style="gap:16px;flex-wrap:wrap;align-items:center">
      <div>
        <button
          v-if="session.isSuperAdmin && selectedCompany"
          class="btn btn--ghost btn--sm"
          type="button"
          style="margin-bottom:8px"
          @click="router.push({ name: 'companies' })"
        >← Empresas</button>
        <h2 style="margin:0;font-size:20px">
          {{ selectedCompany ? `Usuarios · ${selectedCompany.name}` : 'Usuarios' }}
        </h2>
        <p class="text-secondary" style="margin:4px 0 0">
          {{ total }} usuarios ·
          {{ selectedCompany
            ? `Padrón de ${selectedCompany.name}`
            : session.activeCompany
              ? `Filtrando por ${session.activeCompany.name}`
              : 'Vista plataforma' }}
        </p>
      </div>
      <div class="toolbar">
        <input v-model="search" class="toolbar__search" placeholder="Buscar por nombre o email" />
        <div class="toolbar__filters">
          <button :class="['toolbar__chip', { 'is-active': activeFilter === '' }]" type="button" @click="activeFilter = ''">Todos</button>
          <button :class="['toolbar__chip', { 'is-active': activeFilter === 'active' }]" type="button" @click="activeFilter = 'active'">Activos</button>
          <button :class="['toolbar__chip', { 'is-active': activeFilter === 'inactive' }]" type="button" @click="activeFilter = 'inactive'">Inactivos</button>
        </div>
        <select
          v-if="session.isSuperAdmin"
          v-model="companyId"
          class="toolbar__search"
          style="max-width:200px"
        >
          <option value="all">Todas las empresas</option>
          <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <button v-if="canManage" class="btn btn--primary" type="button" @click="openCreate">
          {{ selectedCompany ? `+ Usuario en ${selectedCompany.name}` : '+ Nuevo usuario' }}
        </button>
      </div>
    </div>

    <div class="card">
      <table v-if="items.length" class="table">
        <thead>
          <tr>
            <th>Usuario</th>
            <th>Email</th>
            <th>Membresías</th>
            <th>Estado</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>
              <strong>{{ item.full_name }}</strong>
              <div class="text-muted" style="font-size:12px">
                <span v-if="item.is_superadmin" class="role-chip" style="margin-right:6px">SuperAdmin</span>
                Creado {{ new Date(item.created_at).toLocaleDateString('es-AR') }}
              </div>
            </td>
            <td>{{ item.email }}</td>
            <td>
              <div class="flex gap-8" style="flex-wrap:wrap">
                <span
                  v-for="m in item.memberships"
                  :key="m.company_id"
                  :class="['role-chip', { 'role-chip--muted': !m.active }]"
                >
                  {{ m.company_name }}
                  <span v-if="m.is_admin" style="font-size:10px;letter-spacing:0.06em"> · ADMIN</span>
                </span>
                <span v-if="item.memberships.length === 0" class="text-muted">Sin membresías</span>
              </div>
            </td>
            <td>
              <span :class="['badge', item.active ? 'badge--success' : 'badge--muted']">
                {{ item.active ? 'Activo' : 'Inactivo' }}
              </span>
            </td>
            <td>
              <div class="flex gap-8">
                <button v-if="canManage" class="btn btn--ghost btn--sm" type="button" @click="openEdit(item)">Editar</button>
                <button
                  v-if="canManage && !item.is_superadmin"
                  class="btn btn--ghost btn--sm"
                  type="button"
                  @click="toggleActive(item)"
                >
                  {{ item.active ? 'Desactivar' : 'Activar' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">{{ loading ? 'Cargando…' : 'Sin usuarios' }}</div>
    </div>

    <Modal :open="showForm" :title="editing ? 'Editar usuario' : 'Nuevo usuario'" @close="showForm = false">
      <form @submit.prevent="save">
        <div class="field__row">
          <div class="field">
            <label>Nombre completo *</label>
            <input v-model="form.full_name" required />
          </div>
          <div class="field">
            <label>Email *</label>
            <input v-model="form.email" type="email" required />
          </div>
        </div>
        <div class="field">
          <label>{{ editing ? 'Nueva contraseña (opcional)' : 'Contraseña inicial *' }}</label>
          <input v-model="form.password" type="password" minlength="8" />
        </div>

        <template v-if="session.isSuperAdmin">
          <hr style="border:none;border-top:1px solid var(--color-border);margin:14px 0" />
          <p class="card__title">Membresías *</p>
          <p v-if="form.memberships.length === 0" class="text-secondary" style="margin:0 0 12px">
            Asigná al menos una empresa para poder crear el usuario.
          </p>
          <div v-for="(m, idx) in form.memberships" :key="idx" class="field__row" style="align-items:end">
            <div class="field">
              <label>Empresa</label>
              <select v-model.number="m.company_id">
                <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
            <div class="field">
              <label>Rol</label>
              <select v-model="m.role">
                <option value="MEMBER">Miembro</option>
                <option value="ADMIN">Admin</option>
              </select>
            </div>
            <div class="field" style="flex-direction:row;align-items:center;gap:8px">
              <label style="margin:0">
                <input type="checkbox" v-model="m.is_admin" /> Admin
              </label>
            </div>
            <button
              class="btn btn--ghost btn--sm"
              type="button"
              :disabled="isExistingMembership(m.company_id)"
              @click="removeMembership(idx)"
            >
              {{ isExistingMembership(m.company_id) ? 'Asignada' : 'Quitar' }}
            </button>
          </div>
          <button class="btn btn--ghost btn--sm" type="button" @click="addMembership">+ Agregar membresía</button>
        </template>

        <div class="flex flex--between" style="margin-top:18px">
          <button class="btn btn--ghost" type="button" @click="showForm = false">Cancelar</button>
          <button class="btn btn--primary" type="submit">Guardar</button>
        </div>
      </form>
    </Modal>
  
</template>
<style scoped>
.page-wrap { display: flex; flex-direction: column; gap: 24px; }
</style>
