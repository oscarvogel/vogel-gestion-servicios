<script setup lang="ts">
import { onMounted, ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import Modal from "../components/Modal.vue";
import { apiGet, apiPost, apiPatch, apiPut, getApiErrorMessage } from "../lib/api";
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
  if (isPlatformView.value) void loadAi(item.id);
}

/**
 * El plan de IA de la empresa: si se le vendio el adicional, con que techo, y cuanto llevo
 * gastado del mes. Es la unica pantalla desde donde se cambia — en Parametros el admin de la
 * empresa lo ve pero no lo puede tocar, y en el backend el PATCH lo corta con 403.
 */
interface AiPlan {
  enabled: boolean;
  monthly_quota_usd: number;
  monthly_request_limit: number;
  usage_requests: number;
  usage_cost_usd: number;
  usage_input_tokens: number;
  usage_output_tokens: number;
  last_period_cost_usd: number;
  over_quota: boolean;
  quota_exhausted: boolean;
}
const ai = ref<AiPlan>({
  enabled: false, monthly_quota_usd: 0, monthly_request_limit: 0,
  usage_requests: 0, usage_cost_usd: 0, usage_input_tokens: 0, usage_output_tokens: 0,
  last_period_cost_usd: 0, over_quota: false, quota_exhausted: false,
});
const aiGuardado = ref<AiPlan | null>(null);
const aiSaving = ref(false);
const aiError = ref("");

async function loadAi(companyId: number) {
  aiError.value = "";
  try {
    const datos = await apiGet<AiPlan>(`/companies/${companyId}/ai`);
    ai.value = datos;
    // Copia de lo que esta guardado, para el boton deshabilitado mientras no cambie nada.
    aiGuardado.value = { ...datos };
  } catch (e) {
    aiError.value = getApiErrorMessage(e);
  }
}

const aiDirty = computed(
  () => !aiGuardado.value || JSON.stringify(ai.value) !== JSON.stringify(aiGuardado.value),
);

function toggleAi() {
  ai.value.enabled = !ai.value.enabled;
}

async function saveAi() {
  if (!editing.value || aiSaving.value) return;
  aiSaving.value = true;
  aiError.value = "";
  try {
    const datos = await apiPut<AiPlan>(`/companies/${editing.value.id}/ai`, {
      enabled: ai.value.enabled,
      monthly_quota_usd: Number(ai.value.monthly_quota_usd) || 0,
      monthly_request_limit: Number(ai.value.monthly_request_limit) || 0,
    });
    ai.value = datos;
    aiGuardado.value = { ...datos };
    toasts.push("Plan de IA actualizado", "success");
  } catch (e) {
    aiError.value = getApiErrorMessage(e);
  } finally {
    aiSaving.value = false;
  }
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

function viewUsers(item: CompanyItem) {
  router.push({ name: "users", query: { company_id: String(item.id) } });
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
  
    <div class="card page-header">
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
        <button class="btn btn--primary desktop-primary-action" type="button" @click="openCreate">+ Nueva empresa</button>
      </div><button class="mobile-fab" type="button" aria-label="Nueva empresa" @click="openCreate">+<span>Empresa</span></button>
    </div>

    <div class="card">
      <table v-if="items.length" class="table table--cards-mobile">
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
            <td data-label="Empresa">
              <strong>{{ item.name }}</strong>
              <div class="text-muted" style="font-size:12px">{{ item.slug }}</div>
            </td>
            <td data-label="CUIT">{{ item.tax_id || "—" }}</td>
            <td data-label="Usuarios">{{ item.user_count }}</td>
            <td data-label="Estado">
              <span :class="['badge', item.active ? 'badge--success' : 'badge--muted']">
                {{ item.active ? 'Activa' : 'Inactiva' }}
              </span>
            </td>
            <td data-label="Acciones" class="mobile-card-actions">
              <div class="flex gap-8">
                <button class="btn btn--ghost btn--sm" type="button" @click="openEdit(item)">Editar</button>
                <button class="btn btn--ghost btn--sm" type="button" @click="toggleActive(item)">
                  {{ item.active ? 'Desactivar' : 'Activar' }}
                </button>
                <button
                  v-if="isPlatformView"
                  class="btn btn--ghost btn--sm"
                  type="button"
                  @click="viewUsers(item)"
                >Usuarios ({{ item.user_count }})</button>
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

        <!--
          El adicional de IA se vende desde acá, y no desde Parametros: es configuracion
          comercial de la plataforma, no del cliente. En la pantalla de Parametros el
          administrador de la empresa la ve, pero no la puede tocar.
        -->
        <section v-if="editing && isPlatformView" class="ai-plan">
          <header class="ai-plan__head">
            <h3>Adicional de IA</h3>
            <span v-if="aiSaving" class="text-muted">Guardando…</span>
          </header>
          <p class="text-secondary ai-plan__intro">
            Solo vos lo podés cambiar. La empresa lo ve en su pantalla de Parámetros, apagado.
          </p>

          <div v-if="aiError" class="ai-plan__error">{{ aiError }}</div>

          <label class="ai-plan__switch">
            <input type="checkbox" :checked="ai.enabled" :disabled="aiSaving" @change="toggleAi" />
            <span>{{ ai.enabled ? "IA habilitada para esta empresa" : "IA no vendida a esta empresa" }}</span>
          </label>

          <div class="ai-plan__grid">
            <div class="field">
              <label>Cuota mensual (USD)</label>
              <input
                v-model.number="ai.monthly_quota_usd" type="number" min="0" step="0.01"
                :disabled="aiSaving"
              />
              <small class="text-muted">0 = sin cuota. Alcanzarla frena la IA para esa empresa.</small>
            </div>
            <div class="field">
              <label>Pedidos por mes</label>
              <input
                v-model.number="ai.monthly_request_limit" type="number" min="0" step="1"
                :disabled="aiSaving"
              />
              <small class="text-muted">0 = sin límite.</small>
            </div>
          </div>

          <div class="ai-plan__usage">
            <span>Este mes: <strong>{{ ai.usage_requests }}</strong> pedidos · <strong>$ {{ ai.usage_cost_usd.toFixed(4) }}</strong> estimado</span>
            <span v-if="ai.quota_exhausted" class="ai-plan__warn">Cuota agotada</span>
            <span v-else-if="ai.over_quota" class="ai-plan__warn">Techo de pedidos alcanzado</span>
          </div>

          <div class="flex flex--between" style="margin-top:14px">
            <span class="text-muted">Último período: $ {{ ai.last_period_cost_usd.toFixed(4) }}</span>
            <button
              class="btn btn--primary btn--sm" type="button"
              :disabled="aiSaving || !aiDirty" @click="saveAi"
            >
              Guardar el plan
            </button>
          </div>
        </section>

        <div class="flex flex--between" style="margin-top:18px">
          <button class="btn btn--ghost" type="button" @click="showForm = false">Cancelar</button>
          <button class="btn btn--primary" type="submit">Guardar</button>
        </div>
      </form>
    </Modal>
  
</template>
<style scoped>
.page-wrap { display: flex; flex-direction: column; gap: 24px; }
/* El plan de IA va separado del formulario de la empresa, con su propio boton de guardar: son
   dos cosas distintas y guardarlas juntas haria que tocar el nombre guardara el plan. */
.ai-plan {
  margin-top: 18px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.45);
}
.ai-plan__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.ai-plan__head h3 { margin: 0; }
.ai-plan__intro { margin: 6px 0 12px; font-size: 13px; }
.ai-plan__switch {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 14px;
  margin-bottom: 12px;
}
.ai-plan__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.ai-plan__grid .field { display: flex; flex-direction: column; gap: 4px; }
.ai-plan__grid small { font-size: 11px; }
.ai-plan__usage {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
  font-size: 13px;
}
.ai-plan__warn {
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11px;
  background: rgba(251, 191, 36, 0.16);
  color: #fbbf24;
}
.ai-plan__error {
  margin-bottom: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  background: rgba(239, 68, 68, 0.14);
  color: #ef4444;
}
@media (max-width: 600px) { .ai-plan__grid { grid-template-columns: 1fr; } }
</style>
