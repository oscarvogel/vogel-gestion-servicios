import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { THEME_KEY } from "../lib/api";

type Theme = "dark" | "light";

export const useThemeStore = defineStore("theme", () => {
  const initial: Theme = (() => {
    const stored = localStorage.getItem(THEME_KEY) as Theme | null;
    if (stored === "dark" || stored === "light") return stored;
    return "dark"; // Default Vogel: dark
  })();

  const theme = ref<Theme>(initial);

  function apply(value: Theme) {
    document.documentElement.setAttribute("data-theme", value);
    localStorage.setItem(THEME_KEY, value);
  }

  function toggle() {
    theme.value = theme.value === "dark" ? "light" : "dark";
    apply(theme.value);
  }

  function set(value: Theme) {
    theme.value = value;
    apply(value);
  }

  apply(initial);

  watch(theme, (next) => apply(next));

  return { theme, toggle, set };
});