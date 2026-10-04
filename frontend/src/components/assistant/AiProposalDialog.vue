<script setup lang="ts">
/**
 * Confirmacion de una propuesta. El unico lugar donde se puede ejecutar una accion de la IA.
 *
 * Lo que este dialogo tiene que hacer bien:
 *
 * 1. Mostrar **que va a pasar**, no quepidio el modelo. Con la herramienta, en castellano.
 * 2. Dejar **editar** los valores. La persona puede corregirlo, y lo que se escribe es lo
 *    corregido: por eso los campos son editables y se manda lo que quedo en pantalla.
 * 3. Marcar el **riesgo** antes de confirmar. Un repuesto con precio o un cambio de estado
 *    que le avisa al cliente se tienen que ver antes de apretar, no despues.
 * 4. No dejar aplicar dos veces. El backend tiene el candado, pero el boton se deshabilita
 *    mientras corre para que el operador no se confunda con un error.
 */
import { computed, ref, watch } from "vue";
import Modal from "../Modal.vue";
import type { Propuesta } from "../../lib/ai";

const props = defineProps<{ open: boolean; propuesta: Propuesta | null; busy?: boolean }>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "confirmar", argumentos: Record<string, unknown>): void;
}>();

const editados = ref<Record<string, unknown>>({});

watch(
  () => props.propuesta,
  (p) => {
    // Se parte siempre de lo que propuso el modelo, nunca de una edicion anterior: si se
    // abre otra propuesta, no puede quedar el valor de la anterior pegado.
    editados.value = p ? { ...p.argumentos_propuestos } : {};
  },
  { immediate: true },
);

const ETIQUETAS: Record<string, string> = {
  crear_cliente: "Dar de alta un cliente",
  crear_equipo: "Registrar un equipo",
  crear_ot: "Abrir una orden de trabajo",
  actualizar_ot: "Modificar una orden de trabajo",
  agregar_diagnostico: "Guardar el diagnóstico",
  agregar_trabajo: "Sumar trabajo a una orden",
  agregar_repuesto: "Sumar un repuesto a una orden",
  generar_presupuesto: "Generar el presupuesto de una orden",
};

const CAMPOS: Record<string, string> = {
  nombre: "Nombre",
  documento: "Documento",
  telefono: "Teléfono",
  whatsapp: "WhatsApp",
  email: "Email",
  direccion: "Dirección",
  notas: "Notas",
  cliente_id: "Id del cliente",
  equipo_id: "Id del equipo",
  categoria: "Categoría",
  marca: "Marca",
  modelo: "Modelo",
  numero_de_serie: "N° de serie",
  descripcion: "Descripción",
  falla_reportada: "Falla reportada",
  condicion_fisica: "Condición física",
  accesorios: "Accesorios",
  entrega_estimada: "Entrega estimada",
  estado_id: "Id del estado",
  estado: "Estado",
  nota: "Observación",
  diagnostico: "Diagnóstico",
  notas_tecnicas: "Notas técnicas",
  cantidad: "Cantidad",
  precio_unitario: "Precio unitario",
  costo_unitario: "Costo unitario",
  orden: "Id de la orden",
};

const titulo = computed(() =>
  props.propuesta ? (ETIQUETAS[props.propuesta.tool] ?? props.propuesta.tool) : "",
);

const campos = computed(() =>
  Object.entries(props.propuesta?.argumentos_propuestos ?? {}).map(([clave, valor]) => ({
    clave,
    etiqueta: CAMPOS[clave] ?? clave,
    valor,
  })),
);

const esNumero = (clave: string) =>
  ["precio_unitario", "costo_unitario", "cantidad", "orden", "cliente_id", "equipo_id", "estado_id"].includes(
    clave,
  );

function editado(clave: string): string {
  const v = editados.value[clave];
  return v === null || v === undefined ? "" : String(v);
}

function cambiar(clave: string, evento: Event) {
  const bruto = (evento.target as HTMLInputElement).value;
  editados.value = { ...editados.value, [clave]: esNumero(clave) && bruto !== "" ? Number(bruto) : bruto };
}

const riesgos = computed(() => {
  const r = props.propuesta?.riesgo;
  if (r === "financiero") return "Mueve plata: los importes van a la cuenta del cliente.";
  if (r === "comunicacion") return "Se le avisa al cliente y eso no se puede deshacer.";
  return null;
});

function confirmar() {
  emit("confirmar", { ...editados.value });
}
</script>

<template>
  <Modal :open="open" :title="titulo" width="620px" @close="emit('close')">
    <div v-if="propuesta" class="prop">
      <!-- El riesgo va primero: es lo que hay que saber antes de confirmar. -->
      <div v-if="riesgos || propuesta.notifica_cliente" class="prop__riesgo">
        <span v-if="propuesta.riesgo === 'financiero'" class="badge badge--warning">financiero</span>
        <span v-else-if="propuesta.riesgo === 'comunicacion'" class="badge badge--warning">comunicación</span>
        <p v-if="riesgos">{{ riesgos }}</p>
        <p v-if="propuesta.notifica_cliente && propuesta.riesgo !== 'comunicacion'">
          Al aplicar se le avisa al cliente.
        </p>
      </div>

      <p class="prop__intro">
        Esto es lo que propuso el asistente. <strong>Revisalo y corregí lo que haga falta</strong>:
        se va a guardar exactamente lo que dejes acá.
      </p>

      <div class="prop__campos">
        <label v-for="c in campos" :key="c.clave" class="field">
          <span>{{ c.etiqueta }}</span>
          <input
            :value="editado(c.clave)"
            :type="esNumero(c.clave) ? 'number' : 'text'"
            :step="c.clave === 'cantidad' ? 'any' : undefined"
            @input="cambiar(c.clave, $event)"
          />
        </label>
      </div>

      <div class="prop__pie">
        <span class="text-muted">Propuesta N° {{ propuesta.id }}</span>
        <div class="prop__acciones">
          <button class="btn btn--ghost" :disabled="busy" @click="emit('close')">Cancelar</button>
          <button class="btn btn--primary" :disabled="busy" @click="confirmar">
            {{ busy ? "Aplicando…" : "Confirmar y aplicar" }}
          </button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.prop {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 20px 20px;
}
.prop__riesgo {
  padding: 12px 14px;
  border: 1px solid rgba(245, 158, 11, 0.4);
  border-radius: 10px;
  background: rgba(245, 158, 11, 0.1);
}
.prop__riesgo p {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--color-text-primary, #e5edf7);
}
.prop__intro {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary, #cbd5e1);
}
.prop__campos {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.prop__campos .field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.prop__campos .field > span {
  color: var(--color-text-muted, #94a3b8);
}
.prop__campos input {
  background: #10283f;
  color: #e5edf7;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 8px;
  padding: 8px 10px;
  color-scheme: dark;
  width: 100%;
}
.prop__pie {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 4px;
  border-top: 1px solid rgba(148, 163, 184, 0.15);
}
.prop__acciones {
  display: flex;
  gap: 8px;
}
@media (max-width: 600px) {
  .prop__campos {
    grid-template-columns: 1fr;
  }
  .prop__pie {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
