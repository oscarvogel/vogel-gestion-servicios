<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRoute } from "vue-router";
import { useSessionStore } from "../stores/session";
import Sidebar from "./Sidebar.vue";
import Topbar from "./Topbar.vue";
import MobileBottomNav from "./MobileBottomNav.vue";

const session = useSessionStore();
const route = useRoute();
const menuOpen = ref(false);

// Menu lateral plegado en escritorio. Se recuerda por navegador; si el storage no esta
// disponible (modo privado), arranca desplegado.
const COLLAPSED_KEY = "vogel.sidebarCollapsed";
function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}
const collapsed = ref(readCollapsed());
watch(collapsed, (v) => {
  try {
    localStorage.setItem(COLLAPSED_KEY, v ? "1" : "0");
  } catch {
    /* sin storage: el estado vive hasta recargar */
  }
});

const title = computed(() => {
  // El orden importa: "/app/work-orders/import" antes que "/app/work-orders".
  const map: Record<string, string> = {
    "/app/dashboard": "Inicio",
    "/app/companies": "Empresas",
    "/app/customers": "Clientes y equipos",
    "/app/users": "Usuarios",
    "/app/work-orders/import": "Importar trabajos",
    "/app/work-orders": "Órdenes de trabajo",
    "/app/work-order-statuses": "Estados de OT",
    "/app/cierre-marcas": "Cierre a marcas",
    "/app/tecnicos": "Técnicos",
    "/app/roles": "Roles y permisos",
    "/app/parameters": "Parámetros",
    "/app/assistant": "Asistente",
    "/app/consumo-ia": "Consumo de IA",
    "/app/settings": "Configuración",
  };
  for (const prefix of Object.keys(map)) {
    if (route.path.startsWith(prefix)) return map[prefix];
  }
  return "Vogel";
});

</script>

<template>
  <div :class="['app-shell', { 'app-shell--collapsed': collapsed }]">
    <Sidebar
      :open="menuOpen"
      :collapsed="collapsed"
      @close="menuOpen = false"
      @toggle-collapse="collapsed = !collapsed"
    />
    <div class="app-main">
      <Topbar :title="title" @toggle-menu="menuOpen = !menuOpen" />
      <main class="app-content">
        <router-view />
      </main>
      <MobileBottomNav @more="menuOpen = true" />
    </div>
  </div>
</template>
