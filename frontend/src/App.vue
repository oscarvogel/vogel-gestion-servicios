<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { useSessionStore } from "./stores/session";
import ToastStack from "./components/ToastStack.vue";

const session = useSessionStore();

// Si verificar la sesion tarda, se avisa en vez de dejar la ruedita sola. No se corta la
// consulta: un error en el arranque se trata como sesion vencida y cerraria la sesion.
const SLOW_MS = 8000;
const slow = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => session.authStatus,
  (status) => {
    clearTimeout(timer);
    slow.value = false;
    if (status === "initializing") timer = setTimeout(() => (slow.value = true), SLOW_MS);
  },
  { immediate: true },
);
onBeforeUnmount(() => clearTimeout(timer));

function retry() {
  window.location.reload();
}
</script>

<template>
  <div v-if="session.authStatus === 'initializing'" class="auth-shell" style="grid-template-columns:1fr">
    <section class="auth-shell__form">
      <div class="auth-card" style="text-align:center" aria-live="polite">
        <div class="auth-card__brand" style="justify-content:center">
          <strong style="font-size:14px;letter-spacing:0.18em;text-transform:uppercase">Vogel Consultoría</strong>
        </div>
        <span class="spinner" aria-label="Cargando sesión" />
        <p class="text-secondary" style="margin-top:14px">Verificando tu sesión…</p>
        <template v-if="slow">
          <p class="text-muted" style="margin:10px 0 14px;font-size:13px">
            El servidor está tardando más de lo normal. Podés esperar o volver a intentar.
          </p>
          <button type="button" class="btn btn--ghost" @click="retry">Reintentar</button>
        </template>
      </div>
    </section>
  </div>
  <router-view v-else />
  <ToastStack />
</template>
