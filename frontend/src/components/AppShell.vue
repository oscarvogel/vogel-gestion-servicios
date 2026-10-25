<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import { pageEnter, pageLeave } from "../lib/motion";
import Sidebar from "./Sidebar.vue";
import Topbar from "./Topbar.vue";
import MobileBottomNav from "./MobileBottomNav.vue";

const menuOpen = ref(false);

// Ir a una seccion de mas abajo en el menu hace que la pagina entre subiendo; ir hacia
// arriba, bajando. Se calcula antes del render, cuando cambia la ruta.
const route = useRoute();
const direction = ref(0);
watch(
  () => route.meta.order,
  (next, prev) => {
    direction.value = next === undefined || prev === undefined || next === prev ? 0 : next > prev ? 1 : -1;
  },
);
const onLeave = (el: Element, done: () => void) => pageLeave(el, direction.value, done);
const onEnter = (el: Element, done: () => void) => pageEnter(el, direction.value, done);

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
      <Topbar @toggle-menu="menuOpen = !menuOpen" />
      <main class="app-content">
        <!-- La vista va envuelta para que la transicion tenga un unico nodo aunque la vista
             tenga varias raices; el envoltorio hereda el gap para no cambiar el espaciado. -->
        <router-view v-slot="{ Component, route: current }">
          <Transition :css="false" mode="out-in" @leave="onLeave" @enter="onEnter">
            <div :key="current.path" class="page-transition">
              <component :is="Component" />
            </div>
          </Transition>
        </router-view>
      </main>
      <MobileBottomNav @more="menuOpen = true" />
    </div>
  </div>
</template>
