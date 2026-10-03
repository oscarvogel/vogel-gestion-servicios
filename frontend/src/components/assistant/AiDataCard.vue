<script setup lang="ts">
/**
 * La ficha: los datos, tal como los armo el servidor.
 *
 * Va arriba del texto del asistente a proposito. El texto del modelo no puede contener
 * datos (el backend descarta el texto si trae numeros o estados), asi que la ficha es la
 * unica fuente de verdad de lo que el operador ve. Mostrarla despues, como un detalle,
 * seria mostrar el comentario del modelo como si fuera la informacion.
 */
import { computed } from "vue";
import type { Ficha } from "../../lib/ai";

const props = defineProps<{ ficha: Ficha }>();

const bloques = computed(() => props.ficha?.bloques ?? []);
const tieneAlgo = computed(() => bloques.value.some((b) => !b.vacio));

function fecha(valor: string | null | undefined): string {
  if (!valor) return "—";
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return valor;
  return d.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}

const COLUMNAS_CLIENTE: { campo: string; etiqueta: string }[] = [
  { campo: "id", etiqueta: "N°" },
  { campo: "nombre", etiqueta: "Nombre" },
  { campo: "documento", etiqueta: "Documento" },
  { campo: "telefono", etiqueta: "Teléfono" },
  { campo: "whatsapp", etiqueta: "WhatsApp" },
  { campo: "email", etiqueta: "Email" },
  { campo: "cantidad_de_equipos", etiqueta: "Equipos" },
];

const COLUMNAS_EQUIPO: { campo: string; etiqueta: string }[] = [
  { campo: "id", etiqueta: "N°" },
  { campo: "cliente", etiqueta: "Cliente" },
  { campo: "categoria", etiqueta: "Categoría" },
  { campo: "marca", etiqueta: "Marca" },
  { campo: "modelo", etiqueta: "Modelo" },
  { campo: "numero_de_serie", etiqueta: "N° de serie" },
];

function columnas(bloque: { tipo: string }): { campo: string; etiqueta: string }[] {
  if (bloque.tipo === "buscar_cliente") return COLUMNAS_CLIENTE;
  if (bloque.tipo === "buscar_equipo") return COLUMNAS_EQUIPO;
  return [];
}

function texto(valor: unknown): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  return String(valor);
}

function filas(bloque: { resultados?: Record<string, unknown>[] }): Record<string, unknown>[] {
  return bloque.resultados ?? [];
}
</script>

<template>
  <div v-if="tieneAlgo" class="ficha">
    <div class="ficha__rotulo">Datos de tu empresa</div>

    <section v-for="bloque in bloques" :key="bloque.tipo" class="ficha__bloque">
      <header class="ficha__titulo">
        {{ bloque.titulo }}
        <span v-if="bloque.tipo === 'consultar_historial_equipo' && !bloque.vacio" class="ficha__conteo">
          {{ bloque.cantidad_de_ordenes }} orden(es)
        </span>
      </header>

      <p v-if="bloque.vacio" class="ficha__vacio">
        {{ bloque.detalle ?? "Sin resultados para esa consulta." }}
      </p>

      <!-- Historial de un equipo: el equipo arriba y despues sus ordenes. -->
      <template v-else-if="bloque.tipo === 'consultar_historial_equipo'">
        <div v-if="bloque.equipo" class="ficha__equipo">
          <strong>{{ bloque.equipo.marca }} {{ bloque.equipo.modelo }}</strong>
          <span class="text-muted">
            {{ bloque.equipo.categoria }} · serie {{ texto(bloque.equipo.numero_de_serie) }} ·
            cliente {{ texto(bloque.equipo.cliente) }}
          </span>
        </div>
        <table v-if="(bloque.historial ?? []).length" class="table ficha__tabla">
          <thead>
            <tr>
              <th>Orden</th>
              <th>Estado</th>
              <th>Recibida</th>
              <th>Entrega estimada</th>
              <th>Falla reportada</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="o in bloque.historial ?? []" :key="o.orden">
              <td>#{{ o.orden }}</td>
              <td><span class="badge badge--muted">{{ o.estado }}</span></td>
              <td>{{ fecha(o.recibida) }}</td>
              <td>{{ fecha(o.entrega_estimada) }}</td>
              <td class="ficha__falla">{{ o.falla_reportada }}</td>
            </tr>
          </tbody>
        </table>
      </template>

      <!-- Resultados de busqueda: tabla simple. -->
      <table v-else-if="filas(bloque).length" class="table ficha__tabla">
        <thead>
          <tr>
            <th v-for="c in columnas(bloque)" :key="c.campo">{{ c.etiqueta }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(fila, i) in filas(bloque)" :key="i">
            <td v-for="c in columnas(bloque)" :key="c.campo">{{ texto(fila[c.campo]) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.ficha {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px;
  border: 1px solid rgba(59, 130, 246, 0.35);
  border-left: 3px solid var(--color-primary, #3b82f6);
  border-radius: 12px;
  background: rgba(59, 130, 246, 0.07);
}
.ficha__rotulo {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-primary, #3b82f6);
  font-weight: 700;
}
.ficha__bloque {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ficha__titulo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  color: var(--color-text-primary, #e5edf7);
}
.ficha__conteo {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-muted, #94a3b8);
}
.ficha__vacio {
  margin: 0;
  color: var(--color-text-muted, #94a3b8);
  font-size: 14px;
}
.ficha__equipo {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.35);
}
.ficha__equipo span {
  font-size: 13px;
}
.ficha__tabla {
  width: 100%;
  font-size: 13px;
}
.ficha__tabla th {
  text-align: left;
  color: var(--color-text-muted, #94a3b8);
  font-weight: 600;
  white-space: nowrap;
}
.ficha__falla {
  max-width: 320px;
  white-space: normal;
}
@media (max-width: 720px) {
  .ficha__tabla th:nth-child(3),
  .ficha__tabla td:nth-child(3) {
    display: none;
  }
}
</style>
