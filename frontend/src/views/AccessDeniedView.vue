<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<template>
  <main class="access-denied">
    <section class="access-denied__card">
      <p class="eyebrow">Vogel Consultoría</p>
      <h1>Acceso denegado</h1>
      <p>No tenés permisos para acceder a esta sección.</p>
      <button type="button" @click="router.replace({ name: 'dashboard' })">
        Volver al dashboard
      </button>
    </section>
  </main>
</template>
