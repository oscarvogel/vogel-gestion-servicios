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
    <aside class="auth-shell__hero auth-shell__hero--branding">
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
        <h2 class="auth-card__title">Iniciar sesión</h2>
        <p class="text-secondary auth-card__subtitle">
          Ingresá tus credenciales para acceder a la plataforma.
        </p>
        <form @submit.prevent="onSubmit" novalidate>
          <div class="field">
            <label for="email">Email</label>
            <input id="email" v-model="email" type="email" autocomplete="username" placeholder="ej: vos@empresa.com" required />
          </div>
          <div class="field">
            <label for="password">Contraseña</label>
            <div class="auth-password">
              <input id="password" v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" placeholder="••••••••" required />
              <button type="button" class="btn btn--ghost auth-password__toggle" :aria-label="showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'" @click="showPassword = !showPassword">
                {{ showPassword ? "Ocultar" : "Mostrar" }}
              </button>
            </div>
          </div>
          <div v-if="error" class="badge badge--danger auth-card__error">{{ error }}</div>
          <button class="btn btn--primary auth-card__submit" type="submit" :disabled="loading">
            <span v-if="loading" class="spinner" />
            <span>{{ loading ? "Ingresando…" : "Ingresar" }}</span>
          </button>
        </form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.auth-card__title{font-size:22px;margin:0 0 6px}
.auth-card__subtitle{font-size:14px;margin:0 0 24px}
.auth-password{display:flex;gap:8px;align-items:center}
.auth-password input{flex:1;min-width:0}
.auth-password__toggle{flex:0 0 auto}
.auth-card__error{margin-bottom:14px;display:block}
.auth-card__submit{width:100%;justify-content:center}
@media(max-width:700px){
  .auth-shell{min-height:100dvh}
  .auth-shell__form{display:flex;align-items:flex-start;justify-content:center;padding:clamp(28px,8vh,68px) 16px 24px}
  .auth-card{width:100%;max-width:430px;padding:22px 18px 20px;border-radius:20px}
  .auth-card__brand{margin-bottom:16px}
  .auth-card__title{font-size:24px}
  .auth-card__subtitle{margin-bottom:20px;line-height:1.4}
  .auth-password{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}
  .auth-password__toggle{min-width:78px;padding-inline:12px}
}
@media(max-width:380px){
  .auth-shell__form{padding:20px 10px}
  .auth-card{padding:18px 14px}
  .auth-password{grid-template-columns:1fr}
  .auth-password__toggle{width:100%}
}
</style>
