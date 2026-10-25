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
import IconAssistant from "./IconAssistant.vue";
import IconCierre from "./IconCierre.vue";
import IconTecnicos from "./IconTecnicos.vue";
import IconWorkOrders from "./IconWorkOrders.vue";
import IconCustomers from "./IconCustomers.vue";
import IconSliders from "./IconSliders.vue";
import IconStatuses from "./IconStatuses.vue";
import IconChart from "./IconChart.vue";
import IconCollapse from "./IconCollapse.vue";

defineProps<{ open?: boolean; collapsed?: boolean }>();
const emit = defineEmits<{ (e: "close"): void; (e: "toggle-collapse"): void }>();

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

interface NavGroup {
  title: string;
  links: NavLink[];
}

const groups = computed<NavGroup[]>(() => {
  const platform = session.isSuperAdmin;
  const company = session.activeCompany !== null;
  const companyAdmin = platform || session.activeCompany?.is_admin === true;
  const all: NavGroup[] = [
    {
      // El trabajo de todos los dias.
      title: "Taller",
      links: [
        { id: "dashboard", label: "Inicio", to: "/app/dashboard", icon: IconDashboard, visible: platform || company },
        { id: "work-orders", label: "Órdenes de trabajo", to: "/app/work-orders", icon: IconWorkOrders, visible: company && session.hasPermission("work_orders.view") },
        { id: "customers", label: "Clientes y equipos", to: "/app/customers", icon: IconCustomers, visible: company && session.hasPermission("customers.view") },
        // Junto a las ordenes de trabajo: el cierre de mes es el cierre de esas OTs.
        { id: "cierre-marcas", label: "Cierre a marcas", to: "/app/cierre-marcas", icon: IconCierre, visible: company && session.hasPermission("warranty_settlements.view") },
      ],
    },
    {
      // Quien trabaja y que puede hacer.
      title: "Equipo",
      links: [
        // El maestro de quien hace el trabajo: se asigna desde la orden de trabajo.
        { id: "tecnicos", label: "Técnicos", to: "/app/tecnicos", icon: IconTecnicos, visible: company && session.hasPermission("technicians.view") },
        { id: "users", label: "Usuarios", to: "/app/users", icon: IconUsers, visible: platform || session.hasPermission("users.view") },
        { id: "roles", label: "Roles y permisos", to: "/app/roles", icon: IconRoles, visible: platform || session.hasPermission("roles.view") },
        { id: "companies", label: "Empresas", to: "/app/companies", icon: IconCompanies, visible: platform },
      ],
    },
    {
      title: "Sistema",
      links: [
        { id: "parameters", label: "Parámetros", to: "/app/parameters", icon: IconSliders, visible: company && companyAdmin },
        { id: "work-order-statuses", label: "Estados de OT", to: "/app/work-order-statuses", icon: IconStatuses, visible: company && companyAdmin },
        // Solo se ve con el permiso del modulo. Sin el, la ruta tambien responde 403, pero
        // mejor que el enlace ni exista.
        { id: "assistant", label: "Asistente", to: "/app/assistant", icon: IconAssistant, visible: company && session.hasPermission("ai.use") },
        // Junto al asistente porque es la otra mitad de la misma pregunta: cuanto se uso y
        // cuanto queda. Sin empresa activa no hay "mi consumo", y la ruta tampoco responderia.
        { id: "consumo-ia", label: "Consumo de IA", to: "/app/consumo-ia", icon: IconChart, visible: company && session.hasPermission("ai.use") },
        { id: "settings", label: "Configuración", to: "/app/settings", icon: IconSettings, visible: companyAdmin },
      ],
    },
  ];
  return all
    .map((g) => ({ ...g, links: g.links.filter((l) => l.visible) }))
    .filter((g) => g.links.length);
});

function navigate(to: string) {
  router.push(to);
  emit("close");
}
</script>

<template>
  <div v-if="open" class="sidebar__scrim" @click="emit('close')" />
  <aside :class="['sidebar', { 'is-open': open, 'sidebar--collapsed': collapsed }]">
    <div class="sidebar__brand">
      <VogelLogo :size="collapsed ? 40 : 48" />
    </div>

    <nav class="sidebar__nav" aria-label="Principal">
      <div v-for="group in groups" :key="group.title" class="sidebar__group">
        <div class="sidebar__section-title">{{ group.title }}</div>
        <a
          v-for="link in group.links"
          :key="link.id"
          :class="['sidebar__link', { 'is-active': route.path.startsWith(link.to) }]"
          :href="link.to"
          :title="collapsed ? link.label : undefined"
          :aria-current="route.path.startsWith(link.to) ? 'page' : undefined"
          @click.prevent="navigate(link.to)"
        >
          <component :is="link.icon" />
          <span class="sidebar__label">{{ link.label }}</span>
        </a>
      </div>
    </nav>

    <button
      type="button"
      class="sidebar__collapse"
      :aria-expanded="!collapsed"
      :title="collapsed ? 'Mostrar menú' : 'Ocultar menú'"
      @click="emit('toggle-collapse')"
    >
      <IconCollapse />
      <span class="sidebar__label">Ocultar menú</span>
    </button>
  </aside>
</template>
