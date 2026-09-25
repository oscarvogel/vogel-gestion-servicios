<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { resolvePostLoginDestination, useSessionStore } from "../stores/session";

const session = useSessionStore();
const router = useRouter();
const noCompanies = ref(false);

onMounted(async () => {
  if (!session.me) {
    router.replace({ name: "login" });
    return;
  }
  const destination = resolvePostLoginDestination(session.me, session.activeCompany);
  if (destination === "dashboard") {
    router.replace({ name: "dashboard" });
    return;
  }
  if (destination === "no-companies") {
    noCompanies.value = true;
    return;
  }
  if (destination === "select-company") {
    try {
      await session.selectCompany({
        id: session.memberships[0].company_id,
        name: session.memberships[0].company_name,
        slug: session.memberships[0].company_slug,
        active: session.memberships[0].company_active,
        is_admin: session.memberships[0].is_admin,
      });
      router.replace({ name: "dashboard" });
    } catch (err) {
      router.replace({ name: "company-selector" });
    }
    return;
  }
  router.replace({ name: "company-selector" });
});
</script>

<template>
  <div v-if="noCompanies" class="auth-shell" style="grid-template-columns:1fr">
    <section class="auth-shell__form">
      <div class="auth-card" style="text-align:center">
        <h2>Sin empresas asignadas</h2>
        <p class="text-secondary">Tu usuario todavía no tiene empresas disponibles para operar.</p>
        <button class="btn btn--primary" type="button" @click="session.logout().then(() => router.replace({ name: 'login' }))">
          Cerrar sesión
        </button>
      </div>
    </section>
  </div>
  <div v-else class="auth-shell" style="grid-template-columns:1fr">
    <section class="auth-shell__form">
      <div class="auth-card" style="text-align:center">
        <span class="spinner" />
        <p style="margin-top:14px">Cargando tu espacio…</p>
      </div>
    </section>
  </div>
</template>
