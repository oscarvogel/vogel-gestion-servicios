<script setup lang="ts">
import { nextTick, onMounted, ref, computed } from "vue";
import { useReveal } from "../lib/motion";
import { useSessionStore } from "../stores/session";
import { apiGet } from "../lib/api";
import { useToastStore } from "../stores/toasts";
import { useRouter } from "vue-router";

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
const router = useRouter();
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
const root = ref<HTMLElement | null>(null);
const reveal = useReveal(root);
const canCreateOrder = computed(() => companyData.value?.can_create_work_orders === true && session.hasPermission("work_orders.manage"));
const canViewOrders = computed(() => session.hasPermission("work_orders.view"));
function formatShortDate(value: string | null) {
  if (!value) return "—";
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + "Z");
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit" });
}
// Las barras se escalan contra el tramo mas cargado, no contra el total.
const agingItems = computed(() => {
  const a = companyData.value?.aging;
  if (!a) return [];
  const items = [
    { label: "0 a 2 días", value: a["0_2"], dot: "var(--dot-green)" },
    { label: "3 a 7 días", value: a["3_7"], dot: "var(--dot-blue)" },
    { label: "8 a 15 días", value: a["8_15"], dot: "var(--dot-amber)" },
    { label: "16 días o más", value: a["16_plus"], dot: "var(--dot-red)" },
  ];
  const max = Math.max(1, ...items.map((i) => i.value));
  return items.map((i) => ({ ...i, pct: (i.value / max) * 100 }));
});
// El backend manda la fecha ya expresada en el día de la empresa: se arma como fecha local
// para que parsearla no la corra un día en los husos al este.
const todayLabel = computed(() => {
  const [y, m, d] = (companyData.value?.today.date || "").split("-").map(Number);
  if (!y || !m || !d) return "";
  const text = new Date(y, m - 1, d)
    .toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
    .replace(",", "");
  return text.charAt(0).toUpperCase() + text.slice(1);
});

// El backend resuelve qué cuenta en cada categoría y trae su destino; acá solo se decide
// cómo se nombra y a dónde apunta el link. La regla de estados no se reimplementa en el
// frontend, porque cada empresa tiene su propio flujo.
const ATTENTION: Record<string, { label: string; hint: string; dot: string }> = {
  awaiting_quote_approval: { label: "Esperando aprobación", hint: "Presupuesto enviado sin respuesta", dot: "var(--dot-amber)" },
  waiting_parts: { label: "Esperando repuestos", hint: "Detenidas por falta de repuesto", dot: "var(--dot-orange)" },
  ready_to_deliver: { label: "Listas para entregar", hint: "Completadas y todavía en el taller", dot: "var(--dot-green)" },
  older_than_15_days: { label: "Más de 15 días", hint: "Abiertas desde hace más de dos semanas", dot: "var(--dot-red)" },
};
const attentionItems = computed(() =>
  (companyData.value?.attention ?? []).map((item) => ({
    ...item,
    ...(ATTENTION[item.key] ?? { label: item.key, hint: "", dot: "var(--color-text-muted)" }),
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

const indicators = computed(() => {
  const c = companyData.value;
  if (!c) return [];
  const avg = c.avg_resolution_days;
  return [
    { label: "Abiertas", value: String(c.summary.open), count: c.summary.open, decimals: 0, unit: "órdenes" },
    { label: "Ingresadas hoy", value: String(c.today.received), count: c.today.received, decimals: 0, unit: "" },
    { label: "Terminadas hoy", value: String(c.today.completed), count: c.today.completed, decimals: 0, unit: "" },
    { label: "Entregadas hoy", value: String(c.today.delivered), count: c.today.delivered, decimals: 0, unit: "" },
    {
      label: "Resolución media",
      value: avg === null ? "—" : avg.toLocaleString("es-AR"),
      count: avg ?? undefined,
      decimals: avg !== null && !Number.isInteger(avg) ? 1 : 0,
      unit: avg === null ? "" : "días",
    },
  ];
});

// Eje Y de tres tramos con paso redondo (1, 2, 3… y de 5 en 5 desde ahí).
const trendAxis = computed(() => {
  const max = Math.max(1, ...(companyData.value?.trend.flatMap((w) => [w.received, w.finished]) ?? []));
  let step = Math.ceil(max / 3);
  if (step > 5) step = Math.ceil(step / 5) * 5;
  return { top: step * 3, ticks: [3, 2, 1, 0].map((i) => i * step) };
});
// "07/09" -> "7/9", como en el diseño.
const shortWeek = (label: string) => label.split("/").map((part) => String(Number(part))).join("/");

// Lo que sigue en el taller: los estados que marcan entrega ya no cuentan.
const distribution = computed(() => {
  const rows = (companyData.value?.statuses ?? []).filter((st) => !st.marks_delivered && st.count > 0);
  const total = rows.reduce((sum, st) => sum + st.count, 0);
  return { total, rows: rows.map((st) => ({ ...st, pct: total ? (st.count / total) * 100 : 0 })) };
});
const recentOrders = computed(() => companyData.value?.recent_work_orders.slice(0, 6) ?? []);
function openOrder(id: number) {
  router.push({ path: "/app/work-orders", query: { open: String(id) } });
}

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
    // Los numeros y las barras se animan recien cuando el contenido ya esta pintado.
    nextTick(reveal);
  }
}

onMounted(load);
</script>

<template>
<div ref="root" class="dash">
  <header class="dash-header">
    <div>
      <h1 class="dash-header__title">Dashboard</h1>
      <p class="dash-header__subtitle">
        {{ session.activeCompany ? todayLabel : "Empresas, usuarios y salud global de la plataforma." }}
      </p>
    </div>
    <RouterLink v-if="session.activeCompany && canCreateOrder" class="btn btn--primary btn--desktop-only" :to="{ path: '/app/work-orders', query: { new: '1' } }">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
      Nueva orden
    </RouterLink>
  </header>

  <template v-if="session.isSuperAdmin && !session.activeCompany">
    <div v-if="loading" class="card empty-state"><span class="spinner" /> Cargando métricas…</div>
    <template v-else-if="data">
      <div class="kpi-grid">
        <div class="kpi" data-rise>
          <span class="kpi__label"><i class="dot" style="--dot: var(--dot-blue)" />Empresas</span>
          <strong :data-count="data.kpis.total_companies">{{ data.kpis.total_companies }}</strong><small>{{ data.kpis.active_companies }} activas</small>
        </div>
        <div class="kpi" data-rise>
          <span class="kpi__label"><i class="dot" style="--dot: var(--dot-green)" />Usuarios</span>
          <strong :data-count="data.kpis.total_users">{{ data.kpis.total_users }}</strong><small>{{ data.kpis.active_users }} activos</small>
        </div>
        <div class="kpi" data-rise>
          <span class="kpi__label"><i class="dot" style="--dot: var(--dot-purple)" />Administradores</span>
          <strong :data-count="data.kpis.total_admins">{{ data.kpis.total_admins }}</strong><small>{{ data.kpis.total_superadmins }} superadmins</small>
        </div>
        <div class="kpi" data-rise>
          <span class="kpi__label"><i class="dot" style="--dot: var(--dot-amber)" />Empresas activas</span>
          <strong :data-count="data.kpis.active_companies">{{ data.kpis.active_companies }}</strong><small>disponibles para operar</small>
        </div>
      </div>

      <article class="panel" data-rise>
        <div class="panel__head"><h2>Empresas recientes</h2></div>
        <table class="dash-table">
          <thead><tr><th>Empresa</th><th>Slug</th><th>Estado</th><th>Creada</th></tr></thead>
          <tbody>
            <tr v-for="row in data.recent_companies" :key="row.id">
              <td><strong>{{ row.name }}</strong></td>
              <td><code>{{ row.slug }}</code></td>
              <td><span class="status-chip" :style="{ '--dot': row.active ? 'var(--dot-green)' : 'var(--color-text-muted)' }">{{ row.active ? "Activa" : "Inactiva" }}</span></td>
              <td class="text-secondary">{{ new Date(row.created_at).toLocaleString("es-AR") }}</td>
            </tr>
            <tr v-if="data.recent_companies.length === 0"><td colspan="4" class="empty-state">Aún no hay empresas creadas.</td></tr>
          </tbody>
        </table>
      </article>
    </template>
  </template>

  <template v-else>
    <div v-if="loading" class="card empty-state"><span class="spinner" /> Cargando operación…</div>
    <template v-else-if="session.activeCompany && companyData">
      <section v-if="canViewOrders" class="panel panel--padded" aria-label="Requieren atención" data-rise>
        <div class="attention__head">
          <h2>Requieren atención</h2>
          <p v-if="attentionTotal">{{ attentionTotal }} {{ attentionTotal === 1 ? "orden esperando" : "órdenes esperando" }} una acción. Tocá una para ver el listado.</p>
        </div>
        <div v-if="attentionTotal" class="attention__grid">
          <RouterLink v-for="item in attentionItems" :key="item.key" class="attention-card" :to="item.to" data-rise>
            <span class="kpi__label"><i class="dot" :style="{ '--dot': item.dot }" />{{ item.label }}
              <svg class="attention-card__chevron" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
            </span>
            <strong :data-count="item.count">{{ item.count }}</strong><small>{{ item.hint }}</small>
          </RouterLink>
        </div>
        <p v-else class="panel__hint">Nada pendiente: no hay órdenes esperando una acción.</p>
      </section>

      <div class="indicators">
        <div v-for="k in indicators" :key="k.label" class="kpi" data-rise>
          <span class="kpi__label">{{ k.label }}</span>
          <strong><span :data-count="k.count" :data-decimals="k.decimals">{{ k.value }}</span><small v-if="k.unit">{{ k.unit }}</small></strong>
        </div>
      </div>

      <div class="dash-grid">
        <article class="panel panel--padded" data-rise>
          <div class="panel__title-row">
            <div><p class="eyebrow">Últimas 8 semanas</p><h2>Ingresadas y terminadas por semana</h2></div>
            <div class="legend">
              <span><i style="background: var(--chart-received)" />Ingresadas</span>
              <span><i style="background: var(--dot-teal)" />Terminadas</span>
            </div>
          </div>
          <div class="trend">
            <div class="trend__plot">
              <div v-for="t in trendAxis.ticks" :key="t" class="trend__grid" :style="{ bottom: (t / trendAxis.top) * 100 + '%' }"><span>{{ t }}</span></div>
              <div class="trend__weeks">
                <div v-for="week in companyData.trend" :key="week.label" class="trend__week">
                  <i data-grow-y :style="{ height: (week.received / trendAxis.top) * 100 + '%', background: 'var(--chart-received)' }" :data-tip="`Ingresadas ${shortWeek(week.label)}: ${week.received}`" />
                  <i data-grow-y :style="{ height: (week.finished / trendAxis.top) * 100 + '%', background: 'var(--dot-teal)' }" :data-tip="`Terminadas ${shortWeek(week.label)}: ${week.finished}`" />
                </div>
              </div>
            </div>
            <div class="trend__labels"><span v-for="week in companyData.trend" :key="week.label">{{ shortWeek(week.label) }}</span></div>
          </div>
        </article>

        <article class="panel panel--padded" data-rise>
          <p class="eyebrow">Órdenes abiertas</p>
          <h2 class="panel__h2-gap">Antigüedad</h2>
          <div class="aging">
            <div v-for="item in agingItems" :key="item.label" class="aging__row">
              <div class="aging__label"><span>{{ item.label }}</span><strong :data-count="item.value">{{ item.value }}</strong></div>
              <div class="aging__track"><i data-grow-x :style="{ width: item.pct + '%', background: item.dot }" /></div>
            </div>
          </div>
        </article>
      </div>

      <div class="dash-grid dash-grid--bottom">
        <article class="panel panel--padded" data-rise>
          <p class="eyebrow">{{ distribution.total }} {{ distribution.total === 1 ? "abierta" : "abiertas" }}</p>
          <h2 class="panel__h2-gap">Dónde están las órdenes</h2>
          <template v-if="distribution.rows.length">
            <div class="stack" aria-hidden="true" data-grow-x>
              <i v-for="st in distribution.rows" :key="st.id" :style="{ flexGrow: st.count, background: st.color }" />
            </div>
            <ul class="distribution">
              <li v-for="st in distribution.rows" :key="st.id">
                <i class="dot" :style="{ '--dot': st.color }" />
                <span>{{ st.name }}</span>
                <small>{{ Math.round(st.pct) }}%</small>
                <strong :data-count="st.count">{{ st.count }}</strong>
              </li>
            </ul>
          </template>
          <p v-else class="panel__hint">No hay órdenes en el taller.</p>
        </article>

        <article v-if="canViewOrders" class="panel" aria-label="Últimas órdenes" data-rise>
          <div class="panel__head">
            <h2>Últimas órdenes</h2>
            <RouterLink to="/app/work-orders">Ver todas</RouterLink>
          </div>
          <table v-if="recentOrders.length" class="dash-table">
            <tbody>
              <tr v-for="order in recentOrders" :key="order.id" @click="openOrder(order.id)">
                <td data-label="OT">
                  <RouterLink class="ot-code" :to="{ path: '/app/work-orders', query: { open: String(order.id) } }" @click.stop>{{ order.number }}</RouterLink>
                </td>
                <td data-label="Cliente y equipo" class="dash-table__main">
                  <strong>{{ order.customer_name }}</strong>
                  <small>{{ order.equipment_label }}</small>
                </td>
                <td data-label="Estado"><span class="status-chip" :style="{ '--dot': order.status_color }">{{ order.status_name }}</span></td>
                <td data-label="Entrega" class="dash-table__end text-secondary">Entrega {{ formatShortDate(order.expected_delivery_at) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">Todavía no existen órdenes en esta empresa. Creá la primera con Nueva orden.</div>
        </article>
      </div>
    </template>
    <div class="card empty-state" v-else-if="!session.activeCompany">
      No hay empresa activa. Volvé al selector desde el topbar.
    </div>
  </template>
</div>
</template>

<style scoped>
.dash { display:flex; flex-direction:column; gap:inherit; min-width:0; }
.dash-header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.dash-header__title { margin:0; font-size:28px; font-weight:700; letter-spacing:-0.01em; }
.dash-header__subtitle { margin:4px 0 0; font-size:15px; color:var(--color-text-secondary); }
.kpi-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; }
.kpi { display:flex; flex-direction:column; padding:20px; border:1px solid var(--color-border); border-radius:var(--radius-lg); background:var(--color-surface); color:inherit; text-decoration:none; transition:border-color .15s ease; }
a.kpi:hover { border-color:var(--color-border-strong); }
.kpi__label { display:flex; align-items:center; gap:8px; font-size:14px; color:var(--color-text-secondary); }
.kpi strong { font-size:36px; font-weight:700; line-height:1.15; margin:6px 0 8px; color:var(--color-text-primary); }
.kpi small { font-size:13px; color:var(--color-text-muted); }
.dash-grid { display:grid; grid-template-columns:minmax(0,2.2fr) minmax(260px,1fr); gap:18px; align-items:stretch; }
.dash-grid--bottom { grid-template-columns:minmax(280px,1fr) minmax(0,1.85fr); align-items:start; }
.panel { border:1px solid var(--color-border); border-radius:var(--radius-lg); background:var(--color-surface); min-width:0; overflow:hidden; }
.panel--padded { padding:20px; }
.panel h2 { margin:0; font-size:16px; font-weight:600; }
.panel__head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:20px; border-bottom:1px solid var(--color-border); }
.panel__head a { font-size:14px; font-weight:500; }
.panel__hint { margin:4px 0 18px; font-size:13px; color:var(--color-text-secondary); }
.dash-table { width:100%; border-collapse:collapse; }
.dash-table th { padding:14px 20px; text-align:left; font-size:11px; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--color-text-muted); border-bottom:1px solid var(--color-border); }
.dash-table td { padding:14px 20px; font-size:14px; border-bottom:1px solid var(--color-border); white-space:nowrap; }
.dash-table tbody tr:last-child td { border-bottom:0; }
.dash-table tbody tr { cursor:pointer; }
.dash-table tbody tr:hover { background:var(--color-surface-hover); }
.dash-table__main { display:flex; flex-direction:column; gap:1px; white-space:normal; }
.dash-table__main strong { font-weight:600; }
.dash-table__main small { font-size:14px; color:var(--color-text-secondary); }
.eyebrow { margin:0 0 4px; font-size:11px; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--color-text-muted); }
.panel__h2-gap { margin-bottom:18px !important; }
.panel__title-row { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:20px; }
.attention__head { display:flex; justify-content:space-between; align-items:baseline; gap:16px; flex-wrap:wrap; margin-bottom:18px; }
.attention__head p { margin:0; font-size:14px; color:var(--color-text-secondary); }
.attention__grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }
.attention-card { display:flex; flex-direction:column; padding:18px 18px 16px; border:1px solid var(--color-border); border-radius:var(--radius-lg); background:var(--color-bg); color:inherit; text-decoration:none; transition:border-color .15s ease; }
.attention-card:hover { border-color:var(--color-border-strong); }
.attention-card__chevron { margin-left:auto; color:var(--color-text-muted); flex:none; }
.attention-card strong { font-size:36px; font-weight:700; line-height:1.15; margin:6px 0 8px; }
.attention-card small { font-size:13px; color:var(--color-text-secondary); }
.indicators { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:16px; }
.indicators .kpi strong { display:flex; align-items:baseline; gap:8px; margin-bottom:0; }
.indicators .kpi strong small { font-size:15px; font-weight:400; color:var(--color-text-secondary); }
.legend { display:flex; gap:18px; font-size:14px; color:var(--color-text-secondary); white-space:nowrap; }
.legend span { display:flex; align-items:center; gap:8px; }
.legend i { width:12px; height:12px; border-radius:3px; }
.trend { padding-left:28px; }
.trend__plot { position:relative; height:240px; }
.trend__grid { position:absolute; left:0; right:0; border-top:1px solid var(--color-border); }
.trend__grid span { position:absolute; left:-28px; top:-8px; font-size:11px; color:var(--color-text-muted); }
.trend__weeks { position:absolute; inset:0; display:flex; }
.trend__week { flex:1; display:flex; align-items:flex-end; justify-content:center; gap:6px; }
.trend__week i { position:relative; width:min(28px,28%); min-height:2px; border-radius:4px 4px 0 0; cursor:default; transition:filter .15s ease; }
/* El filtro crea su propio contexto de apilado: sin z-index, las barras vecinas tapan el globo. */
.trend__week i:hover { filter:brightness(1.2); z-index:5; }
/* Globo con el valor de la barra al pasar el mouse. */
.trend__week i:hover::after { content:attr(data-tip); position:absolute; bottom:calc(100% + 8px); left:50%; transform:translateX(-50%); z-index:2; padding:6px 10px; border:1px solid var(--color-border-strong); border-radius:var(--radius-sm); background:var(--color-chip); color:var(--color-text-primary); font-size:12px; font-weight:600; white-space:nowrap; pointer-events:none; }
.trend__labels { display:flex; margin-top:8px; }
.trend__labels span { flex:1; text-align:center; font-size:12px; color:var(--color-text-secondary); }
.stack { display:flex; gap:2px; height:12px; border-radius:99px; overflow:hidden; margin-bottom:8px; }
.stack i { display:block; min-width:4px; }
.distribution { list-style:none; margin:0; padding:0; }
.distribution li { display:grid; grid-template-columns:auto 1fr auto 32px; align-items:center; gap:12px; padding:14px 4px; border-top:1px solid var(--color-border); font-size:14px; }
.distribution small { font-size:13px; color:var(--color-text-secondary); }
.distribution strong { text-align:right; }
.dash-table__end { text-align:right; }
.aging { display:flex; flex-direction:column; gap:16px; }
.aging__label { display:flex; justify-content:space-between; font-size:14px; margin-bottom:8px; }
.aging__label span { color:var(--color-text-secondary); }
.aging__track { height:8px; border-radius:99px; background:var(--color-chip); overflow:hidden; }
.aging__track i { display:block; height:100%; border-radius:99px; }
@media (max-width:1100px) { .dash-grid, .dash-grid--bottom { grid-template-columns:1fr; } .indicators { grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media (max-width:760px) {
  .btn--desktop-only { display:none; }
  .dash-header__title { font-size:22px; }
  .kpi-grid, .indicators, .attention__grid { grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
  .attention-card { padding:14px; }
  .attention-card strong { font-size:28px; }
  .panel__title-row { flex-direction:column; }
  .trend__plot { height:180px; }
  .trend__week { gap:3px; }
  .kpi { padding:14px; }
  .kpi strong { font-size:28px; }
  .dash-table thead { display:none; }
  .dash-table, .dash-table tbody, .dash-table tr, .dash-table td { display:block; }
  .dash-table tr { display:grid; grid-template-columns:auto 1fr; gap:4px 12px; padding:12px 16px; border-bottom:1px solid var(--color-border); }
  .dash-table td { padding:0; border:0; }
  .dash-table td[data-label="Estado"] { grid-column:2; }
  .dash-table td[data-label="Recibida"], .dash-table td[data-label="Entrega"] { display:none; }
}
</style>
