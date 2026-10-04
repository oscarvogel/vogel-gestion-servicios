<script setup lang="ts">
/**
 * Consumo del adicional de IA (#44, sub-issue 8).
 *
 * Dos audiencias en una sola pantalla, y una regla dura: **una empresa solo ve lo suyo**.
 *
 * - Con empresa activa, cualquiera con `ai.use` ve su mes: cuanto gastó, cuanto le queda de
 *   cuota, el desglose por operacion y el historial.
 * - Si ademas sos superadmin, arriba del todo aparece el listado de **todas** las empresas,
 *   que es lo que sirve para decidir a quien se le renueva.
 *
 * El backend de la lista es superadmin, asi que la seccion se oculta si el GET da 403 en vez
 * de romper la pantalla: un superadmin sin empresa activa no tiene "su" mes, y eso esta bien.
 *
 * **El costo es estimado.** Sale de la tabla de precios de la plataforma, no de la factura de
 * la proveedor, y la pantalla lo dice en vez de dejar que el numero se lea como un total a
 * cobrar. Para facturar hay que cruzarlo con la factura del proveedor.
 */
import { computed, onMounted, ref } from "vue";
import { apiGet, getApiErrorMessage } from "../lib/api";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();

interface MesEnCurso {
  period_start: string;
  requests: number;
  registros: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  monthly_quota_usd: number;
  monthly_request_limit: number;
  cuota_restante_usd: number | null;
  pedidos_restantes: number | null;
  agotada: boolean;
}
interface Operacion {
  operation: string;
  requests: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}
interface Historial {
  period_start: string;
  requests: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}
interface MiConsumo {
  mes_en_curso: MesEnCurso;
  por_operacion: Operacion[];
  historial: Historial[];
  costo_es_estimado: boolean;
}
interface FilaEmpresa {
  company_id: number;
  company_name: string;
  company_active: boolean;
  enabled: boolean;
  monthly_quota_usd: number;
  monthly_request_limit: number;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  previous_month_cost_usd: number;
  agotada: boolean;
}

const miConsumo = ref<MiConsumo | null>(null);
const empresas = ref<FilaEmpresa[]>([]);
const verEmpresas = ref(false);
const cargando = ref(false);
const error = ref("");

const hayEmpresa = computed(() => session.activeCompany !== null);
const esPlataforma = computed(() => session.isSuperAdmin);

function usd(valor: number, decimales = 4): string {
  return `$${valor.toLocaleString("es-AR", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  })}`;
}

function numero(valor: number): string {
  return valor.toLocaleString("es-AR");
}

function mes(fecha: string): string {
  const d = new Date(fecha);
  if (Number.isNaN(d.getTime())) return fecha;
  return d.toLocaleDateString("es-AR", { month: "short", year: "2-digit" });
}

/** "sin tope" y "agotado" son cosas distintas y hay que poder distinguishedas de un vistazo. */
function tope(cuota: number, limite: number): string {
  const partes: string[] = [];
  partes.push(cuota > 0 ? `${usd(cuota, 2)} / mes` : "sin tope de gasto");
  if (limite > 0) partes.push(`${numero(limite)} pedidos / mes`);
  return partes.join(" · ");
}

const totalEmpresa = computed(() =>
  empresas.value.reduce((suma, f) => suma + f.cost_usd, 0),
);
const sinHabilitarConUso = computed(() =>
  empresas.value.filter((f) => !f.enabled && f.requests > 0),
);

const consumoMaximo = computed(() =>
  Math.max(0.000001, ...empresas.value.map((f) => f.cost_usd)),
);

async function cargar() {
  cargando.value = true;
  error.value = "";
  try {
    // La parte de la empresa solo tiene sentido con empresa activa: en modo plataforma el
    // superadmin no pertenece a ninguna, y su "consumo propio" seria el de nadie.
    if (hayEmpresa.value && session.hasPermission("ai.use")) {
      try {
        miConsumo.value = await apiGet<MiConsumo>("/ai/consumo?meses=6");
      } catch (e) {
        miConsumo.value = null;
        error.value = getApiErrorMessage(e);
      }
    } else {
      miConsumo.value = null;
    }
    if (esPlataforma.value) {
      try {
        empresas.value = await apiGet<FilaEmpresa[]>("/companies/ai-consumo");
        verEmpresas.value = true;
      } catch {
        // 403: no es superadmin en esta sesion. No es un error que haya que mostrar.
        empresas.value = [];
        verEmpresas.value = false;
      }
    }
  } finally {
    cargando.value = false;
  }
}

onMounted(cargar);
</script>

<template>
  <div class="page-stack">
    <div class="card">
      <h2>Consumo de IA</h2>
      <p class="text-secondary">
        <template v-if="hayEmpresa">Cuánto consumió {{ session.activeCompany?.name }} este mes.</template>
        <template v-else>No tenés empresa activa: elegí una para ver tu consumo.</template>
      </p>
      <p class="text-muted estimate-note">
        Los importes son <strong>estimados</strong> con la tabla de precios de la plataforma, no la
        factura del proveedor. Sirven para medir el adicional; para cobrar hay que cruzarlos con
        la factura.
      </p>
    </div>

    <div v-if="cargando" class="card text-muted">Cargando consumo…</div>
    <div v-else-if="error && !miConsumo" class="card empty-state">{{ error }}</div>

    <!-- Todas las empresas: lo que la plataforma usa para decidir a quién se renueva. -->
    <section v-if="verEmpresas" class="card">
      <header class="section-head">
        <h3>Todas las empresas</h3>
        <span class="text-muted">{{ usd(totalEmpresa) }} estimados este mes</span>
      </header>

      <p v-if="sinHabilitarConUso.length" class="warn-strip">
        <strong>{{ sinHabilitarConUso.length }}</strong>
        {{ sinHabilitarConUso.length === 1 ? "empresa tiene" : "empresas tienen" }}
        consumo con la IA apagada: o se quedó el interruptor después de un mes de uso, o está
        pagando sin estar contratada.
      </p>

      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>Empresa</th>
              <th>Estado</th>
              <th class="num">Pedidos</th>
              <th class="num">Tokens</th>
              <th class="num">Este mes</th>
              <th class="num">Mes anterior</th>
              <th>Techo</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in empresas" :key="f.company_id" :class="{ 'is-off': !f.company_active }">
              <td>
                {{ f.company_name }}
                <span v-if="!f.company_active" class="pill pill--muted">inactiva</span>
              </td>
              <td>
                <span v-if="f.enabled" class="pill pill--ok">vendida</span>
                <span v-else class="pill pill--muted">no vendida</span>
                <span v-if="f.agotada" class="pill pill--warn">agotada</span>
              </td>
              <td class="num">{{ numero(f.requests) }}</td>
              <td class="num">{{ numero(f.input_tokens + f.output_tokens) }}</td>
              <td class="num">
                <!-- La barra es proporcional a la empresa que mas gasto del mes: sirve para
                     ver de un golpe cuales se van del rango, sin tener que leer los numeros. -->
                <div class="cost-cell">
                  <span class="bar" :style="{ width: `${(f.cost_usd / consumoMaximo) * 100}%` }"></span>
                  <span>{{ usd(f.cost_usd) }}</span>
                </div>
              </td>
              <td class="num">{{ usd(f.previous_month_cost_usd) }}</td>
              <td class="text-muted">{{ tope(f.monthly_quota_usd, f.monthly_request_limit) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- La empresa y su propio mes. -->
    <template v-if="miConsumo">
      <div class="grid-3">
        <div class="card metric">
          <span class="metric__label">Gastado este mes</span>
          <strong class="metric__value">{{ usd(miConsumo.mes_en_curso.cost_usd) }}</strong>
          <span class="text-muted">de {{ tope(miConsumo.mes_en_curso.monthly_quota_usd, 0) }}</span>
        </div>
        <div class="card metric">
          <span class="metric__label">Te queda</span>
          <strong class="metric__value" :class="{ 'is-zero': miConsumo.mes_en_curso.cuota_restante_usd === 0 }">
            {{ miConsumo.mes_en_curso.cuota_restante_usd === null ? "sin tope" : usd(miConsumo.mes_en_curso.cuota_restante_usd) }}
          </strong>
          <span class="text-muted">
            <template v-if="miConsumo.mes_en_curso.pedidos_restantes !== null">
              {{ numero(miConsumo.mes_en_curso.pedidos_restantes) }} pedidos disponibles
            </template>
            <template v-else>sin tope de pedidos</template>
          </span>
        </div>
        <div class="card metric">
          <span class="metric__label">Pedidos</span>
          <strong class="metric__value">{{ numero(miConsumo.mes_en_curso.requests) }}</strong>
          <span class="text-muted">
            {{ numero(miConsumo.mes_en_curso.input_tokens + miConsumo.mes_en_curso.output_tokens) }} tokens
          </span>
        </div>
      </div>

      <div v-if="miConsumo.mes_en_curso.agotada" class="card warn-strip">
        <p>
          Llegaste al techo de este mes: la IA deja de responder hasta que se renueve o pase el
          mes.
        </p>
        <p class="text-muted">
          <template v-if="miConsumo.mes_en_curso.monthly_quota_usd > 0">
            Gastaste {{ usd(miConsumo.mes_en_curso.cost_usd) }} de
            {{ usd(miConsumo.mes_en_curso.monthly_quota_usd, 2) }} de cuota.
          </template>
          <template v-if="miConsumo.mes_en_curso.monthly_request_limit > 0">
            Y hiciste {{ numero(miConsumo.mes_en_curso.requests) }} de
            {{ numero(miConsumo.mes_en_curso.monthly_request_limit) }} pedidos.
          </template>
        </p>
      </div>

      <section v-if="miConsumo.por_operacion.length" class="card">
        <h3>En qué se fue</h3>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>Operación</th>
                <th class="num">Pedidos</th>
                <th class="num">Tokens de entrada</th>
                <th class="num">Tokens de salida</th>
                <th class="num">Costo estimado</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="o in miConsumo.por_operacion" :key="o.operation">
                <td>{{ o.operation }}</td>
                <td class="num">{{ numero(o.requests) }}</td>
                <td class="num">{{ numero(o.input_tokens) }}</td>
                <td class="num">{{ numero(o.output_tokens) }}</td>
                <td class="num">{{ usd(o.cost_usd) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="miConsumo.historial.length" class="card">
        <h3>Historial</h3>
        <p class="text-muted">
          Los meses sin consumo también aparecen, en cero. Los pedidos que fallaron cuentan
          para la cuota: si el proveedor se cae, el costo existe igual.
        </p>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>Mes</th>
                <th class="num">Pedidos</th>
                <th class="num">Tokens</th>
                <th class="num">Costo estimado</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="h in miConsumo.historial" :key="h.period_start">
                <td>{{ mes(h.period_start) }}</td>
                <td class="num">{{ numero(h.requests) }}</td>
                <td class="num">{{ numero(h.input_tokens + h.output_tokens) }}</td>
                <td class="num">{{ usd(h.cost_usd) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page-stack { display: flex; flex-direction: column; gap: 18px; }
h2, h3 { margin: 0 0 6px; }
.estimate-note {
  margin: 10px 0 0;
  padding: 8px 10px;
  border-left: 3px solid var(--color-text-muted, #8290a5);
  font-size: 13px;
}
.section-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.metric { display: flex; flex-direction: column; gap: 4px; }
.metric__label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted, #8290a5); }
.metric__value { font-size: 22px; font-variant-numeric: tabular-nums; }
.metric__value.is-zero { color: #ef4444; }
.table-scroll { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th, .data-table td { padding: 8px 8px; text-align: left; border-bottom: 1px solid var(--border, #263a57); }
.data-table th { font-size: 12px; font-weight: 500; color: var(--text-muted, #8290a5); }
.data-table .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.data-table tr.is-off { opacity: 0.6; }
.cost-cell { position: relative; display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.cost-cell .bar { position: absolute; right: 0; top: 50%; transform: translateY(-50%); height: 18px; border-radius: 4px; background: rgba(59, 130, 246, 0.22); }
.cost-cell span:last-child { position: relative; }
.pill { display: inline-block; margin-right: 5px; padding: 1px 7px; border-radius: 999px; font-size: 11px; }
.pill--ok { background: rgba(34, 197, 94, 0.16); color: #22c55e; }
.pill--warn { background: rgba(251, 191, 36, 0.16); color: #fbbf24; }
.pill--muted { background: rgba(130, 144, 165, 0.18); color: var(--text-muted, #8290a5); }
.warn-strip { font-size: 13px; }
.warn-strip button { margin-left: 8px; }
@media (max-width: 900px) { .grid-3 { grid-template-columns: 1fr; } }
</style>
