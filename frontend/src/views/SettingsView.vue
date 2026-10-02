<script setup lang="ts">

import {onMounted,ref} from "vue";
import {useSessionStore} from "../stores/session";
import {useThemeStore} from "../stores/theme";
import {useToastStore} from "../stores/toasts";
import {apiGet,apiPatch,getApiErrorMessage} from "../lib/api";

const session=useSessionStore(),theme=useThemeStore(),toast=useToastStore();
const notif=ref({whatsapp_instance_id:"",notification_sender_name:"",notification_sender_email:"",whatsapp_api_key:"",whatsapp_api_key_configured:false,whatsapp_use_platform_key:false});
const canManage=session.hasPermission("work_orders.manage");
async function loadNotif(){try{notif.value=await apiGet("/work-orders/notification-settings")}catch(_){}}
async function saveNotif(){try{const payload={...notif.value};const key=payload.whatsapp_api_key;delete payload.whatsapp_api_key_configured;if(!key?.trim()){delete payload.whatsapp_api_key}notif.value=await apiPatch("/work-orders/notification-settings",payload);notif.value.whatsapp_api_key="";toast.push("Configuracion de avisos guardada","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
onMounted(async()=>{if(canManage)await loadNotif()});
</script>

<template>
<div class="settings-stack">
  <div v-if="canManage" class="card" style="margin-bottom:16px">
    <h2 style="margin:0 0 6px;font-size:20px">Avisos al cliente</h2>
    <p class="text-secondary">Que instancia de WhatsApp y que remitente usa esta empresa. La API key y el SMTP son de la plataforma: no se guardan credenciales por empresa.</p>
    <div class="field" style="margin-top:14px"><label>Instancia de WhatsApp</label><input v-model="notif.whatsapp_instance_id" placeholder="ej: ceramica"></div>
    <div class="field"><label>Nombre del remitente</label><input v-model="notif.notification_sender_name" placeholder="Vogel Consultoria"></div>
    <div class="field"><label>Email del remitente</label><input v-model="notif.notification_sender_email" type="email" placeholder="taller@empresa.com"></div>
    <div class="field"><label>API key de la gateway de WhatsApp</label>
      <input v-model="notif.whatsapp_api_key" type="password" autocomplete="new-password" :placeholder="notif.whatsapp_api_key_configured ? 'Cargada. Escribí para reemplazarla.' : 'No cargada'">
      <small class="text-muted">Se guarda cifrada y no se vuelve a mostrar. Es la key de SU empresa: sus clientes reciben los avisos desde su numero.</small></div>
    <label class="check" style="margin:10px 0 4px"><input v-model="notif.whatsapp_use_platform_key" type="checkbox"> Usar la linea y la key de Vogel en vez de las propias</label>
    <small v-if="notif.whatsapp_api_key" class="text-muted">Guardando: la key nueva va a reemplazar la anterior.</small>
    <button class="btn btn--primary" style="margin-top:10px" @click="saveNotif">Guardar</button>
  </div>
  <div class="card">
    <h2 style="margin:0 0 6px;font-size:20px">Apariencia</h2>
    <p class="text-secondary">Tema por defecto: oscuro. Persistido en este navegador.</p>
    <div class="flex gap-12" style="margin-top:14px">
      <button :class="['btn',{'btn--primary':theme.theme==='dark','btn--ghost':theme.theme!=='dark'}]" type="button" @click="theme.set('dark')">Oscuro</button>
      <button :class="['btn',{'btn--primary':theme.theme==='light','btn--ghost':theme.theme!=='light'}]" type="button" @click="theme.set('light')">Claro</button>
    </div>
  </div>

  <div class="card">
    <h2 style="margin:0 0 6px;font-size:20px">Cuenta</h2>
    <p class="text-secondary">Sesión activa y permisos.</p>
    <table class="table" style="margin-top:14px"><tbody>
      <tr><th>Usuario</th><td>{{session.me?.full_name}} <span class="text-muted">({{session.me?.email}})</span></td></tr>
      <tr><th>Rol plataforma</th><td><span v-if="session.isSuperAdmin" class="role-chip">SuperAdmin Vogel</span><span v-else class="badge badge--muted">Empresa</span></td></tr>
      <tr><th>Empresa activa</th><td>{{session.activeCompany?.name||'— (modo plataforma)'}}</td></tr>
      <tr><th>Permisos efectivos</th><td><div class="flex gap-8" style="flex-wrap:wrap"><span v-for="p in session.permissions.slice(0,12)" :key="p" class="role-chip">{{p}}</span><span v-if="session.permissions.length>12" class="text-muted">+{{session.permissions.length-12}}</span></div></td></tr>
    </tbody></table>
  </div>
</div>
</template>

<style scoped>.settings-stack{display:flex;flex-direction:column;gap:24px}</style>