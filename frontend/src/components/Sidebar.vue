<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";
import VogelLogo from "./VogelLogo.vue";
import IconDashboard from "./IconDashboard.vue";
import IconCompanies from "./IconCompanies.vue";
import IconUsers from "./IconUsers.vue";
import IconRoles from "./IconRoles.vue";
import IconSettings from "./IconSettings.vue";

defineProps<{ open?: boolean }>();
const emit = defineEmits<{ (e: "close"): void }>();

const session = useSessionStore();
const route = useRoute();
const router = useRouter();

interface NavLink {
  id: string;
  label: string;
  to: string;
  icon: unknown;
  visible: boolean;
}

const links = computed<NavLink[]>(() => {
  const platform = session.isSuperAdmin;
  return [
    {
      id: "dashboard",
      label: "Dashboard",
      to: "/app/dashboard",
      icon: IconDashboard,
      visible: platform || session.activeCompany !== null,
    },
    {
      id: "companies",
      label: "Empresas",
      to: "/app/companies",
      icon: IconCompanies,
      visible: platform,
    },
    {
      id: "users",
      label: "Usuarios",
      to: "/app/users",
      icon: IconUsers,
      visible:
        platform ||
        session.hasPermission("users.view"),
    },
    {
      id: "roles",
      label: "Roles y permisos",
      to: "/app/roles",
      icon: IconRoles,
      visible:
        platform ||
        session.hasPermission("roles.view"),
    },
    {
      id: "settings",
      label: "Configuración",
      to: "/app/settings",
      icon: IconSettings,
      visible: platform,
    },
  ];
});

function navigate(to: string) {
  router.push(to);
  emit("close");
}
</script>

<template>
  <div v-if="open" class="sidebar__scrim" @click="emit('close')" />
  <aside :class="['sidebar', { 'is-open': open }]">
    <div class="sidebar__brand">
      <VogelLogo :size="58" />
    </div>

    <nav class="sidebar__nav" aria-label="Principal">
      <div class="sidebar__section-title">Plataforma</div>
      <template v-for="link in links" :key="link.id">
        <a
          v-if="link.visible"
          :class="['sidebar__link', { 'is-active': route.path.startsWith(link.to) }]"
          :href="link.to"
          @click.prevent="navigate(link.to)"
        >
          <component :is="link.icon" />
          <span>{{ link.label }}</span>
        </a>
      </template>
    </nav>

    <div class="sidebar__footer">
      <div>v0.2 · {{ session.isSuperAdmin ? "Modo Plataforma" : "Modo Empresa" }}</div>
      <div>vogel-gestion-servicios</div>
    </div>
  </aside>
</template>