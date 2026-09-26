<script setup lang="ts">
import {onMounted,ref} from "vue";
import {apiGet,apiPatch,apiPost,getApiErrorMessage} from "../lib/api";
import {useSessionStore} from "../stores/session";
import {useThemeStore} from "../stores/theme";
import {useToastStore} from "../stores/toasts";

interface OtStatus{id:number;name:string;color:string;sort_order:number;active:boolean;is_initial:boolean;is_final:boolean;marks_completed:boolean;marks_delivered:boolean}
const session=useSessionStore(),theme=useThemeStore(),toast=useToastStore();
const statuses=ref<OtStatus[]>([]),loadingStatuses=ref(false),showNewStatus=ref(false);
const newStatus=ref({name:"",color:"#3B82F6",sort_order:90,active:true,is_initial:false,is_final:false,marks_completed:false,marks_delivered:false});
async function loadStatuses(){if(!session.activeCompany)return;loadingStatuses.value=true;try{statuses.value=await apiGet<OtStatus[]>("/work-orders/statuses")}catch(e){toast.push(getApiErrorMessage(e),"error")}finally{loadingStatuses.value=false}}
async function saveStatus(st:OtStatus){try{await apiPatch("/work-orders/statuses/"+st.id,st);await loadStatuses();toast.push("Estado guardado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function createStatus(){try{await apiPost("/work-orders/statuses",newStatus.value);showNewStatus.value=false;newStatus.value={name:"",color:"#3B82F6",sort_order:90,active:true,is_initial:false,is_final:false,marks_completed:false,marks_delivered:false};await loadStatuses();toast.push("Estado creado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
onMounted(loadStatuses);
</script>

<template>
<div class="settings-stack">
  <div class="card">
    <h2 style="margin:0 0 6px;font-size:20px">Apariencia</h2>
    <p class="text-secondary">Tema por defecto: oscuro. Persistido en este navegador.</p>
    <div class="flex gap-12" style="margin-top:14px">
      <button :class="['btn',{'btn--primary':theme.theme==='dark','btn--ghost':theme.theme!=='dark'}]" type="button" @click="theme.set('dark')">Oscuro</button>
      <button :class="['btn',{'btn--primary':theme.theme==='light','btn--ghost':theme.theme!=='light'}]" type="button" @click="theme.set('light')">Claro</button>
    </div>
  </div>

  <div v-if="session.activeCompany" class="card">
    <div class="flex flex--between settings-heading"><div><h2>Estados de órdenes de trabajo</h2><p class="text-secondary">Configuración propia de {{session.activeCompany.name}}. Estos estados se usan en todo el circuito de las OT.</p></div><button class="btn btn--primary" @click="showNewStatus=true">+ Nuevo estado</button></div>
    <div v-if="loadingStatuses" class="text-muted">Cargando estados…</div>
    <div v-else class="status-admin">
      <div v-for="st in statuses" :key="st.id" class="status-admin__row">
        <input v-model="st.color" class="color-input" type="color" :aria-label="'Color de '+st.name">
        <div class="field status-name"><label>Nombre</label><input v-model="st.name"></div>
        <div class="field order-field"><label>Orden</label><input v-model.number="st.sort_order" type="number" min="0"></div>
        <label class="check"><input v-model="st.active" type="checkbox"> Activo</label>
        <label class="check"><input v-model="st.is_initial" type="checkbox"> Inicial</label>
        <label class="check"><input v-model="st.marks_completed" type="checkbox"> Finaliza trabajo</label>
        <label class="check"><input v-model="st.marks_delivered" type="checkbox"> Entrega equipo</label>
        <button class="btn btn--ghost btn--sm" @click="saveStatus(st)">Guardar</button>
      </div>
    </div>
    <p class="text-muted semantics-note">“Finaliza trabajo” registra la finalización técnica. “Entrega equipo” registra la entrega real al cliente. Son comportamientos del estado y no dependen de su nombre o color.</p>
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

<div v-if="showNewStatus" class="modal-backdrop"><div class="modal card status-modal">
  <div class="flex flex--between"><h2>Nuevo estado de OT</h2><button class="btn btn--ghost" @click="showNewStatus=false">×</button></div>
  <p class="text-secondary">Crealo desde administración. No aparecerá ninguna creación rápida dentro de una OT.</p>
  <div class="field"><label>Nombre *</label><input v-model="newStatus.name" autofocus></div>
  <div class="field__row"><div class="field"><label>Color</label><input v-model="newStatus.color" class="color-input color-input--large" type="color"></div><div class="field"><label>Orden</label><input v-model.number="newStatus.sort_order" type="number" min="0"></div></div>
  <div class="flags"><label class="check"><input v-model="newStatus.active" type="checkbox"> Activo</label><label class="check"><input v-model="newStatus.is_initial" type="checkbox"> Estado inicial</label><label class="check"><input v-model="newStatus.marks_completed" type="checkbox"> Finaliza trabajo</label><label class="check"><input v-model="newStatus.marks_delivered" type="checkbox"> Entrega equipo</label></div>
  <div class="flex flex--between" style="margin-top:20px"><button class="btn btn--ghost" @click="showNewStatus=false">Cancelar</button><button class="btn btn--primary" :disabled="!newStatus.name.trim()" @click="createStatus">Crear estado</button></div>
</div></div>
</template>

<style scoped>
.settings-stack{display:flex;flex-direction:column;gap:24px}.settings-heading{align-items:flex-start;gap:16px}.settings-heading h2{margin:0 0 6px;font-size:20px}.status-admin{display:flex;flex-direction:column;margin-top:18px}.status-admin__row{display:grid;grid-template-columns:52px minmax(150px,1fr) 80px repeat(4,auto) auto;align-items:end;gap:12px;padding:12px 0;border-bottom:1px solid rgba(148,163,184,.13)}.color-input{width:44px;height:40px;padding:2px;border-radius:9px;cursor:pointer}.color-input--large{width:72px}.status-name,.order-field{margin:0}.check{display:flex;align-items:center;gap:6px;min-height:40px;white-space:nowrap;font-size:13px}.semantics-note{margin:16px 0 0}.modal-backdrop{position:fixed;inset:0;z-index:140;background:rgba(2,6,23,.72);display:grid;place-items:center;padding:20px}.status-modal{width:min(620px,100%)}.flags{display:flex;gap:18px;flex-wrap:wrap;margin-top:12px}@media(max-width:1000px){.status-admin__row{grid-template-columns:52px 1fr 80px;align-items:center}.status-admin__row .check,.status-admin__row .btn{grid-column:2/4}.settings-heading{flex-direction:column}}@media(max-width:600px){.status-admin__row{grid-template-columns:48px 1fr}.order-field{grid-column:2}.status-admin__row .check,.status-admin__row .btn{grid-column:1/3}.field__row{grid-template-columns:1fr}}
</style>