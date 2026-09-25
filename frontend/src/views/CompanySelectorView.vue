<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore, type CompanyOption } from "../stores/session";
import { useToastStore } from "../stores/toasts";
import VogelLogo from "../components/VogelLogo.vue";

const session = useSessionStore();
const router = useRouter();
const toasts = useToastStore();

const companies = ref<CompanyOption[]>([]);
const loading = ref(false);
const selectingId = ref<number | null>(null);

async function load() {
  loading.value = true;
  try {
    companies.value = await session.loadCompanies();
  } finally {
    loading.value = false;
  }
}

async function pick(company: CompanyOption) {
  selectingId.value = company.id;
  try {
    await session.selectCompany(company);
    router.push({ name: "dashboard" });
  } catch (err: unknown) {
    toasts.push("No se pudo entrar a la empresa", "error");
    selectingId.value = null;
  }
}

onMounted(() => {
  if (!session.me) {
    router.replace({ name: "login" });
    return;
  }
  load();
});
</script>

<template>
  <div class="auth-shell" style="grid-template-columns:1fr">
    <section class="auth-shell__form">
      <div class="auth-card" style="max-width:720px;width:100%">
        <div class="auth-card__brand">
          <VogelLogo :size="44" />
          <div>
            <strong style="font-size:14px;letter-spacing:0.18em;text-transform:uppercase">Vogel Consultoría</strong>
            <div class="text-muted" style="font-size:12px">Seleccioná la empresa</div>
          </div>
        </div>
        <h2 style="font-size:22px;margin:0 0 6px">Elegí una empresa</h2>
        <p class="text-secondary" style="font-size:14px;margin:0 0 18px">
          {{ session.isSuperAdmin
            ? "Pertenecés a múltiples empresas o administrás la plataforma. Elegí el contexto con el que querés operar."
            : "Tenés más de una empresa asociada. Elegí con cuál querés continuar." }}
        </p>

        <div v-if="loading" class="empty-state">
          <span class="spinner" /> Cargando…
        </div>

        <div v-else class="card-grid">
          <button
            v-for="company in companies"
            :key="company.id"
            class="card"
            :disabled="!company.active || selectingId === company.id"
            type="button"
            style="text-align:left;cursor:pointer;transition:transform 0.18s ease, border 0.18s ease"
            @click="pick(company)"
          >
            <div class="flex flex--between" style="align-items:flex-start">
              <div>
                <strong style="font-size:16px">{{ company.name }}</strong>
                <div class="text-muted" style="font-size:12px">{{ company.slug || '—' }}</div>
              </div>
              <span v-if="company.is_admin" class="role-chip">Admin</span>
              <span v-else class="badge badge--muted">Miembro</span>
            </div>
            <div style="margin-top:14px;display:flex;gap:8px;align-items:center">
              <span :class="['badge', company.active ? 'badge--success' : 'badge--muted']">
                {{ company.active ? "Activa" : "Inactiva" }}
              </span>
              <span v-if="selectingId === company.id" class="spinner" />
              <span v-else class="text-muted" style="font-size:12px">Entrar →</span>
            </div>
          </button>
        </div>

        <div
          v-if="!loading && companies.length === 0"
          class="empty-state"
        >
          No tenés empresas asociadas todavía.
        </div>
      </div>
    </section>
  </div>
</template>