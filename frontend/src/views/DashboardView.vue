<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useSessionStore } from "../stores/session";
import { apiGet } from "../lib/api";
import AppShell from "../components/AppShell.vue";
import { useToastStore } from "../stores/toasts";

interface SuperAdminDashboard {
  kpis: {
    total_companies: number;
    active_companies: number;
    total_users: number;
    active_users: number;
    total_admins: number;
    total_superadmins: number;
  };
  recent_companies: Array<{
    id: number;
    name: string;
    slug: string | null;
    active: boolean;
    created_at: string;
  }>;
  recent_activity: unknown[];
  quick_actions: Array<{ id: string; label: string; icon: string }>;
}

const session = useSessionStore();
const toasts = useToastStore();
const data = ref<SuperAdminDashboard | null>(null);
const loading = ref(false);

async function load() {
  if (!session.isSuperAdmin) return;
  loading.value = true;
  try {
    data.value = await apiGet<SuperAdminDashboard>("/dashboard/superadmin");
  } catch (err: unknown) {
    toasts.push("No se pudo cargar el dashboard", "error");
  } finally {
    loading.value = false;
  }
}

onMounted(load);

const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 12) return "Buenos días";
  if (hour < 19) return "Buenas tardes";
  return "Buenas noches";
});
</script>

<template>
  <AppShell>
    <section
      class="hero"
      :style="{
        backgroundImage:
          'linear-gradient(135deg, rgba(11,23,48,0.78), rgba(11,23,48,0.45)), url(https://images.unsplash.com/photo-1581090700227-1e37b190418e?auto=format&fit=crop&w=1200&q=80)',
      }"
    >
      <div class="hero__eyebrow">Plataforma Vogel</div>
      <h1 class="hero__title">{{ greeting }}, {{ session.me?.full_name?.split(' ')[0] }}.</h1>
      <p class="hero__subtitle">
        {{ session.isSuperAdmin
          ? "Operás como SuperAdmin. Gestioná empresas, asigná administradores y mantené la salud de la plataforma."
          : `Operás en el contexto de ${session.activeCompany?.name}.` }}
      </p>
    </section>

    <template v-if="session.isSuperAdmin">
      <div v-if="loading" class="card empty-state">
        <span class="spinner" /> Cargando métricas…
      </div>
      <template v-else-if="data">
        <div class="card-grid">
          <div class="card">
            <p class="card__title">Empresas totales</p>
            <div class="card__value">{{ data.kpis.total_companies }}</div>
            <p class="card__hint">{{ data.kpis.active_companies }} activas</p>
          </div>
          <div class="card">
            <p class="card__title">Usuarios</p>
            <div class="card__value">{{ data.kpis.total_users }}</div>
            <p class="card__hint">{{ data.kpis.active_users }} activos</p>
          </div>
          <div class="card">
            <p class="card__title">Administradores</p>
            <div class="card__value">{{ data.kpis.total_admins }}</div>
            <p class="card__hint">{{ data.kpis.total_superadmins }} superadmins</p>
          </div>
          <div class="card">
            <p class="card__title">Empresas activas</p>
            <div class="card__value">{{ data.kpis.active_companies }}</div>
            <p class="card__hint">Disponibles para operar</p>
          </div>
        </div>

        <div class="card">
          <p class="card__title">Empresas recientes</p>
          <table class="table">
            <thead>
              <tr>
                <th>Empresa</th>
                <th>Slug</th>
                <th>Estado</th>
                <th>Creada</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in data.recent_companies" :key="row.id">
                <td><strong>{{ row.name }}</strong></td>
                <td><code>{{ row.slug }}</code></td>
                <td>
                  <span :class="['badge', row.active ? 'badge--success' : 'badge--muted']">
                    {{ row.active ? 'Activa' : 'Inactiva' }}
                  </span>
                </td>
                <td class="text-muted">{{ new Date(row.created_at).toLocaleString('es-AR') }}</td>
              </tr>
              <tr v-if="data.recent_companies.length === 0">
                <td colspan="4" class="empty-state">Aún no hay empresas creadas.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card-grid">
          <div class="card" v-for="action in data.quick_actions" :key="action.id">
            <p class="card__title">{{ action.label }}</p>
            <p class="text-secondary" style="font-size:13px;margin:0">
              Disponible desde el menú lateral.
            </p>
          </div>
        </div>
      </template>
    </template>

    <template v-else>
      <div class="card">
        <p class="card__title">Empresa activa</p>
        <h2 style="margin:0 0 6px;font-size:22px">{{ session.activeCompany?.name }}</h2>
        <p class="text-secondary" style="margin:0">
          {{ session.activeCompany?.is_admin
            ? "Sos administrador de esta empresa. Gestioná usuarios y roles."
            : "Sos miembro. Tu administrador puede modificar tus permisos." }}
        </p>
      </div>
      <div class="card empty-state" v-if="!session.activeCompany">
        No hay empresa activa. Volvé al selector desde el topbar.
      </div>
    </template>
  </AppShell>
</template>