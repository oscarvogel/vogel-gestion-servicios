<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useSessionStore } from "../stores/session";
import { apiGet } from "../lib/api";
import { useToastStore } from "../stores/toasts";

interface SuperAdminDashboard {
  kpis: {
    total_companies: number;
    active_companies: number;
    total_users: number;
    active_users: number;
    total_admins: number;
    total_superadmins: number;
  };
  recent_companies: Array<{
    id: number;
    name: string;
    slug: string | null;
    active: boolean;
    created_at: string;
  }>;
  recent_activity: unknown[];
  quick_actions: Array<{ id: string; label: string; icon: string }>;
}

const session = useSessionStore();
const toasts = useToastStore();
interface CompanyDashboard {
  total: number;
  summary: {
    open: number;
    awaiting_quote_approval: number;
    quoted: number;
    repair: number;
    completed: number;
    delivered: number;
  };
  statuses: Array<{ id: number; name: string; color: string; count: number; is_final: boolean; marks_delivered: boolean }>;
}

const data = ref<SuperAdminDashboard | null>(null);
const companyData = ref<CompanyDashboard | null>(null);
const loading = ref(false);

const firstName = computed(() => {
  const name = session.me?.full_name?.trim();
  return name ? name.split(/\s+/)[0] : "tu cuenta";
});

const contextSubtitle = computed(() => {
  if (session.isSuperAdmin) {
    return "Dashboard de Plataforma. Gestioná empresas, usuarios y la salud global del servicio.";
  }
  const companyName = session.activeCompany?.name;
  return companyName
    ? `Operás en el contexto de ${companyName}.`
    : "No hay una empresa seleccionada para esta sesión.";
});

async function load() {
  loading.value = true;
  try {
    if (session.activeCompany) {
      companyData.value = await apiGet<CompanyDashboard>("/dashboard/company");
    } else if (session.isSuperAdmin) {
      data.value = await apiGet<SuperAdminDashboard>("/dashboard/superadmin");
    }
  } catch (err: unknown) {
    toasts.push("No se pudo cargar el dashboard", "error");
  } finally {
    loading.value = false;
  }
}

onMounted(load);

const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 12) return "Buenos días";
  if (hour < 19) return "Buenas tardes";
  return "Buenas noches";
});
</script>

<template>
  
    <section class="hero hero--branding">
      <div class="hero__eyebrow">{{ session.activeCompany ? "Empresa activa" : "Plataforma Vogel" }}</div>
      <h1 class="hero__title">{{ greeting }}, {{ firstName }}.</h1>
      <p class="hero__subtitle">{{ contextSubtitle }}</p>
    </section>

    <template v-if="session.isSuperAdmin && !session.activeCompany">
      <div v-if="loading" class="card empty-state">
        <span class="spinner" /> Cargando métricas…
      </div>
      <template v-else-if="data">
        <div class="card-grid">
          <div class="card">
            <p class="card__title">Empresas totales</p>
            <div class="card__value">{{ data.kpis.total_companies }}</div>
            <p class="card__hint">{{ data.kpis.active_companies }} activas</p>
          </div>
          <div class="card">
            <p class="card__title">Usuarios</p>
            <div class="card__value">{{ data.kpis.total_users }}</div>
            <p class="card__hint">{{ data.kpis.active_users }} activos</p>
          </div>
          <div class="card">
            <p class="card__title">Administradores</p>
            <div class="card__value">{{ data.kpis.total_admins }}</div>
            <p class="card__hint">{{ data.kpis.total_superadmins }} superadmins</p>
          </div>
          <div class="card">
            <p class="card__title">Empresas activas</p>
            <div class="card__value">{{ data.kpis.active_companies }}</div>
            <p class="card__hint">Disponibles para operar</p>
          </div>
        </div>

        <div class="card">
          <p class="card__title">Empresas recientes</p>
          <table class="table">
            <thead>
              <tr>
                <th>Empresa</th>
                <th>Slug</th>
                <th>Estado</th>
                <th>Creada</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in data.recent_companies" :key="row.id">
                <td><strong>{{ row.name }}</strong></td>
                <td><code>{{ row.slug }}</code></td>
                <td>
                  <span :class="['badge', row.active ? 'badge--success' : 'badge--muted']">
                    {{ row.active ? 'Activa' : 'Inactiva' }}
                  </span>
                </td>
                <td class="text-muted">{{ new Date(row.created_at).toLocaleString('es-AR') }}</td>
              </tr>
              <tr v-if="data.recent_companies.length === 0">
                <td colspan="4" class="empty-state">Aún no hay empresas creadas.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card-grid">
          <div class="card" v-for="action in data.quick_actions" :key="action.id">
            <p class="card__title">{{ action.label }}</p>
            <p class="text-secondary" style="font-size:13px;margin:0">
              Disponible desde el menú lateral.
            </p>
          </div>
        </div>
      </template>
    </template>

    <template v-else>
      <div v-if="loading" class="card empty-state"><span class="spinner" /> Cargando operación…</div>
      <template v-else-if="session.activeCompany && companyData">
        <section class="operations">
          <div class="operations__heading">
            <div>
              <p class="operations__eyebrow">Órdenes de trabajo</p>
              <h2>Resumen operativo</h2>
            </div>
            <RouterLink class="btn btn--primary" to="/work-orders/new">+ Nueva OT</RouterLink>
          </div>
          <div class="kpi-grid">
            <RouterLink class="kpi kpi--primary" to="/work-orders">
              <span class="kpi__label">Abiertas</span><strong>{{ companyData.summary.open }}</strong><small>OT activas</small>
            </RouterLink>
            <RouterLink class="kpi" to="/work-orders">
              <span class="kpi__label">Esperando aprobación</span><strong>{{ companyData.summary.awaiting_quote_approval }}</strong><small>Presupuestos</small>
            </RouterLink>
            <RouterLink class="kpi" to="/work-orders">
              <span class="kpi__label">En reparación</span><strong>{{ companyData.summary.repair }}</strong><small>En proceso</small>
            </RouterLink>
            <RouterLink class="kpi" to="/work-orders">
              <span class="kpi__label">Listas</span><strong>{{ companyData.summary.completed }}</strong><small>Para entregar</small>
            </RouterLink>
          </div>
          <div class="status-strip" v-if="companyData.statuses.length">
            <div class="status-strip__item" v-for="status in companyData.statuses" :key="status.id">
              <span class="status-dot" :style="{ backgroundColor: status.color }"></span>
              <span>{{ status.name }}</span><strong>{{ status.count }}</strong>
            </div>
          </div>
        </section>
      </template>
      <div class="card empty-state" v-else-if="!session.activeCompany">
        No hay empresa activa. Volvé al selector desde el topbar.
      </div>
    </template>
  
</template>
<style scoped>
.page-wrap { display:flex; flex-direction:column; gap:24px; }
.operations { display:flex; flex-direction:column; gap:18px; }
.operations__heading { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.operations__heading h2 { margin:3px 0 0; font-size:22px; }
.operations__eyebrow { margin:0; color:var(--text-muted,#94a3b8); font-size:12px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
.kpi-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }
.kpi { min-height:126px; padding:18px; border:1px solid var(--border,#263a57); border-radius:18px; background:var(--surface,#15243e); color:inherit; text-decoration:none; display:flex; flex-direction:column; justify-content:center; transition:transform .15s ease,border-color .15s ease; }
.kpi:hover { transform:translateY(-2px); border-color:#3b82f6; }
.kpi--primary { background:linear-gradient(145deg,rgba(37,99,235,.2),var(--surface,#15243e)); }
.kpi__label { color:var(--text-secondary,#aab7ca); font-size:13px; font-weight:650; }
.kpi strong { font-size:36px; line-height:1.1; margin:7px 0 3px; }
.kpi small { color:var(--text-muted,#8290a5); }
.status-strip { display:flex; flex-wrap:wrap; gap:9px; }
.status-strip__item { display:flex; align-items:center; gap:7px; padding:8px 11px; border:1px solid var(--border,#263a57); border-radius:999px; font-size:12px; }
.status-strip__item strong { margin-left:3px; }
.status-dot { width:8px; height:8px; border-radius:50%; flex:none; }
@media (max-width:760px) {
  .operations__heading { align-items:flex-end; }
  .operations__heading h2 { font-size:18px; }
  .kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
  .kpi { min-height:104px; padding:14px; border-radius:15px; }
  .kpi strong { font-size:30px; }
  .kpi__label { font-size:12px; }
  .status-strip { display:grid; grid-template-columns:1fr 1fr; }
  .status-strip__item { border-radius:12px; min-width:0; }
}
</style>
