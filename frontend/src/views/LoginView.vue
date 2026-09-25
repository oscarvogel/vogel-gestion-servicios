<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";
import VogelLogo from "../components/VogelLogo.vue";

const email = ref("");
const password = ref("");
const loading = ref(false);
const error = ref<string | null>(null);

const session = useSessionStore();
const router = useRouter();
const toasts = useToastStore();

async function onSubmit() {
  if (!email.value || !password.value) {
    error.value = "Ingresá email y contraseña";
    return;
  }
  error.value = null;
  loading.value = true;
  try {
    await session.login(email.value, password.value);
    toasts.push("Bienvenido/a", "success");
    router.push({ name: "post-login" });
  } catch (err: unknown) {
    const detail =
      (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail || "Credenciales inválidas";
    error.value = detail;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="auth-shell">
    <aside
      class="auth-shell__hero"
      :style="{
          backgroundImage:
            'linear-gradient(135deg, rgba(11,23,48,0.7), rgba(11,23,48,0.45)), url(\'https://images.unsplash.com/photo-1581090700227-1e37b190418e?auto=format&fit=crop&w=1200&q=80\')',
        }"
    >
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:48px">
        <VogelLogo :size="48" />
        <div>
          <strong style="font-size:14px;letter-spacing:0.18em;text-transform:uppercase">Vogel Consultoría</strong>
          <div style="font-size:12px;color:var(--color-text-muted)">Gestión de Servicios</div>
        </div>
      </div>
      <h1 style="font-size:38px;letter-spacing:-0.02em;line-height:1.1;max-width:520px">
        La plataforma operativa de tus servicios técnicos.
      </h1>
      <p style="margin-top:18px;color:var(--color-text-secondary);font-size:16px;max-width:520px">
        Administrá empresas, usuarios, equipos y órdenes de trabajo con un diseño claro, seguro y pensado para equipos distribuidos.
      </p>
      <div style="margin-top:48px;display:flex;gap:16px;flex-wrap:wrap">
        <span class="topbar__chip">Multi-tenant</span>
        <span class="topbar__chip">SSO-ready</span>
        <span class="topbar__chip">Roles y permisos granulares</span>
      </div>
    </aside>
    <section class="auth-shell__form">
      <div class="auth-card">
        <div class="auth-card__brand">
          <VogelLogo :size="44" />
          <div>
            <strong style="font-size:14px;letter-spacing:0.18em;text-transform:uppercase">Vogel Consultoría</strong>
            <div style="font-size:12px;color:var(--color-text-muted)">Vogel Gestión de Servicios</div>
          </div>
        </div>
        <h2 style="font-size:22px;margin:0 0 6px">Iniciar sesión</h2>
        <p class="text-secondary" style="font-size:14px;margin:0 0 24px">
          Ingresá tus credenciales para acceder a la plataforma.
        </p>
        <form @submit.prevent="onSubmit" novalidate>
          <div class="field">
            <label for="email">Email</label>
            <input
              id="email"
              v-model="email"
              type="email"
              autocomplete="username"
              placeholder="ej: vos@empresa.com"
              required
            />
          </div>
          <div class="field">
            <label for="password">Contraseña</label>
            <input
              id="password"
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="••••••••"
              required
            />
          </div>
          <div v-if="error" class="badge badge--danger" style="margin-bottom:14px;display:block">
            {{ error }}
          </div>
          <button class="btn btn--primary" type="submit" :disabled="loading" style="width:100%;justify-content:center">
            <span v-if="loading" class="spinner" />
            <span>{{ loading ? "Ingresando…" : "Ingresar" }}</span>
          </button>
        </form>
      </div>
    </section>
  </div>
</template>