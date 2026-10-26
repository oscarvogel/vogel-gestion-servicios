/**
 * Microanimaciones con GSAP. Las vistas marcan lo que se anima con atributos y llaman a
 * `reveal()`; aca vive toda la configuracion para que se mueva igual en todas las pantallas.
 *
 * - `data-rise`: aparece subiendo un poco, escalonado.
 * - `data-grow-x` / `data-grow-y`: barra que se llena desde la izquierda / desde abajo.
 * - `data-count="48"`: el numero cuenta hasta su valor. Opcionales `data-decimals` y
 *   `data-prefix`. El elemento tiene que contener SOLO el numero: se reescribe su texto.
 *
 * El HTML siempre trae el valor final que pinta Vue, asi que sin animacion (movimiento
 * reducido, tests) se ve lo mismo.
 */
import { gsap } from "gsap";
import { onBeforeUnmount, type Ref } from "vue";

export function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  } catch {
    return false;
  }
}

function formatear(valor: number, decimales: number, prefijo: string): string {
  return prefijo + valor.toLocaleString("es-AR", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
}

/** Anima lo marcado dentro de `scope`. Devuelve la timeline, o null si no se anima. */
export function revealIn(scope: HTMLElement): gsap.core.Timeline | null {
  if (prefersReducedMotion()) return null;
  const q = gsap.utils.selector(scope);
  const tl = gsap.timeline();

  const rise = q("[data-rise]");
  if (rise.length) {
    tl.from(rise, { y: 10, autoAlpha: 0, stagger: 0.05, duration: 0.4, ease: "power2.out", clearProps: "transform,opacity,visibility" }, 0);
  }
  const growX = q("[data-grow-x]");
  if (growX.length) {
    tl.from(growX, { scaleX: 0, transformOrigin: "left center", stagger: 0.06, duration: 0.8, ease: "power3.out", clearProps: "transform" }, 0.1);
  }
  const growY = q("[data-grow-y]");
  if (growY.length) {
    tl.from(growY, { scaleY: 0, transformOrigin: "bottom center", stagger: 0.03, duration: 0.7, ease: "power3.out", clearProps: "transform" }, 0.1);
  }

  for (const el of q("[data-count]") as HTMLElement[]) {
    const hasta = Number(el.dataset.count);
    if (!Number.isFinite(hasta)) continue;
    const decimales = Number(el.dataset.decimals ?? 0);
    const prefijo = el.dataset.prefix ?? "";
    // El texto final se arma desde el dato, no se lee del DOM: la cuenta anterior puede
    // haber dejado el numero a medio contar (o en cero) y leerlo de ahi congelaria ese
    // valor roto en pantalla.
    const final = formatear(hasta, decimales, prefijo);
    // Si ya conto antes (por ejemplo al cambiar de mes) arranca desde el valor anterior.
    const desde = Number(el.dataset.from ?? 0) || 0;
    el.dataset.from = String(hasta);
    if (desde === hasta) {
      el.textContent = final;
      continue;
    }
    const contador = { v: desde };
    // La cuenta sigue al dato: si el valor cambio (se cargo otro mes), esta cuenta ya no
    // vale y deja de escribir. Sin esto, una cuenta vieja puede pisar el numero nuevo y
    // dejarlo en cero.
    const vigente = () => Number(el.dataset.count) === hasta;
    tl.to(
      contador,
      {
        v: hasta,
        duration: 0.9,
        ease: "power2.out",
        onUpdate: () => {
          if (vigente()) el.textContent = formatear(contador.v, decimales, prefijo);
        },
        // Se deja exactamente el valor del dato, no una version recalculada.
        onComplete: () => {
          if (vigente()) el.textContent = final;
        },
      },
      0,
    );
  }
  return tl;
}

/**
 * Para usar en una vista: `const reveal = useReveal(rootRef)` y llamar `reveal()` cuando el
 * contenido ya esta en el DOM. Cada llamada corta la animacion anterior; al desmontar se
 * revierte todo.
 */
export function useReveal(root: Ref<HTMLElement | null>) {
  let ctx: gsap.Context | null = null;
  onBeforeUnmount(() => ctx?.revert());
  return () => {
    if (!root.value) return;
    ctx?.revert();
    ctx = gsap.context(() => {
      revealIn(root.value!);
    }, root.value);
  };
}

/** Transicion entre secciones: `dir` 1 = se baja en el menu, -1 = se sube, 0 = mismo nivel. */
export function pageLeave(el: Element, dir: number, done: () => void) {
  if (prefersReducedMotion()) return done();
  gsap.to(el, { y: dir * -16, autoAlpha: 0, duration: 0.14, ease: "power2.in", onComplete: done });
}

export function pageEnter(el: Element, dir: number, done: () => void) {
  if (prefersReducedMotion()) return done();
  gsap.fromTo(
    el,
    { y: dir * 28, autoAlpha: 0 },
    {
      y: 0,
      autoAlpha: 1,
      duration: dir === 0 ? 0.2 : 0.38,
      ease: "expo.out",
      // Sin transform residual: rompe position:sticky y los modales fijos.
      clearProps: "transform,opacity,visibility",
      onComplete: done,
    },
  );
}
