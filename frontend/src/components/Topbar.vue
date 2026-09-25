<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";
import { useThemeStore } from "../stores/theme";
import IconSun from "./IconSun.vue";
import IconMoon from "./IconMoon.vue";
import IconMenu from "./IconMenu.vue";
import IconLogout from "./IconLogout.vue";

defineProps<{ title: string }>();
const emit = defineEmits<{ (e: "toggle-menu"): void }>();

const session = useSessionStore();
const theme = useThemeStore();
const router = useRouter();

const menuOpen = ref(false);

const subtitle = computed(() => {
  if (session.isSuperAdmin && !session.activeCompany) return "Modo plataforma";
  if (session.activeCompany) return session.activeCompany.name;
  return "Sesión activa";
});

async function logout() {
  await session.logout();
  router.push({ name: "login" });
}

async function goToCompanySelector() {
  if (session.isSuperAdmin && session.activeCompany) {
    await session.leaveCompany();
  }
  router.push({ name: "company-selector" });
}
</script>

<template>
  <header class="topbar">
    <div class="flex gap-12" style="align-items:center">
      <button
        class="btn btn--ghost btn--sm"
        type="button"
        @click="emit('toggle-menu')"
        aria-label="Abrir menú"
        style="display:none"
      >
        <IconMenu />
      </button>
      <div>
        <div class="topbar__title">{{ title }}</div>
        <div class="text-muted" style="font-size:12px">{{ subtitle }}</div>
      </div>
    </div>

    <div class="topbar__right">
      <span class="topbar__chip topbar__chip--accent">
        <strong class="topbar__chip--label">{{ session.me?.full_name }}</strong>
        <span v-if="session.isSuperAdmin" style="font-size:11px;letter-spacing:0.1em">SU</span>
      </span>

      <span
        v-if="session.activeCompany"
        class="topbar__chip"
        role="button"
        @click="goToCompanySelector"
      >
        <strong>{{ session.activeCompany.name }}</strong>
        <span style="font-size:11px;color:var(--color-text-muted)">Cambiar</span>
      </span>

      <button
        class="btn btn--ghost btn--sm"
        type="button"
        @click="theme.toggle"
        :aria-label="theme.theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'"
      >
        <IconMoon v-if="theme.theme === 'dark'" />
        <IconSun v-else />
        <span class="topbar__chip--label">{{ theme.theme === 'dark' ? 'Oscuro' : 'Claro' }}</span>
      </button>

      <div style="position:relative">
        <button class="btn btn--ghost btn--sm" type="button" @click="menuOpen = !menuOpen">
          <span style="font-weight:600">{{ session.me?.full_name?.slice(0, 1) ?? "?" }}</span>
        </button>
        <div
          v-if="menuOpen"
          class="card"
          style="position:absolute;right:0;top:calc(100% + 8px);min-width:220px;padding:8px;z-index:50"
        >
          <div style="padding:8px 12px;font-size:13px">
            <div><strong>{{ session.me?.full_name }}</strong></div>
            <div class="text-muted" style="font-size:12px">{{ session.me?.email }}</div>
          </div>
          <hr style="border:none;border-top:1px solid var(--color-border);margin:4px 0" />
          <button
            class="sidebar__link"
            type="button"
            style="width:100%;border:none;background:transparent;text-align:left"
            @click="logout"
          >
            <IconLogout />
            <span>Cerrar sesión</span>
          </button>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
@media (max-width: 900px) {
  button[aria-label="Abrir menú"] {
    display: inline-flex !important;
  }
}
</style>