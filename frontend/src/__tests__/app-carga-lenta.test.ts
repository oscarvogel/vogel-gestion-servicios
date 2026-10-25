import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import App from "../App.vue";
import { useSessionStore } from "../stores/session";

describe("pantalla de verificacion de sesion", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("avisa y ofrece reintentar si la verificacion tarda mas de 8 segundos", async () => {
    const session = useSessionStore();
    session.authStatus = "initializing";
    const wrapper = mount(App, { global: { stubs: { "router-view": true, ToastStack: true } } });
    expect(wrapper.text()).not.toContain("Reintentar");
    await vi.advanceTimersByTimeAsync(8000);
    expect(wrapper.text()).toContain("Reintentar");
    session.authStatus = "authenticated";
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).not.toContain("Verificando tu sesión");
  });
});
