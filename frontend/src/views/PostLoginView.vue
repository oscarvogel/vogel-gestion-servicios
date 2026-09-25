<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
const router = useRouter();

onMounted(async () => {
  if (!session.me) {
    router.replace({ name: "login" });
    return;
  }
  if (session.isSuperAdmin) {
    router.replace({ name: "dashboard" });
    return;
  }
  if (session.activeCompany) {
    router.replace({ name: "dashboard" });
    return;
  }
  if (session.memberships.length === 0) {
    router.replace({ name: "dashboard" });
    return;
  }
  if (session.memberships.length === 1) {
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
  <div class="auth-shell" style="grid-template-columns:1fr">
    <section class="auth-shell__form">
      <div class="auth-card" style="text-align:center">
        <span class="spinner" />
        <p style="margin-top:14px">Cargando tu espacio…</p>
      </div>
    </section>
  </div>
</template>