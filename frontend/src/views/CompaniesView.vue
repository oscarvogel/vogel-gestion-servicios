<script setup lang="ts">
import { onMounted, ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import Modal from "../components/Modal.vue";
import { apiGet, apiPost, apiPatch } from "../lib/api";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";

interface CompanyItem {
  id: number;
  name: string;
  slug: string | null;
  legal_name: string | null;
  tax_id: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  notes: string | null;
  timezone: string;
  locale: string;
  active: boolean;
  user_count: number;
  created_at: string;
  updated_at: string;
}

interface CompanyListResponse {
  items: CompanyItem[];
  total: number;
  page: number;
  page_size: number;
}

const session = useSessionStore();
const router = useRouter();
const toasts = useToastStore();

const items = ref<CompanyItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const search = ref("");
const activeFilter = ref<"" | "active" | "inactive">("");
const loading = ref(false);

const editing = ref<CompanyItem | null>(null);
const showForm = ref(false);

const form = ref({
  name: "",
  legal_name: "",
  tax_id: "",
  slug: "",
  email: "",
  phone: "",
  address: "",
  notes: "",
  timezone: "America/Argentina/Cordoba",
  locale: "es-AR",
  admin_email: "",
  admin_full_name: "",
  admin_password: "",
});

const isPlatformView = computed(() => session.isSuperAdmin);

async function load() {
  if (!session.isSuperAdmin) {
    router.replace({ name: "dashboard" });
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
    const data = await apiGet<CompanyListResponse>("/companies", { params });
    items.value = data.items;
    total.value = data.total;
  } catch (err) {
    toasts.push("No se pudo cargar el listado", "error");
  } finally {
    loading.value = false;
  }
}

watch([search, activeFilter], () => {
  page.value = 1;
  load();
});

watch(page, load);

onMounted(load);

function openCreate() {
  editing.value = null;
  form.value = {
    name: "",
    legal_name: "",
    tax_id: "",
    slug: "",
    email: "",
    phone: "",
    address: "",
    notes: "",
    timezone: "America/Argentina/Cordoba",
    locale: "es-AR",
    admin_email: "",
    admin_full_name: "",
    admin_password: "",
  };
  showForm.value = true;
}

function openEdit(item: CompanyItem) {
  editing.value = item;
  form.value = {
    name: item.name,
    legal_name: item.legal_name ?? "",
    tax_id: item.tax_id ?? "",
    slug: item.slug ?? "",
    email: item.email ?? "",
    phone: item.phone ?? "",
    address: item.address ?? "",
    notes: item.notes ?? "",
    timezone: item.timezone,
    locale: item.locale,
    admin_email: "",
    admin_full_name: "",
    admin_password: "",
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
      await apiPatch(`/companies/${editing.value.id}`, {
        name: form.value.name,
        legal_name: form.value.legal_name || null,
        tax_id: form.value.tax_id || null,
        slug: form.value.slug || null,
        email: form.value.email || null,
        phone: form.value.phone || null,
        address: form.value.address || null,
        notes: form.value.notes || null,
        timezone: form.value.timezone,
        locale: form.value.locale,
      });
      toasts.push("Empresa actualizada", "success");
    } else {
      const payload = {
        name: form.value.name,
        legal_name: form.value.legal_name || null,
        tax_id: form.value.tax_id || null,
        slug: form.value.slug || null,
        email: form.value.email || null,
        phone: form.value.phone || null,
        address: form.value.address || null,
        notes: form.value.notes || null,
        timezone: form.value.timezone,
        locale: form.value.locale,
        admin_email: form.value.admin_email || null,
        admin_full_name: form.value.admin_full_name || null,
        admin_password: form.value.admin_password || null,
      };
      await apiPost("/companies", payload);
      toasts.push("Empresa creada", "success");
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

async function toggleActive(item: CompanyItem) {
  try {
    await apiPost(`/companies/${item.id}/${item.active ? "disable" : "enable"}`);
    toasts.push(item.active ? "Empresa desactivada" : "Empresa activada", "success");
    await load();
  } catch (err) {
    toasts.push("No se pudo cambiar el estado", "error");
  }
}

async function enterCompany(item: CompanyItem) {
  try {
    await session.selectCompany({
      id: item.id,
      name: item.name,
      slug: item.slug,
      active: item.active,
      is_admin: true,
    });
    router.push({ name: "dashboard" });
  } catch (err) {
    toasts.push("No se pudo entrar al contexto", "error");
  }
}
</script>

<template>
  
    <div class="card flex flex--between" style="gap:16px;align-items:center;flex-wrap:wrap">
      <div>
        <h2 style="margin:0;font-size:20px">Empresas</h2>
        <p class="text-secondary" style="margin:4px 0 0">Total: {{ total }}</p>
      </div>
      <div class="toolbar">
        <input
          v-model="search"
          class="toolbar__search"
          placeholder="Buscar por nombre, CUIT o slug"
        />
        <div class="toolbar__filters">
          <button
            :class="['toolbar__chip', { 'is-active': activeFilter === '' }]"
            type="button"
            @click="activeFilter = ''"
          >Todas</button>
          <button
            :class="['toolbar__chip', { 'is-active': activeFilter === 'active' }]"
            type="button"
            @click="activeFilter = 'active'"
          >Activas</button>
          <button
            :class="['toolbar__chip', { 'is-active': activeFilter === 'inactive' }]"
            type="button"
            @click="activeFilter = 'inactive'"
          >Inactivas</button>
        </div>
        <button class="btn btn--primary" type="button" @click="openCreate">+ Nueva empresa</button>
      </div>
    </div>

    <div class="card">
      <table v-if="items.length" class="table">
        <thead>
          <tr>
            <th>Empresa</th>
            <th>CUIT</th>
            <th>Usuarios</th>
            <th>Estado</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>
              <strong>{{ item.name }}</strong>
              <div class="text-muted" style="font-size:12px">{{ item.slug }}</div>
            </td>
            <td>{{ item.tax_id || "—" }}</td>
            <td>{{ item.user_count }}</td>
            <td>
              <span :class="['badge', item.active ? 'badge--success' : 'badge--muted']">
                {{ item.active ? 'Activa' : 'Inactiva' }}
              </span>
            </td>
            <td>
              <div class="flex gap-8">
                <button class="btn btn--ghost btn--sm" type="button" @click="openEdit(item)">Editar</button>
                <button class="btn btn--ghost btn--sm" type="button" @click="toggleActive(item)">
                  {{ item.active ? 'Desactivar' : 'Activar' }}
                </button>
                <button
                  v-if="isPlatformView && item.active"
                  class="btn btn--primary btn--sm"
                  type="button"
                  @click="enterCompany(item)"
                >Entrar</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">
        {{ loading ? 'Cargando…' : 'Sin empresas para mostrar' }}
      </div>
    </div>

    <Modal :open="showForm" :title="editing ? 'Editar empresa' : 'Nueva empresa'" @close="showForm = false">
      <form @submit.prevent="save">
        <div class="field__row">
          <div class="field">
            <label>Nombre *</label>
            <input v-model="form.name" required />
          </div>
          <div class="field">
            <label>Razón social</label>
            <input v-model="form.legal_name" />
          </div>
        </div>
        <div class="field__row">
          <div class="field">
            <label>CUIT / Tax ID</label>
            <input v-model="form.tax_id" />
          </div>
          <div class="field">
            <label>Slug</label>
            <input v-model="form.slug" placeholder="empresa-demo" />
          </div>
        </div>
        <div class="field__row">
          <div class="field">
            <label>Email</label>
            <input v-model="form.email" type="email" />
          </div>
          <div class="field">
            <label>Teléfono</label>
            <input v-model="form.phone" />
          </div>
        </div>
        <div class="field">
          <label>Dirección</label>
          <input v-model="form.address" />
        </div>
        <div class="field">
          <label>Notas</label>
          <textarea v-model="form.notes" rows="2" />
        </div>

        <template v-if="!editing">
          <hr style="border:none;border-top:1px solid var(--color-border);margin:14px 0" />
          <p class="card__title">Administrador inicial (opcional)</p>
          <div class="field__row">
            <div class="field">
              <label>Email admin</label>
              <input v-model="form.admin_email" type="email" />
            </div>
            <div class="field">
              <label>Nombre completo</label>
              <input v-model="form.admin_full_name" />
            </div>
          </div>
          <div class="field">
            <label>Contraseña inicial</label>
            <input v-model="form.admin_password" type="password" minlength="8" />
          </div>
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
