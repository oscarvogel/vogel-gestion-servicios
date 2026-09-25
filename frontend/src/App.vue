<script setup lang="ts">
import { useSessionStore } from "./stores/session";
import ToastStack from "./components/ToastStack.vue";

const session = useSessionStore();
</script>

<template>
  <div v-if="session.authStatus === 'initializing'" class="auth-shell" style="grid-template-columns:1fr">
    <section class="auth-shell__form">
      <div class="auth-card" style="text-align:center">
        <div class="auth-card__brand" style="justify-content:center">
          <strong style="font-size:14px;letter-spacing:0.18em;text-transform:uppercase">Vogel Consultoría</strong>
        </div>
        <span class="spinner" aria-label="Cargando sesión" />
        <p class="text-secondary" style="margin-top:14px">Verificando tu sesión…</p>
      </div>
    </section>
  </div>
  <router-view v-else />
  <ToastStack />
</template>
