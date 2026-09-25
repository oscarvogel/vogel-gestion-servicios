<script setup lang="ts">
import AppShell from "../components/AppShell.vue";
import { useSessionStore } from "../stores/session";
import { useThemeStore } from "../stores/theme";

const session = useSessionStore();
const theme = useThemeStore();
</script>

<template>
  <AppShell>
    <div class="card">
      <h2 style="margin:0 0 6px;font-size:20px">Apariencia</h2>
      <p class="text-secondary">Tema por defecto: oscuro. Persistido en este navegador.</p>
      <div class="flex gap-12" style="margin-top:14px">
        <button
          :class="['btn', { 'btn--primary': theme.theme === 'dark', 'btn--ghost': theme.theme !== 'dark' }]"
          type="button"
          @click="theme.set('dark')"
        >Oscuro</button>
        <button
          :class="['btn', { 'btn--primary': theme.theme === 'light', 'btn--ghost': theme.theme !== 'light' }]"
          type="button"
          @click="theme.set('light')"
        >Claro</button>
      </div>
    </div>

    <div class="card">
      <h2 style="margin:0 0 6px;font-size:20px">Cuenta</h2>
      <p class="text-secondary">Sesión activa y permisos.</p>
      <table class="table" style="margin-top:14px">
        <tbody>
          <tr>
            <th>Usuario</th>
            <td>{{ session.me?.full_name }} <span class="text-muted">({{ session.me?.email }})</span></td>
          </tr>
          <tr>
            <th>Rol plataforma</th>
            <td>
              <span v-if="session.isSuperAdmin" class="role-chip">SuperAdmin Vogel</span>
              <span v-else class="badge badge--muted">Empresa</span>
            </td>
          </tr>
          <tr>
            <th>Empresa activa</th>
            <td>{{ session.activeCompany?.name || '— (modo plataforma)' }}</td>
          </tr>
          <tr>
            <th>Permisos efectivos</th>
            <td>
              <div class="flex gap-8" style="flex-wrap:wrap">
                <span v-for="p in session.permissions.slice(0,12)" :key="p" class="role-chip">{{ p }}</span>
                <span v-if="session.permissions.length > 12" class="text-muted">+{{ session.permissions.length - 12 }}</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2 style="margin:0 0 6px;font-size:20px">Próximos hitos</h2>
      <p class="text-secondary">
        Este módulo sienta las bases para Cliente/Equipo/Orden de Trabajo/Facturación.
        Mantenemos compatibilidades y no tocamos producción.
      </p>
    </div>
  </AppShell>
</template>