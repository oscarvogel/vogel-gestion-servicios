import { describe, it, expect, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useThemeStore } from "../stores/theme";

describe("theme store", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    setActivePinia(createPinia());
  });

  it("defaults to dark when no preference is stored", () => {
    const store = useThemeStore();
    expect(store.theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("respects an existing light preference", () => {
    localStorage.setItem("vogel.theme", "light");
    setActivePinia(createPinia());
    const store = useThemeStore();
    expect(store.theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("toggles between themes and persists", () => {
    const store = useThemeStore();
    store.toggle();
    expect(store.theme).toBe("light");
    expect(localStorage.getItem("vogel.theme")).toBe("light");
    store.toggle();
    expect(store.theme).toBe("dark");
    expect(localStorage.getItem("vogel.theme")).toBe("dark");
  });
});