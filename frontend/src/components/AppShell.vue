<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";
import Sidebar from "./Sidebar.vue";
import Topbar from "./Topbar.vue";

const session = useSessionStore();
const router = useRouter();
const route = useRoute();
const menuOpen = ref(false);

const title = computed(() => {
  const map: Record<string, string> = {
    "/app/dashboard": "Dashboard",
    "/app/companies": "Empresas",
    "/app/users": "Usuarios",
    "/app/roles": "Roles y permisos",
    "/app/settings": "Configuración",
  };
  for (const prefix of Object.keys(map)) {
    if (route.path.startsWith(prefix)) return map[prefix];
  }
  return "Vogel";
});

onMounted(async () => {
  if (!session.me) {
    try {
      await session.loadMe();
    } catch (error) {
      router.replace({ name: "login" });
    }
  }
});
</script>

<template>
  <div class="app-shell">
    <Sidebar :open="menuOpen" @close="menuOpen = false" />
    <div class="app-main">
      <Topbar :title="title" @toggle-menu="menuOpen = !menuOpen" />
      <main class="app-content">
        <router-view />
      </main>
    </div>
  </div>
</template>