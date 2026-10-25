/**
 * El maestro de áreas de trabajo (marca + política) y cómo se lee en pantalla.
 *
 * El área es lo que decide dos cosas de la orden: **la garantía** y **a qué empresa se
 * liquida**. Por eso no se escriben sueltas en la orden: se elige un área y todo lo
 * demás sale de ahí. Si se escribieran por separado, la orden y el cierre a marcas
 * podrían terminar discrepando sin que nadie lo note.
 */
export interface WorkArea {
  id: number;
  area_code: string;
  area_name: string;
  policy_code: string;
  policy_description: string | null;
  is_principal: boolean;
  billing_customer_id: number | null;
  billing_customer_name: string | null;
  warranty_type: number;
  warranty_label: string;
  liquidate_mode: number;
  active: boolean;
}

import { apiGet } from "./api";

/** Cómo se ve el área: marca + política. La política vacía es la principal del área. */
export function etiquetaArea(area: WorkArea): string {
  return area.policy_code ? `${area.area_name} · ${area.policy_code}` : area.area_name;
}

/** Para comparar y filtrar: sin mayúsculas, sin acentos y sin espacios de los bordes. */
export function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

let cache: WorkArea[] | null = null;
let cargando: Promise<WorkArea[]> | null = null;

/**
 * El maestro, con caché entre pantallas.
 *
 * El picker lo usa la recepción y la ficha de la orden: si cada uno pidiera el
 * maestro por su cuenta, serían dos viajes al servidor por la misma pantalla.
 * `invalidarAreas()` se llama después de dar de alta o editar un área, para que el
 * picker la vea sin recargar la página.
 */
export async function cargarAreas(forzar = false): Promise<WorkArea[]> {
  if (cache && !forzar) return cache;
  if (!cargando || forzar) {
    cargando = apiGet<WorkArea[]>("/work-areas").then((areas) => {
      cache = areas;
      cargando = null;
      return areas;
    });
  }
  return cargando;
}

export function invalidarAreas(): void {
  cache = null;
}
