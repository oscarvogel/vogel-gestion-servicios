import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import Sidebar from "../components/Sidebar.vue";
import { useSessionStore, type MeResponse } from "../stores/session";

vi.mock("vue-router", () => ({
  useRoute: () => ({ path: "/app/dashboard" }),
  useRouter: () => ({ push: vi.fn() }),
}));

const base: MeResponse = {
  id: 1,
  email: "superadmin@vogel.local",
  full_name: "SuperAdmin Vogel",
  is_superadmin: true,
  active: true,
  memberships: [],
  permissions: [],
};

async function montar(build?: MeResponse["build"]) {
  setActivePinia(createPinia());
  const session = useSessionStore();
  session.me = { ...base, build };
  const wrapper = mount(Sidebar, { global: { stubs: { RouterLink: true } } });
  await flushPromises();
  return wrapper;
}

function pie(wrapper: Awaited<ReturnType<typeof montar>>) {
  // Los links del menu tambien usan .sidebar__label: el pie es el del footer.
  return wrapper.find(".sidebar__footer .sidebar__label").text();
}

describe("la version que se ve en el pie del menu", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("muestra la version del sistema y el commit del deploy", async () => {
    const w = await montar({ version: "0.1.0", commit: "35b55c98eb9fc847642793926470209fd3b9da78" });

    expect(pie(w)).toContain("v0.2");
    // El commit abreviado: es lo que dice que build esta en pantalla.
    expect(pie(w)).toContain("35b55c9");
  });

  it("sin commit del deploy cae al commit del bundle", async () => {
    const w = await montar({ version: "0.1.0", commit: null });

    // El bundle trae el sha del build (en local sale de git) o, si no, la hora.
    expect(pie(w)).toMatch(/v0\.2 · (\w{7}|build \d{2}\/\d{2} \d{2}:\d{2})/);
  });

  it("sin informacion de build igual muestra la version", async () => {
    const w = await montar();

    expect(pie(w)).toContain("v0.2");
    expect(pie(w)).toContain("Modo plataforma");
  });
});
