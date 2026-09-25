<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";
import VogelLogo from "../components/VogelLogo.vue";

const email = ref("");
const password = ref("");
const showPassword = ref(false);
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
        <VogelLogo :size="78" />
      </div>
      <h1 style="font-size:38px;letter-spacing:-0.02em;line-height:1.1;max-width:520px">
        La plataforma operativa de tus servicios técnicos.
      </h1>
      <p style="margin-top:18px;color:var(--color-text-secondary);font-size:16px;max-width:520px">
        Administrá empresas, usuarios, equipos y órdenes de trabajo con un diseño claro, seguro y pensado para equipos distribuidos.
      </p>
      <p style="margin-top:36px;color:var(--color-text-muted);font-size:13px">
        Una plataforma de Vogel Consultoría.
      </p>
    </aside>
    <section class="auth-shell__form">
      <div class="auth-card">
        <div class="auth-card__brand">
          <VogelLogo :size="64" />
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
            <div style="display:flex;gap:8px;align-items:center">
              <input
                id="password"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="••••••••"
                required
                style="flex:1"
              />
              <button
                type="button"
                class="btn btn--ghost"
                :aria-label="showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'"
                @click="showPassword = !showPassword"
              >
                {{ showPassword ? "Ocultar" : "Mostrar" }}
              </button>
            </div>
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
