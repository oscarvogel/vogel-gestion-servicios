import { defineStore } from "pinia";
import { ref } from "vue";
import { THEME_KEY } from "../lib/api";

type Theme = "dark" | "light";

export const useThemeStore = defineStore("theme", () => {
  const initial: Theme = (() => {
    const stored = localStorage.getItem(THEME_KEY) as Theme | null;
    if (stored === "dark" || stored === "light") return stored;
    return "dark"; // Default Vogel: dark
  })();

  const theme = ref<Theme>(initial);
  let fadeTimer = 0;

  function apply(value: Theme) {
    document.documentElement.setAttribute("data-theme", value);
    localStorage.setItem(THEME_KEY, value);
  }

  // El cambio de tema se funde en vez de saltar de golpe, que encandila. Donde el navegador
  // tiene View Transitions se hace un fundido de toda la pagina; si no, una transicion de
  // colores que se saca enseguida para no frenar los hover del resto de la app.
  function applySmooth(value: Theme) {
    const root = document.documentElement;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return apply(value);
    const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
    if (doc.startViewTransition) {
      doc.startViewTransition(() => apply(value));
      return;
    }
    root.classList.add("theme-fading");
    apply(value);
    // Si el usuario cambia el tema dos veces seguidas, el primer temporizador sacaria la
    // clase a mitad del segundo fundido y la transicion se cortaria.
    if (fadeTimer) window.clearTimeout(fadeTimer);
    fadeTimer = window.setTimeout(() => {
      root.classList.remove("theme-fading");
      fadeTimer = 0;
    }, 500);
  }

  function toggle() {
    theme.value = theme.value === "dark" ? "light" : "dark";
    applySmooth(theme.value);
  }

  function set(value: Theme) {
    theme.value = value;
    applySmooth(value);
  }

  apply(initial);

  return { theme, toggle, set };
});