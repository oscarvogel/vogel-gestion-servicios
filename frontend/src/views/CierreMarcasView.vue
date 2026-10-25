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
import { computed, nextTick, onMounted, ref } from "vue";
import { useReveal } from "../lib/motion";
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
const root = ref<HTMLElement | null>(null);
const reveal = useReveal(root);
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
  return `${MESES[indice]} de ${anio}`;
}

function moverPeriodo(delta: number) {
  const [anio, mes] = period.value.split("-").map(Number);
  const d = new Date(anio, mes - 1 + delta, 1);
  period.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  abierta.value = null;
  cargar();
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

function porcentaje(parte: string, total: string): string {
  const t = Number(total);
  if (!t) return "0 %";
  return `${((Number(parte) / t) * 100).toLocaleString("es-AR", { maximumFractionDigits: 1 })} %`;
}

const ESTADOS: Record<string, { texto: string; dot: string }> = {
  draft: { texto: "Borrador", dot: "var(--color-text-muted)" },
  issued: { texto: "Emitido", dot: "var(--dot-amber)" },
  settled: { texto: "Liquidado", dot: "var(--dot-green)" },
  cancelled: { texto: "Anulado", dot: "var(--dot-red)" },
};

/** Como se llama a la garantia de este trabajo, para que el casillero se entienda. */
function garantiaTexto(tipo: number): string {
  if (tipo === 1) return "Garantía de terceros";
  if (tipo === 2) return "Garantía propia o de service";
  return "Fuera de garantía";
}

// Una fila por empresa: el calculo en vivo y, si ya hay, su cierre registrado. Un cierre
// vigente congela el numero, asi que manda sobre el calculo; uno anulado solo se usa si no
// hay otro, para que la empresa no desaparezca de la lista.
const filas = computed(() => {
  const porEmpresa = new Map<number, Cierre>();
  for (const c of cierres.value) {
    const previo = porEmpresa.get(c.billing_customer_id);
    if (!previo || (previo.status === "cancelled" && c.status !== "cancelled")) porEmpresa.set(c.billing_customer_id, c);
  }
  const ids = new Set<number>([
    ...(reporte.value?.companies ?? []).map((e) => e.billing_customer_id),
    ...porEmpresa.keys(),
  ]);
  return [...ids].map((id) => {
    const empresa = reporte.value?.companies.find((e) => e.billing_customer_id === id);
    const cierre = porEmpresa.get(id) ?? null;
    const datos: Empresa = cierre && cierre.status !== "cancelled" ? cierre : (empresa ?? cierre!);
    return { id, cierre, datos };
  });
});

const filtro = ref<string>("all");
const filtros = computed(() => [
  { key: "all", texto: "Todos", dot: "var(--color-link)", total: filas.value.length },
  ...Object.entries(ESTADOS).map(([key, e]) => ({
    key,
    texto: e.texto,
    dot: e.dot,
    total: filas.value.filter((f) => f.cierre?.status === key).length,
  })),
]);
const filasVisibles = computed(() =>
  filtro.value === "all" ? filas.value : filas.value.filter((f) => f.cierre?.status === filtro.value),
);

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
    nextTick(reveal);
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

async function generarEmpresa(id: number, nombre?: string | null, regenerando = false) {
  ocupada.value = true;
  try {
    await apiPost(`/warranty-settlements/generate/${id}`, { period: period.value });
    toast.push(`Cierre de ${nombre || "la empresa"} ${regenerando ? "regenerado" : "generado"}.`, "success");
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
  <section v-if="puedeVer" ref="root" class="cierre">
    <header class="heading">
      <div>
        <h1>Cierre mensual a marcas</h1>
        <p>Lo que se le liquida a cada empresa por el trabajo del mes. Se liquida el costo de los trabajos, no la venta.</p>
      </div>
      <div class="heading__actions">
        <div class="periodo" role="group" aria-label="Período">
          <button class="periodo__flecha" type="button" aria-label="Mes anterior" :disabled="cargando" @click="moverPeriodo(-1)">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 6-6 6 6 6" /></svg>
          </button>
          <span class="periodo__mes" aria-live="polite">{{ cargando ? "Calculando…" : etiquetaPeriodo(period) }}</span>
          <button class="periodo__flecha" type="button" aria-label="Mes siguiente" :disabled="cargando" @click="moverPeriodo(1)">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
          </button>
        </div>
        <button v-if="puedeAdministrar" class="btn btn--primary" type="button" :disabled="ocupada || cargando" @click="generar">
          Generar cierre
        </button>
      </div>
    </header>

    <article v-if="reporte" class="panel panel--padded" data-rise>
      <div class="resumen__head">
        <div>
          <p class="resumen__label">Total a liquidar</p>
          <div class="resumen__total" :data-count="Number(reporte.totals.total_amount)" data-decimals="2" data-prefix="$ ">$ {{ dinero(reporte.totals.total_amount) }}</div>
        </div>
        <p class="resumen__meta">
          {{ reporte.totals.works_count }} {{ reporte.totals.works_count === 1 ? "trabajo" : "trabajos" }} ·
          {{ reporte.companies.length }} {{ reporte.companies.length === 1 ? "empresa" : "empresas" }} ·
          cálculo en vivo, todavía sin registrar
        </p>
      </div>
      <div class="resumen__barra" aria-hidden="true" data-grow-x>
        <i :style="{ flexGrow: Number(reporte.totals.warranty_amount), background: 'var(--dot-blue)' }" />
        <i :style="{ flexGrow: Number(reporte.totals.own_warranty_amount), background: 'var(--dot-teal)' }" />
        <i :style="{ flexGrow: Number(reporte.totals.out_of_warranty_amount), background: 'var(--dot-amber)' }" />
      </div>
      <div class="resumen__partes">
        <div>
          <span class="resumen__parte"><i style="background: var(--dot-blue)" />En garantía de terceros</span>
          <strong :data-count="Number(reporte.totals.warranty_amount)" data-decimals="2" data-prefix="$ ">$ {{ dinero(reporte.totals.warranty_amount) }}</strong>
          <small>{{ reporte.totals.warranty_works_count }} trabajos · {{ porcentaje(reporte.totals.warranty_amount, reporte.totals.total_amount) }}</small>
        </div>
        <div>
          <span class="resumen__parte"><i style="background: var(--dot-teal)" />Garantía propia o de service</span>
          <strong :data-count="Number(reporte.totals.own_warranty_amount)" data-decimals="2" data-prefix="$ ">$ {{ dinero(reporte.totals.own_warranty_amount) }}</strong>
          <small>{{ reporte.totals.own_warranty_works_count }} trabajos · la hace el service oficial</small>
        </div>
        <div>
          <span class="resumen__parte"><i style="background: var(--dot-amber)" />Fuera de garantía</span>
          <strong :data-count="Number(reporte.totals.out_of_warranty_amount)" data-decimals="2" data-prefix="$ ">$ {{ dinero(reporte.totals.out_of_warranty_amount) }}</strong>
          <small>{{ reporte.totals.out_of_warranty_works_count }} trabajos · {{ porcentaje(reporte.totals.out_of_warranty_amount, reporte.totals.total_amount) }}</small>
        </div>
      </div>
    </article>

    <article class="panel" data-rise>
      <div class="panel__head panel__head--stack">
        <div class="panel__head-row">
          <h2>Cierre por empresa</h2>
          <p>Un cierre emitido congela el número: el período ya no se recalcula. Tocá una empresa para ver sus trabajos.</p>
        </div>
        <div class="filtros" role="group" aria-label="Filtrar por estado">
          <button
            v-for="f in filtros"
            :key="f.key"
            type="button"
            :class="['filtro', { 'is-active': filtro === f.key }]"
            :aria-pressed="filtro === f.key"
            @click="filtro = f.key"
          >
            <i class="dot" :style="{ '--dot': f.dot }" />{{ f.texto }} <span>{{ f.total }}</span>
          </button>
        </div>
      </div>

      <div v-if="filasVisibles.length" class="tabla-scroll">
        <table class="tabla">
          <thead>
            <tr>
              <th>Empresa</th>
              <th class="num">Trabajos</th>
              <th class="num">Garantía de terceros</th>
              <th class="num">Garantía propia</th>
              <th class="num">Fuera de garantía</th>
              <th class="num">Total</th>
              <th>Estado</th>
              <th v-if="puedeAdministrar" class="acciones">Acciones</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(fila, i) in filasVisibles" :key="fila.id">
              <tr
                class="fila-empresa"
                :style="{ '--i': Math.min(i, 12) }"
                :class="{ 'is-open': abierta === fila.id }"
                tabindex="0"
                :aria-expanded="abierta === fila.id"
                @click="abierta = abierta === fila.id ? null : fila.id"
                @keydown.enter="abierta = abierta === fila.id ? null : fila.id"
              >
                <td class="empresa-nombre">{{ fila.datos.billing_customer_name || "Sin nombre" }}</td>
                <td class="num">{{ fila.datos.works_count }}</td>
                <td class="num">
                  {{ Number(fila.datos.warranty_amount) ? dinero(fila.datos.warranty_amount) : "—" }}
                  <small v-if="fila.datos.warranty_works_count">{{ fila.datos.warranty_works_count }} {{ fila.datos.warranty_works_count === 1 ? "trabajo" : "trabajos" }}</small>
                </td>
                <td class="num">
                  {{ Number(fila.datos.own_warranty_amount) ? dinero(fila.datos.own_warranty_amount) : "—" }}
                  <small v-if="fila.datos.own_warranty_works_count">{{ fila.datos.own_warranty_works_count }} {{ fila.datos.own_warranty_works_count === 1 ? "trabajo" : "trabajos" }}</small>
                </td>
                <td class="num">
                  {{ Number(fila.datos.out_of_warranty_amount) ? dinero(fila.datos.out_of_warranty_amount) : "—" }}
                  <small v-if="fila.datos.out_of_warranty_works_count">{{ fila.datos.out_of_warranty_works_count }} {{ fila.datos.out_of_warranty_works_count === 1 ? "trabajo" : "trabajos" }}</small>
                </td>
                <td class="num"><strong>{{ dinero(fila.datos.total_amount) }}</strong></td>
                <td>
                  <span v-if="fila.cierre" class="status-chip" :style="{ '--dot': ESTADOS[fila.cierre.status]?.dot }">{{ ESTADOS[fila.cierre.status]?.texto ?? fila.cierre.status }}</span>
                  <span v-else class="text-muted">Sin generar</span>
                  <small v-if="fila.cierre?.invoice_number" class="factura">Factura {{ fila.cierre.invoice_number }}</small>
                </td>
                <td v-if="puedeAdministrar" class="acciones" @click.stop>
                  <template v-if="fila.cierre">
                    <button v-if="fila.cierre.status === 'draft'" class="btn" type="button" :disabled="ocupada" @click="emitir(fila.cierre)">Emitir</button>
    <button v-if="fila.cierre.status === 'draft'" class="btn" type="button" :disabled="ocupada" @click="generarEmpresa(fila.id, fila.datos.billing_customer_name, true)">Regenerar</button>
                    <button v-if="fila.cierre.status === 'issued'" class="btn" type="button" :disabled="ocupada" @click="abrirLiquidacion(fila.cierre)">Liquidar</button>
                    <button v-if="fila.cierre.status === 'draft' || fila.cierre.status === 'issued'" class="anular" type="button" :disabled="ocupada" @click="anular(fila.cierre)">Anular</button>
                    <span v-if="fila.cierre.status === 'settled'" class="text-muted">liquidado {{ fecha(fila.cierre.settled_at) }}</span>
                  </template>
                  <button v-else class="btn" type="button" :disabled="ocupada" @click="generarEmpresa(fila.id, fila.datos.billing_customer_name)">Generar</button>
                </td>
              </tr>
              <tr v-if="abierta === fila.id" :key="`detalle-${fila.id}`">
                <td :colspan="puedeAdministrar ? 8 : 7" class="detalle">
                  <table v-if="fila.datos.works.length" class="tabla tabla-detalle">
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
                      <tr v-for="obra in fila.datos.works" :key="obra.work_order_id">
                        <td class="ot-code">#{{ obra.number }}</td>
                        <td class="text-muted">{{ obra.legacy_number || "—" }}</td>
                        <td>{{ obra.client_name || "—" }}</td>
                        <td>
                          {{ obra.equipment || "—" }}
                          <span v-if="obra.serial_number" class="text-muted">· {{ obra.serial_number }}</span>
                        </td>
                        <td class="text-muted">{{ obra.work_area || "—" }}</td>
                        <td>
                          <span class="status-chip" :style="{ '--dot': obra.warranty_type === 1 ? 'var(--dot-blue)' : obra.warranty_type === 2 ? 'var(--dot-teal)' : 'var(--dot-amber)' }">
                            {{ garantiaTexto(obra.warranty_type) }}
                          </span>
                        </td>
                        <td class="num">{{ dinero(obra.amount) }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <p v-else class="detalle__vacio">Sin trabajos para mostrar.</p>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <p v-else-if="!cargando" class="vacio">
        {{ filtro === "all" ? `En ${etiquetaPeriodo(period)} no hay trabajos para liquidar.` : "No hay empresas con ese estado." }}
      </p>
    </article>

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
.cierre { display:flex; flex-direction:column; gap:24px; }
.heading { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; flex-wrap:wrap; }
.heading h1 { margin:0 0 6px; font-size:28px; font-weight:700; }
.heading p { margin:0; max-width:620px; font-size:15px; color:var(--color-text-secondary); }
.heading__actions { display:flex; align-items:center; gap:12px; }
.periodo { display:flex; align-items:center; border:1px solid var(--color-border-strong); border-radius:var(--radius-md); }
.periodo__flecha { display:grid; place-items:center; width:44px; height:44px; border:0; background:transparent; color:var(--color-text-primary); cursor:pointer; border-radius:var(--radius-md); }
.periodo__flecha:hover:not(:disabled) { background:var(--color-surface-hover); }
.periodo__flecha:disabled { color:var(--color-text-muted); cursor:default; }
.periodo__mes { min-width:130px; text-align:center; font-size:14px; font-weight:600; }

.panel { border:1px solid var(--color-border); border-radius:var(--radius-lg); background:var(--color-surface); min-width:0; overflow:hidden; }
.panel--padded { padding:24px; }
.panel h2 { margin:0; font-size:16px; font-weight:600; }
.panel__head { padding:24px 24px 18px; border-bottom:1px solid var(--color-border); }
.panel__head--stack { display:flex; flex-direction:column; gap:16px; }
.panel__head-row { display:flex; justify-content:space-between; align-items:baseline; gap:16px; flex-wrap:wrap; }
.panel__head-row p { margin:0; font-size:13px; color:var(--color-text-secondary); }

.resumen__head { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; flex-wrap:wrap; }
.resumen__label { margin:0; font-size:13px; color:var(--color-text-secondary); }
.resumen__total { font-size:36px; font-weight:700; line-height:1.2; font-variant-numeric:tabular-nums; }
.resumen__meta { margin:0 0 6px; font-size:14px; color:var(--color-text-secondary); }
.resumen__barra { display:flex; gap:3px; height:12px; margin:18px 0 20px; border-radius:99px; overflow:hidden; background:var(--color-chip); }
.resumen__barra i { display:block; }
.resumen__partes { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:24px; }
.resumen__partes > div { display:flex; flex-direction:column; gap:4px; }
.resumen__parte { display:flex; align-items:center; gap:8px; font-size:13px; color:var(--color-text-secondary); }
.resumen__parte i { width:10px; height:10px; border-radius:2px; }
.resumen__partes strong { font-size:20px; font-weight:700; font-variant-numeric:tabular-nums; }
.resumen__partes small { font-size:13px; color:var(--color-text-muted); }

.filtros { display:flex; gap:10px; flex-wrap:wrap; }
.filtro { display:inline-flex; align-items:center; gap:8px; padding:9px 16px; border:1px solid var(--color-border-strong); border-radius:999px; background:transparent; color:var(--color-text-primary); font-size:14px; font-weight:500; cursor:pointer; }
.filtro span { color:var(--color-text-muted); }
.filtro:hover { background:var(--color-surface-hover); }
.filtro.is-active { background:var(--color-chip); border-color:var(--color-primary); color:var(--color-link); }

.tabla-scroll { overflow-x:auto; }
.tabla { width:100%; border-collapse:collapse; }
.tabla th { padding:14px 16px; text-align:left; font-size:11px; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--color-text-muted); border-bottom:1px solid var(--color-border); vertical-align:bottom; }
.tabla td { padding:12px 16px; font-size:14px; border-bottom:1px solid var(--color-border); vertical-align:middle; }
.tabla th:first-child, .tabla td:first-child { padding-left:24px; }
.tabla th:last-child, .tabla td:last-child { padding-right:24px; }
.tabla tbody tr:last-child > td { border-bottom:0; }
.num { text-align:right !important; font-variant-numeric:tabular-nums; white-space:nowrap; }
.num small { display:block; font-size:12px; color:var(--color-text-muted); }
.fila-empresa { cursor:pointer; }
/* Las filas entran con CSS y no con GSAP: si GSAP toca los tr, al filtrar Vue puede dejar
   la fila equivocada en pantalla. */
.fila-empresa { animation:fila-entra .35s cubic-bezier(.2,.8,.2,1) both; animation-delay:calc(var(--i, 0) * 35ms); }
@keyframes fila-entra { from { opacity:0; transform:translateY(8px); } }
@media (prefers-reduced-motion: reduce) { .fila-empresa { animation:none; } }
.fila-empresa:hover, .fila-empresa.is-open { background:var(--color-surface-hover); }
.empresa-nombre { font-weight:600; max-width:240px; }
.factura { display:block; margin-top:4px; font-size:12px; color:var(--color-text-muted); }
.acciones { text-align:right !important; white-space:nowrap; }
.acciones .btn { padding:9px 18px; }
.anular { margin-left:8px; padding:9px 8px; border:0; background:transparent; color:var(--dot-red); font-size:14px; font-weight:500; cursor:pointer; }
.anular:hover:not(:disabled) { text-decoration:underline; }
.anular:disabled { color:var(--color-text-muted); cursor:not-allowed; }
.detalle { padding:0 !important; background:var(--color-bg); }
.tabla-detalle th, .tabla-detalle td { padding:9px 16px; font-size:13px; }
.detalle__vacio, .vacio { margin:0; padding:20px 24px; color:var(--color-text-secondary); }

.modal-cuerpo { padding:4px 0 12px; display:grid; gap:14px; }
.modal__acciones { display:flex; justify-content:flex-end; gap:8px; padding-top:8px; }

@media (max-width:760px) {
  .heading h1 { font-size:22px; }
  .heading__actions { width:100%; flex-wrap:wrap; }
  .periodo { flex:1; justify-content:space-between; }
  .resumen__total { font-size:28px; }
  .resumen__partes { grid-template-columns:1fr; gap:14px; }
  .panel--padded, .panel__head { padding:16px; }
}
</style>
