<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
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
const menuRoot = ref<HTMLElement | null>(null);

const subtitle = computed(() => {
  if (session.isSuperAdmin && !session.activeCompany) return "Modo plataforma";
  if (session.activeCompany) return session.activeCompany.name;
  return "Sesión activa";
});
const roleLabel = computed(() => session.isSuperAdmin ? "SuperAdmin" : "Usuario");

function closeMenu() { menuOpen.value = false; }
function onDocumentClick(event: MouseEvent) {
  if (menuOpen.value && menuRoot.value && !menuRoot.value.contains(event.target as Node)) closeMenu();
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") closeMenu();
}
onMounted(() => {
  document.addEventListener("click", onDocumentClick);
  document.addEventListener("keydown", onKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onDocumentClick);
  document.removeEventListener("keydown", onKeydown);
});

async function logout() {
  closeMenu();
  await session.logout();
  router.push({ name: "login" });
}
async function goToCompanySelector() {
  if (session.isSuperAdmin && session.activeCompany) await session.leaveCompany();
  router.push({ name: "company-selector" });
}
</script>

<template>
  <header class="topbar">
    <div class="topbar__heading">
      <button class="btn btn--ghost btn--sm topbar__mobile-menu" type="button"
        @click="emit('toggle-menu')" aria-label="Abrir menú"><IconMenu /></button>
      <div>
        <div class="topbar__title">{{ title }}</div>
        <div class="text-muted topbar__subtitle">{{ subtitle }}</div>
      </div>
    </div>

    <div class="topbar__right">
      <button v-if="session.activeCompany" class="topbar__company" type="button"
        @click="goToCompanySelector" title="Cambiar empresa">
        <strong>{{ session.activeCompany.name }}</strong><span>Cambiar</span>
      </button>

      <button class="btn btn--ghost btn--sm topbar__theme" type="button" @click="theme.toggle"
        :aria-label="theme.theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'">
        <IconMoon v-if="theme.theme === 'dark'" /><IconSun v-else />
        <span>{{ theme.theme === 'dark' ? 'Oscuro' : 'Claro' }}</span>
      </button>

      <div ref="menuRoot" class="topbar__user">
        <button class="topbar__identity" type="button" @click="menuOpen = !menuOpen"
          aria-haspopup="menu" :aria-expanded="menuOpen">
          <span class="topbar__identity-copy">
            <strong>{{ session.me?.full_name }}</strong>
            <small>{{ roleLabel }}</small>
          </span>
          <span class="topbar__avatar">{{ session.me?.full_name?.slice(0, 1)?.toUpperCase() ?? "?" }}</span>
        </button>
        <div v-if="menuOpen" class="topbar__menu" role="menu">
          <div class="topbar__menu-profile">
            <strong>{{ session.me?.full_name }}</strong>
            <span>{{ session.me?.email }}</span>
            <small>{{ roleLabel }} · {{ session.activeCompany?.name || "Modo plataforma" }}</small>
          </div>
          <div class="topbar__menu-separator" />
          <button class="topbar__menu-action" type="button" role="menuitem" @click="logout">
            <IconLogout class="topbar__menu-icon" /><span>Cerrar sesión</span>
          </button>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.topbar__heading{display:flex;gap:12px;align-items:center;min-width:0}
.topbar__subtitle{font-size:12px}
.topbar__mobile-menu{display:none}
.topbar__right{display:flex;align-items:center;gap:8px;min-width:0}
.topbar__company,.topbar__identity{border:1px solid var(--color-border);background:var(--color-surface);color:var(--color-text);border-radius:12px;cursor:pointer}
.topbar__company{display:flex;gap:8px;align-items:center;padding:8px 11px}
.topbar__company span{font-size:11px;color:var(--color-text-muted)}
.topbar__user{position:relative}
.topbar__identity{display:flex;align-items:center;gap:9px;padding:5px 6px 5px 11px}
.topbar__identity-copy{display:flex;flex-direction:column;align-items:flex-end;line-height:1.15}
.topbar__identity-copy strong{font-size:12px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.topbar__identity-copy small{font-size:10px;color:var(--color-text-muted)}
.topbar__avatar{display:grid;place-items:center;width:31px;height:31px;border-radius:50%;background:var(--color-primary);color:white;font-weight:700}
.topbar__identity:focus-visible,.topbar__company:focus-visible,.topbar__menu-action:focus-visible{outline:2px solid var(--color-primary);outline-offset:2px}
.topbar__menu{position:absolute;right:0;top:calc(100% + 9px);width:min(300px,calc(100vw - 24px));padding:8px;background:#10283f;border:1px solid rgba(125,170,210,.28);border-radius:14px;box-shadow:0 18px 50px rgba(0,0,0,.48);z-index:1000;isolation:isolate}
.topbar__menu-profile{display:flex;flex-direction:column;gap:3px;padding:10px 11px}
.topbar__menu-profile strong{font-size:14px;color:var(--color-text)}
.topbar__menu-profile span{font-size:12px;color:var(--color-text-secondary);overflow-wrap:anywhere}
.topbar__menu-profile small{font-size:11px;color:var(--color-text-muted)}
.topbar__menu-separator{height:1px;background:var(--color-border);margin:3px 0}
.topbar__menu-action{display:flex;align-items:center;gap:9px;width:100%;padding:10px 11px;border:0;border-radius:9px;background:transparent;color:var(--color-text);cursor:pointer;text-align:left}
.topbar__menu-action:hover{background:var(--color-surface-hover)}
.topbar__menu-action :deep(svg){display:block;width:18px!important;height:18px!important;min-width:18px!important;max-width:18px!important;flex:0 0 18px!important}
.topbar__menu-icon{display:block;width:18px!important;height:18px!important;min-width:18px!important;max-width:18px!important;flex:0 0 18px!important}
@media(max-width:900px){.topbar__mobile-menu{display:inline-flex}.topbar__identity-copy,.topbar__theme span{display:none}.topbar__company span{display:none}}
@media(max-width:600px){
.topbar{padding:0 12px;min-height:62px}
.topbar__heading{gap:8px;flex:1}
.topbar__mobile-menu{display:none}
.topbar__title{font-size:15px}
.topbar__subtitle{font-size:10px;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.topbar__company{display:none}
.topbar__theme{display:none}
.topbar__right{gap:4px}
.topbar__identity{border:0;background:transparent;padding:4px}
.topbar__avatar{width:36px;height:36px}
}
</style>
