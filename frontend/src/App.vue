<script setup lang="ts">
import { API_BASE_URL } from "./api";
</script>

<template>
  <main>
    <section>
      <small>Vogel Consultoría</small>
      <h1>Vogel Gestión de Servicios</h1>
      <p>Fundación multiempresa activa.</p>
      <p class="api">API base: {{ API_BASE_URL }}</p>
    </section>
  </main>
</template>

<style>
body{margin:0;font-family:Inter,system-ui;background:#f4f6fa;color:#172033}
main{min-height:100vh;display:grid;place-items:center;padding:24px}
section{background:#fff;padding:40px;border-radius:24px;box-shadow:0 20px 60px #17203320}
h1{font-size:clamp(36px,7vw,64px);margin:8px 0}
.api{color:#5d6b82;font-family:ui-monospace,monospace}
</style>
