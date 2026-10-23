<script setup lang="ts">
/**
 * Cierre mensual a marcas.
 *
 * Es la pantalla del fin de mes: que se le liquida a cada empresa (las marcas) por el
 * trabajo del periodo, y el registro de esos cierres.
 *
 * Dos cosas conviven acá y no hay que confundirlas:
 *
 * - El REPORTE es en vivo: se calcula sobre las ordenes de trabajo del periodo cada vez
 *   que se abre. Sirve para revisar antes de comprometer nada.
 * - Los REGISTROS son cierres ya emitidos: congelan el numero. Una vez emitido, el
 *   periodo no se vuelve a calcular; por eso emitir y liquidar son pasos separados y
 *   con su propio permiso.
 *
 * El importe liquidado es el COSTO de los trabajos, no la venta: en garantia de terceros
 * el legacy infla el precio de venta, asi que con la venta el numero no cierra.
 */
import { computed, onMounted, ref } from "vue";
import { apiGet, apiPost, getApiErrorMessage } from "../lib/api";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";
import Modal from "../components/Modal.vue";

interface Obra {
  work_order_id: number;
  number: number;
  legacy_number?: string | null;
  completed_at?: string | null;
  client_name?: string | null;
  work_area?: string | null;
  policy_code?: string | null;
  warranty_type: number;
  amount: string;
  equipment?: string | null;
  model?: string | null;
  serial_number?: string | null;
  technicians?: string[];
}

interface Empresa {
  billing_customer_id: number;
  billing_customer_name?: string | null;
  works_count: number;
  total_amount: string;
  warranty_works_count: number;
  warranty_amount: string;
  out_of_warranty_works_count: number;
  out_of_warranty_amount: string;
  own_warranty_works_count: number;
  own_warranty_amount: string;
  works: Obra[];
}

interface Totales {
  works_count: number;
  total_amount: string;
  warranty_works_count: number;
  warranty_amount: string;
  out_of_warranty_works_count: number;
  out_of_warranty_amount: string;
  own_warranty_works_count: number;
  own_warranty_amount: string;
}

interface Reporte {
  period: string;
  companies: Empresa[];
  totals: Totales;
}

interface Cierre {
  id: number;
  period: string;
  status: string;
  billing_customer_id: number;
  billing_customer_name?: string | null;
  works_count: number;
  total_amount: string;
  warranty_works_count: number;
  warranty_amount: string;
  out_of_warranty_works_count: number;
  out_of_warranty_amount: string;
  own_warranty_works_count: number;
  own_warranty_amount: string;
  invoice_number?: string | null;
  notes?: string | null;
  generated_at: string;
  issued_at?: string | null;
  settled_at?: string | null;
  works: Obra[];
}

const session = useSessionStore();
const toast = useToastStore();

const period = ref(periodoPorDefecto());
const reporte = ref<Reporte | null>(null);
const cierres = ref<Cierre[]>([]);
const cargando = ref(false);
const ocupada = ref(false);
const abierta = ref<number | null>(null);
const liquidando = ref<Cierre | null>(null);
const numeroFactura = ref("");

const puedeVer = computed(() => session.hasPermission("warranty_settlements.view"));
const puedeAdministrar = computed(() => session.hasPermission("warranty_settlements.manage"));

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

function periodoPorDefecto(): string {
  // El cierre es del mes que ya termino: el que se liquida a fin de mes es el anterior.
  const hoy = new Date();
  const mes = hoy.getMonth(); // 0 = enero
  const anio = hoy.getFullYear();
  if (mes === 0) return `${anio - 1}-12`;
  return `${anio}-${String(mes).padStart(2, "0")}`;
}

function etiquetaPeriodo(valor: string): string {
  const [anio, mes] = valor.split("-");
  const indice = Number(mes) - 1;
  if (!anio || Number.isNaN(indice) || !MESES[indice]) return valor;
  return `${MESES[indice]} ${anio}`;
}

const monto = new Intl.NumberFormat("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function dinero(valor: string | number | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  const numero = Number(valor);
  if (Number.isNaN(numero)) return "—";
  return monto.format(numero);
}

function fecha(valor?: string | null): string {
  if (!valor) return "—";
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("es-AR");
}

function estadoClase(estado: string): string {
  if (estado === "settled") return "badge--success";
  if (estado === "issued") return "badge--warning";
  if (estado === "cancelled") return "badge--muted";
  return "badge--muted";
}

function estadoTexto(estado: string): string {
  if (estado === "draft") return "Borrador";
  if (estado === "issued") return "Emitido";
  if (estado === "settled") return "Liquidado";
  if (estado === "cancelled") return "Anulado";
  return estado;
}

/** Como se llama a la garantia de este trabajo, para que el casillero se entienda. */
function garantiaTexto(tipo: number): string {
  if (tipo === 1) return "Garantía de terceros";
  if (tipo === 2) return "Garantía propia / de service";
  return "Fuera de garantía";
}

async function cargar() {
  if (!period.value) return;
  cargando.value = true;
  try {
    const [r, c] = await Promise.all([
      apiGet<Reporte>(`/warranty-settlements?period=${encodeURIComponent(period.value)}`),
      apiGet<{ items: Cierre[]; total: number }>(
        `/warranty-settlements/registros?period=${encodeURIComponent(period.value)}`
      ),
    ]);
    reporte.value = r;
    cierres.value = c.items;
  } catch (e) {
    toast.push(getApiErrorMessage(e), "error");
  } finally {
    cargando.value = false;
  }
}

async function generar() {
  ocupada.value = true;
  try {
    await apiPost("/warranty-settlements/generate", { period: period.value });
    toast.push(`Cierre de ${etiquetaPeriodo(period.value)} generado.`, "success");
    await cargar();
  } catch (e) {
    toast.push(getApiErrorMessage(e), "error");
  } finally {
    ocupada.value = false;
  }
}

async function emitir(cierre: Cierre) {
  ocupada.value = true;
  try {
    await apiPost(`/warranty-settlements/${cierre.id}/issue`);
    toast.push(`Cierre de ${cierre.billing_customer_name} emitido.`, "success");
    await cargar();
  } catch (e) {
    toast.push(getApiErrorMessage(e), "error");
  } finally {
    ocupada.value = false;
  }
}

function abrirLiquidacion(cierre: Cierre) {
  liquidando.value = cierre;
  numeroFactura.value = cierre.invoice_number ?? "";
}

async function liquidar() {
  if (!liquidando.value) return;
  ocupada.value = true;
  try {
    await apiPost(`/warranty-settlements/${liquidando.value.id}/settle`, {
      invoice_number: numeroFactura.value.trim() || null,
    });
    toast.push(`Cierre de ${liquidando.value.billing_customer_name} liquidado.`, "success");
    liquidando.value = null;
    await cargar();
  } catch (e) {
    toast.push(getApiErrorMessage(e), "error");
  } finally {
    ocupada.value = false;
  }
}

async function anular(cierre: Cierre) {
  ocupada.value = true;
  try {
    await apiPost(`/warranty-settlements/${cierre.id}/cancel`);
    toast.push(`Cierre de ${cierre.billing_customer_name} anulado.`, "success");
    await cargar();
  } catch (e) {
    toast.push(getApiErrorMessage(e), "error");
  } finally {
    ocupada.value = false;
  }
}

onMounted(() => {
  if (puedeVer.value) cargar();
});
</script>

<template>
  <section v-if="puedeVer" class="cierre">
    <header class="flex flex--between heading">
      <div>
        <h1>Cierre mensual a marcas</h1>
        <p class="text-secondary">
          Qué se le liquida a cada empresa por el trabajo del mes, y los cierres ya emitidos.
        </p>
      </div>
      <div class="toolbar">
        <label class="field field--inline">
          <span>Periodo</span>
          <input v-model="period" type="month" class="toolbar__search" @change="cargar" />
        </label>
        <button class="btn" type="button" :disabled="cargando" @click="cargar">
          {{ cargando ? "Calculando…" : "Ver" }}
        </button>
        <button
          v-if="puedeAdministrar"
          class="btn btn--primary"
          type="button"
          :disabled="ocupada || cargando"
          @click="generar"
        >
          Generar cierre
        </button>
      </div>
    </header>

    <div v-if="reporte" class="card-grid">
      <div class="card">
        <p class="card__title">Total a liquidar</p>
        <div class="card__value">{{ dinero(reporte.totals.total_amount) }}</div>
        <p class="card__hint">
          {{ reporte.totals.works_count }}
          {{ reporte.totals.works_count === 1 ? "trabajo" : "trabajos" }} ·
          {{ reporte.companies.length }}
          {{ reporte.companies.length === 1 ? "empresa" : "empresas" }}
        </p>
      </div>
      <div class="card">
        <p class="card__title">En garantía de terceros</p>
        <div class="card__value">{{ dinero(reporte.totals.warranty_amount) }}</div>
        <p class="card__hint">{{ reporte.totals.warranty_works_count }} trabajos</p>
      </div>
      <div class="card">
        <p class="card__title">Garantía propia / de service</p>
        <div class="card__value">{{ dinero(reporte.totals.own_warranty_amount) }}</div>
        <p class="card__hint">
          {{ reporte.totals.own_warranty_works_count }} trabajos · la hace el service oficial
        </p>
      </div>
      <div class="card">
        <p class="card__title">Fuera de garantía</p>
        <div class="card__value">{{ dinero(reporte.totals.out_of_warranty_amount) }}</div>
        <p class="card__hint">{{ reporte.totals.out_of_warranty_works_count }} trabajos</p>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <div>
          <h2 class="card__title">Cálculo por empresa</h2>
          <p class="text-secondary">
            {{ etiquetaPeriodo(period) }} · es un cálculo en vivo, todavía no está registrado.
            Tocá una empresa para ver los trabajos que la componen.
          </p>
        </div>
      </div>

      <table v-if="reporte && reporte.companies.length" class="table">
        <thead>
          <tr>
            <th>Empresa</th>
            <th class="num">Trabajos</th>
            <th class="num">Total</th>
            <th class="num">Garantía terceros</th>
            <th class="num">Garantía propia</th>
            <th class="num">Fuera de garantía</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="empresa in reporte.companies" :key="empresa.billing_customer_id">
            <tr
              class="fila-empresa"
              :class="{ 'is-open': abierta === empresa.billing_customer_id }"
              tabindex="0"
              @click="abierta = abierta === empresa.billing_customer_id ? null : empresa.billing_customer_id"
              @keydown.enter="abierta = abierta === empresa.billing_customer_id ? null : empresa.billing_customer_id"
            >
              <td>
                <span class="empresa-nombre">{{ empresa.billing_customer_name || "Sin nombre" }}</span>
                <span class="badge badge--muted" v-if="empresa.own_warranty_works_count">
                  service
                </span>
              </td>
              <td class="num">{{ empresa.works_count }}</td>
              <td class="num"><strong>{{ dinero(empresa.total_amount) }}</strong></td>
              <td class="num">
                {{ dinero(empresa.warranty_amount) }}
                <span class="text-muted">({{ empresa.warranty_works_count }})</span>
              </td>
              <td class="num">
                {{ dinero(empresa.own_warranty_amount) }}
                <span class="text-muted">({{ empresa.own_warranty_works_count }})</span>
              </td>
              <td class="num">
                {{ dinero(empresa.out_of_warranty_amount) }}
                <span class="text-muted">({{ empresa.out_of_warranty_works_count }})</span>
              </td>
            </tr>
            <tr v-if="abierta === empresa.billing_customer_id" :key="`detalle-${empresa.billing_customer_id}`">
              <td colspan="6" class="detalle">
                <table class="table tabla-detalle">
                  <thead>
                    <tr>
                      <th>OT</th>
                      <th>Legacy</th>
                      <th>Cliente</th>
                      <th>Equipo</th>
                      <th>Área</th>
                      <th>Garantía</th>
                      <th class="num">Costo</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="obra in empresa.works" :key="obra.work_order_id">
                      <td>#{{ obra.number }}</td>
                      <td class="text-muted">{{ obra.legacy_number || "—" }}</td>
                      <td>{{ obra.client_name || "—" }}</td>
                      <td>
                        {{ obra.equipment || "—" }}
                        <span v-if="obra.serial_number" class="text-muted">
                          · {{ obra.serial_number }}
                        </span>
                      </td>
                      <td class="text-muted">{{ obra.work_area || "—" }}</td>
                      <td>
                        <span
                          class="badge"
                          :class="obra.warranty_type === 1 ? 'badge--success' : obra.warranty_type === 2 ? 'badge--warning' : 'badge--muted'"
                        >
                          {{ garantiaTexto(obra.warranty_type) }}
                        </span>
                      </td>
                      <td class="num">{{ dinero(obra.amount) }}</td>
                    </tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <p v-else-if="!cargando" class="text-secondary">
        En {{ etiquetaPeriodo(period) }} no hay trabajos para liquidar.
      </p>
    </div>

    <div class="card">
      <div class="card-header">
        <div>
          <h2 class="card__title">Cierres registrados</h2>
          <p class="text-secondary">
            Un cierre emitido congela el número: el periodo ya no se recalcula.
          </p>
        </div>
      </div>

      <table v-if="cierres.length" class="table">
        <thead>
          <tr>
            <th>Empresa</th>
            <th>Periodo</th>
            <th>Estado</th>
            <th class="num">Trabajos</th>
            <th class="num">Total</th>
            <th>Factura</th>
            <th v-if="puedeAdministrar"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="cierre in cierres" :key="cierre.id">
            <td>{{ cierre.billing_customer_name || "Sin nombre" }}</td>
            <td>{{ etiquetaPeriodo(cierre.period) }}</td>
            <td><span class="badge" :class="estadoClase(cierre.status)">{{ estadoTexto(cierre.status) }}</span></td>
            <td class="num">{{ cierre.works_count }}</td>
            <td class="num"><strong>{{ dinero(cierre.total_amount) }}</strong></td>
            <td class="text-muted">{{ cierre.invoice_number || "—" }}</td>
            <td v-if="puedeAdministrar" class="acciones">
              <button
                v-if="cierre.status === 'draft'"
                class="btn btn--sm"
                type="button"
                :disabled="ocupada"
                @click="emitir(cierre)"
              >
                Emitir
              </button>
              <button
                v-if="cierre.status === 'issued'"
                class="btn btn--sm btn--primary"
                type="button"
                :disabled="ocupada"
                @click="abrirLiquidacion(cierre)"
              >
                Liquidar
              </button>
              <button
                v-if="cierre.status === 'draft' || cierre.status === 'issued'"
                class="btn btn--sm btn--danger"
                type="button"
                :disabled="ocupada"
                @click="anular(cierre)"
              >
                Anular
              </button>
              <span v-if="cierre.status === 'settled'" class="text-muted">
                liquidado {{ fecha(cierre.settled_at) }}
              </span>
              <span v-if="cierre.status === 'cancelled'" class="text-muted">anulado</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="text-secondary">
        Todavía no hay cierres registrados para {{ etiquetaPeriodo(period) }}.
      </p>
    </div>

    <Modal
      :open="liquidando !== null"
      :title="liquidando ? `Liquidar a ${liquidando.billing_customer_name}` : ''"
      @close="liquidando = null"
    >
      <div class="modal-cuerpo">
        <p class="text-secondary">
          Cierre por <strong>{{ dinero(liquidando?.total_amount) }}</strong> ·
          {{ liquidando?.works_count }} trabajos.
        </p>
        <div class="field">
          <label for="factura">Número de factura</label>
          <input id="factura" v-model="numeroFactura" type="text" placeholder="Opcional" maxlength="30" />
        </div>
      </div>
      <div class="modal__acciones">
        <button class="btn" type="button" @click="liquidando = null">Cancelar</button>
        <button class="btn btn--primary" type="button" :disabled="ocupada" @click="liquidar">
          Liquidar
        </button>
      </div>
    </Modal>
  </section>
</template>

<style scoped>
.heading {
  align-items: flex-start;
  gap: 16px;
}
.heading h1 {
  margin: 0 0 6px;
  font-size: 22px;
}
.heading p {
  margin: 0;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.card-header .card__title {
  margin-bottom: 6px;
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.field--inline {
  display: flex;
  align-items: center;
  gap: 8px;
}
.field--inline input {
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-primary);
}
.fila-empresa {
  cursor: pointer;
}
.fila-empresa.is-open {
  background: rgba(45, 124, 255, 0.06);
}
.empresa-nombre {
  font-weight: 600;
}
.detalle {
  background: var(--color-surface-elevated);
  padding: 0;
}
.tabla-detalle {
  border: none;
  border-radius: 0;
}
.tabla-detalle th,
.tabla-detalle td {
  padding: 9px 14px;
  font-size: 13px;
}
.acciones {
  text-align: right;
  white-space: nowrap;
}
.modal-cuerpo {
  padding: 4px 0 12px;
  display: grid;
  gap: 14px;
}
.modal__acciones {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
}
</style>
