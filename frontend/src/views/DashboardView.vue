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
interface RecentWorkOrder {
  id: number;
  number: number;
  customer_name: string;
  customer_phone: string | null;
  equipment_label: string;
  serial_number: string | null;
  status_name: string;
  status_color: string;
  received_at: string | null;
  expected_delivery_at: string | null;
}
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
  aging: { "0_2": number; "3_7": number; "8_15": number; "16_plus": number };
  trend: Array<{ label: string; received: number; finished: number }>;
  today: { date: string; received: number; completed: number; delivered: number };
  attention: Array<{
    key: string;
    count: number;
    status_ids?: number[];
    date_to?: string;
    open_only?: boolean;
  }>;
  avg_resolution_days: number | null;
  statuses: Array<{ id: number; name: string; color: string; count: number; is_final: boolean; marks_delivered: boolean }>;
  recent_work_orders: RecentWorkOrder[];
  can_create_work_orders: boolean;
}

const data = ref<SuperAdminDashboard | null>(null);
const companyData = ref<CompanyDashboard | null>(null);
const loading = ref(false);
const canCreateOrder = computed(() => companyData.value?.can_create_work_orders === true && session.hasPermission("work_orders.manage"));
const canViewOrders = computed(() => session.hasPermission("work_orders.view"));
function formatShortDate(value: string | null) {
  if (!value) return "—";
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + "Z");
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit" });
}
const maxStatus = computed(() => Math.max(1, ...(companyData.value?.statuses.map(s => s.count) ?? [1])));
const maxTrend = computed(() => Math.max(1, ...(companyData.value?.trend.flatMap(w => [w.received, w.finished]) ?? [1])));
const agingItems = computed(() => { const a=companyData.value?.aging; return a ? [{label:"0–2 días",value:a["0_2"]},{label:"3–7 días",value:a["3_7"]},{label:"8–15 días",value:a["8_15"]},{label:"+15 días",value:a["16_plus"]}] : []; });

// El backend manda la fecha ya expresada en el día de la empresa, así que se arma
// "dd/mm/aaaa" a mano: parsearla como Date la correría un día en los husos al este.
function formatDayLabel(iso: string) {
  const [y, m, d] = (iso || "").split("-");
  return y && m && d ? `${d}/${m}/${y}` : "";
}
// El backend resuelve qué cuenta en cada categoría y trae su destino; acá solo se decide
// cómo se nombra y a dónde apunta el link. La regla de estados no se reimplementa en el
// frontend, porque cada empresa tiene su propio flujo.
const ATTENTION_LABELS: Record<string, string> = {
  awaiting_quote_approval: "Presupuestos esperando respuesta",
  waiting_parts: "OT frenadas por repuesto",
  ready_to_deliver: "Listas para entregar",
  older_than_15_days: "Abiertas hace más de 15 días",
};
const attentionItems = computed(() =>
  (companyData.value?.attention ?? []).map((item) => ({
    ...item,
    label: ATTENTION_LABELS[item.key] ?? item.key,
    to: {
      path: "/app/work-orders",
      query: {
        ...(item.status_ids?.length ? { status_id: item.status_ids.map(String) } : {}),
        ...(item.date_to ? { date_to: item.date_to } : {}),
        ...(item.open_only ? { open_only: "true" } : {}),
      },
    },
  })),
);
const attentionTotal = computed(() => attentionItems.value.reduce((sum, item) => sum + item.count, 0));
const today = computed(() => companyData.value?.today ?? null);
const todayLabel = computed(() => (today.value ? formatDayLabel(today.value.date) : ""));
const todayItems = computed(() => {
  const t = today.value;
  if (!t) return [];
  return [
    { key: "received", label: "Ingresadas", value: t.received },
    { key: "completed", label: "Terminadas", value: t.completed },
    { key: "delivered", label: "Entregadas", value: t.delivered },
  ];
});

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
            <RouterLink v-if="canCreateOrder" class="btn btn--primary btn--desktop-only" :to="{ path: '/app/work-orders', query: { new: '1' } }">+ Nueva OT</RouterLink>
          </div>
          <div class="kpi-grid">
            <RouterLink class="kpi kpi--primary" to="/app/work-orders">
              <span class="kpi__label">Abiertas</span><strong>{{ companyData.summary.open }}</strong><small>OT activas</small>
            </RouterLink>
            <RouterLink class="kpi" to="/app/work-orders">
              <span class="kpi__label">Esperando aprobación</span><strong>{{ companyData.summary.awaiting_quote_approval }}</strong><small>Presupuestos</small>
            </RouterLink>
            <RouterLink class="kpi" to="/app/work-orders">
              <span class="kpi__label">En reparación</span><strong>{{ companyData.summary.repair }}</strong><small>En proceso</small>
            </RouterLink>
            <RouterLink class="kpi" to="/app/work-orders">
              <span class="kpi__label">Listas</span><strong>{{ companyData.summary.completed }}</strong><small>Para entregar</small>
            </RouterLink>
          </div>
          <section v-if="canViewOrders && attentionItems.length" class="attention-strip" aria-label="Requieren atención">
            <div class="attention-strip__head">
              <small>Requieren atención</small>
              <strong v-if="attentionTotal">{{ attentionTotal }} {{ attentionTotal === 1 ? "orden pendiente" : "órdenes pendientes" }}</strong>
            </div>
            <div v-if="attentionTotal" class="attention-strip__items">
              <RouterLink v-for="item in attentionItems" :key="item.key" class="attention-item" :to="item.to">
                <span class="attention-item__label">{{ item.label }}</span>
                <strong class="attention-item__count">{{ item.count }}</strong>
                <span class="attention-item__chevron" aria-hidden="true">›</span>
              </RouterLink>
            </div>
            <p v-else class="attention-strip__empty">Nada pendiente: no hay órdenes esperando una acción.</p>
          </section>
          <section v-if="canViewOrders && today" class="today-strip" aria-label="Actividad del día">
            <div class="today-strip__head">
              <small>Actividad de hoy</small>
              <strong>{{ todayLabel }}</strong>
            </div>
            <div class="today-strip__stats">
              <div v-for="item in todayItems" :key="item.key" class="today-stat" :class="'today-stat--' + item.key">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
          </section>
          <article v-if="canViewOrders" class="analytics-card recent-orders" aria-label="Últimas órdenes de trabajo">
            <div class="analytics-title">
              <div><small>Accesos directos</small><h3>Últimas órdenes de trabajo</h3></div>
              <div class="recent-orders__actions">
                <RouterLink class="btn btn--ghost btn--sm" to="/app/work-orders">Ver todas</RouterLink>
                <RouterLink v-if="canCreateOrder" class="btn btn--primary btn--sm btn--desktop-only" :to="{ path: '/app/work-orders', query: { new: '1' } }">+ Nueva OT</RouterLink>
              </div>
            </div>
            <div v-if="companyData.recent_work_orders.length" class="recent-list">
              <RouterLink
                v-for="order in companyData.recent_work_orders"
                :key="order.id"
                class="recent-item"
                :to="{ path: '/app/work-orders', query: { open: String(order.id) } }"
              >
                <span class="recent-item__number">#{{ order.number }}</span>
                <span class="recent-item__main">
                  <strong>{{ order.customer_name }}</strong>
                  <small>{{ order.equipment_label }}</small>
                </span>
                <span class="recent-item__meta">
                  <span class="status-pill" :style="{ background: order.status_color + '22', color: order.status_color, borderColor: order.status_color + '66' }">{{ order.status_name }}</span>
                  <small class="text-muted">{{ formatShortDate(order.received_at) }}</small>
                </span>
                <span class="recent-item__chevron" aria-hidden="true">›</span>
              </RouterLink>
            </div>
            <div v-else class="empty-state">Todavía no existen órdenes en esta empresa. Creá la primera con Nueva OT.</div>
          </article>
          <div class="analytics-grid">
            <article class="analytics-card analytics-card--wide">
              <div class="analytics-title"><div><small>Últimas 8 semanas</small><h3>Ingresadas vs terminadas</h3></div><strong v-if="companyData.avg_resolution_days !== null">{{ companyData.avg_resolution_days }} días <small>promedio</small></strong></div>
              <div class="trend-chart"><div class="trend-week" v-for="week in companyData.trend" :key="week.label"><div class="trend-bars"><i class="bar received" :style="{height:(week.received/maxTrend*100)+'%'}" :title="'Ingresadas: '+week.received"></i><i class="bar finished" :style="{height:(week.finished/maxTrend*100)+'%'}" :title="'Terminadas: '+week.finished"></i></div><span>{{ week.label }}</span></div></div>
              <div class="legend"><span><i class="dot received"></i>Ingresadas</span><span><i class="dot finished"></i>Terminadas</span></div>
            </article>
            <article class="analytics-card"><div class="analytics-title"><div><small>OT abiertas</small><h3>Antigüedad</h3></div></div><div class="metric-bars"><div v-for="item in agingItems" :key="item.label" class="metric-row"><span>{{ item.label }}</span><div><i :style="{width:(item.value/Math.max(1,companyData.summary.open)*100)+'%'}"></i></div><strong>{{ item.value }}</strong></div></div></article>
            <article class="analytics-card analytics-card--wide analytics-card--full"><div class="analytics-title"><div><small>Distribución actual</small><h3>OT por estado</h3></div></div><div class="metric-bars"><div v-for="status in companyData.statuses" :key="status.id" class="metric-row"><span>{{ status.name }}</span><div><i :style="{width:(status.count/maxStatus*100)+'%',backgroundColor:status.color}"></i></div><strong>{{ status.count }}</strong></div></div></article>

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
.recent-orders { margin-top:2px; }
.recent-orders__actions { display:flex; gap:8px; align-items:center; flex:none; }
.recent-list { display:flex; flex-direction:column; gap:8px; }
.recent-item { display:grid; grid-template-columns:auto 1fr auto 16px; gap:12px; align-items:center; padding:12px 14px; border:1px solid var(--border,#263a57); border-radius:14px; text-decoration:none; color:inherit; transition:border-color .15s ease,transform .15s ease; }
.recent-item:hover { border-color:#3b82f6; transform:translateY(-1px); }
.recent-item__number { font-weight:800; font-size:15px; white-space:nowrap; }
.recent-item__main { display:flex; flex-direction:column; gap:2px; min-width:0; }
.recent-item__main strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.recent-item__main small { color:var(--text-muted,#8290a5); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.recent-item__meta { display:flex; align-items:center; gap:10px; }
.recent-item__chevron { color:var(--text-muted,#8290a5); font-size:20px; }
.attention-strip{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:12px 18px;border:1px solid var(--border,#263a57);border-radius:16px;background:var(--surface,#15243e)}
.attention-strip__head{display:flex;flex-direction:column;gap:2px;flex:none}
.attention-strip__head small{color:var(--text-muted,#8290a5);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
.attention-strip__head strong{font-size:15px}
.attention-strip__items{display:flex;gap:10px;flex-wrap:wrap}
.attention-strip__empty{margin:0;font-size:13px;color:var(--text-muted,#8290a5)}
.attention-item{display:flex;align-items:center;gap:10px;padding:6px 10px 6px 12px;border:1px solid var(--border,#263a57);border-radius:99px;text-decoration:none;color:inherit;transition:border-color .15s ease,transform .15s ease}
.attention-item:hover{border-color:#f59e0b;transform:translateY(-1px)}
.attention-item__label{font-size:12px}
.attention-item__count{font-size:18px;color:#f59e0b}
.attention-item__chevron{color:var(--text-muted,#8290a5);font-size:18px;line-height:1}
/* La grilla analítica queda con tres tarjetas: la de distribución ocupa el ancho completo
   para no dejar un hueco en la columna angosta. */
.analytics-card--full{grid-column:1/-1}
.today-strip{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:12px 18px;border:1px solid var(--border,#263a57);border-radius:16px;background:var(--surface,#15243e)}
.today-strip__head{display:flex;flex-direction:column;gap:2px}
.today-strip__head small{color:var(--text-muted,#8290a5);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
.today-strip__head strong{font-size:15px}
.today-strip__stats{display:flex;gap:10px;flex-wrap:wrap}
.today-stat{display:flex;align-items:baseline;gap:8px;padding:6px 12px;border:1px solid var(--border,#263a57);border-radius:99px}
.today-stat span{font-size:12px;color:var(--text-muted,#8290a5)}
.today-stat strong{font-size:18px}
.today-stat--received strong{color:#3b82f6}
.today-stat--completed strong{color:#22c55e}
.today-stat--delivered strong{color:#8b5cf6}
.analytics-grid{display:grid;grid-template-columns:2fr 1fr;gap:14px}.analytics-card{border:1px solid var(--border,#263a57);border-radius:18px;background:var(--surface,#15243e);padding:18px;min-width:0}.analytics-title{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:16px}.analytics-title small{color:var(--text-muted,#8290a5);font-size:11px;text-transform:uppercase;letter-spacing:.08em}.analytics-title h3{margin:3px 0 0;font-size:16px}.analytics-title>strong{font-size:20px;white-space:nowrap}.analytics-title>strong small{display:block;text-align:right;text-transform:none;letter-spacing:0}.trend-chart{height:170px;display:flex;gap:8px;border-bottom:1px solid var(--border,#263a57)}.trend-week{flex:1;display:flex;flex-direction:column;justify-content:flex-end;min-width:0}.trend-bars{height:145px;display:flex;align-items:flex-end;justify-content:center;gap:3px}.bar{width:min(14px,40%);min-height:2px;border-radius:5px 5px 0 0;display:block}.received{background:#3b82f6}.finished{background:#22c55e}.trend-week>span{font-size:10px;color:var(--text-muted,#8290a5);text-align:center;height:20px;padding-top:5px}.legend{display:flex;gap:16px;margin-top:10px;font-size:11px;color:var(--text-muted,#8290a5)}.legend span{display:flex;align-items:center;gap:5px}.dot{width:7px;height:7px;border-radius:50%}.metric-bars{display:flex;flex-direction:column;gap:12px}.metric-row{display:grid;grid-template-columns:minmax(90px,140px) 1fr 28px;align-items:center;gap:10px;font-size:12px}.metric-row>div{height:8px;background:rgba(148,163,184,.12);border-radius:99px;overflow:hidden}.metric-row i{display:block;height:100%;background:#3b82f6;border-radius:99px}.metric-row strong{text-align:right}.attention-list{display:flex;flex-direction:column;gap:9px}.attention-list div{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--border,#263a57);font-size:12px}.attention-list div:last-child{border-bottom:0}.attention-list strong{font-size:16px}
@media (max-width:760px) {
  .operations__heading { align-items:flex-end; }
  .btn--desktop-only { display:none; }
  .recent-item { grid-template-columns:auto 1fr auto; }
  .recent-item__chevron { display:none; }
  .recent-item__meta { flex-direction:column; align-items:flex-end; gap:4px; }
  .analytics-grid{grid-template-columns:1fr}.analytics-card{padding:14px;border-radius:15px}.trend-chart{height:145px}.trend-bars{height:120px}.metric-row{grid-template-columns:90px 1fr 24px}
  .operations__heading h2 { font-size:18px; }
  .kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
  .kpi { min-height:104px; padding:14px; border-radius:15px; }
  .kpi strong { font-size:30px; }
  .kpi__label { font-size:12px; }
  .attention-strip { padding:12px 14px; border-radius:15px; gap:10px; }
  .attention-strip__items { width:100%; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
  .attention-item { justify-content:space-between; border-radius:12px; padding:10px 12px; }
  .today-strip { padding:12px 14px; border-radius:15px; gap:10px; }
  .today-strip__stats { width:100%; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }
  .today-stat { flex-direction:column; align-items:flex-start; gap:2px; border-radius:12px; padding:8px 10px; }
  .today-stat span { font-size:11px; }
  .status-strip { display:grid; grid-template-columns:1fr 1fr; }
  .status-strip__item { border-radius:12px; min-width:0; }
}
</style>
