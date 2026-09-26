<script setup lang="ts">
import {onMounted,ref} from "vue";
import {apiGet,apiPatch,apiPost,getApiErrorMessage} from "../lib/api";
import {useSessionStore} from "../stores/session";
import {useThemeStore} from "../stores/theme";
import {useToastStore} from "../stores/toasts";

interface CompanyParameter{parameter:string;value:string|number|boolean;default_value:string|number|boolean;is_overridden:boolean;description:string;data_type:string;category:string;editable:boolean}
interface OtStatus{id:number;name:string;color:string;sort_order:number;active:boolean;is_initial:boolean;is_final:boolean;marks_completed:boolean;marks_delivered:boolean}
const session=useSessionStore(),theme=useThemeStore(),toast=useToastStore();
const statuses=ref<OtStatus[]>([]),loadingStatuses=ref(false),showNewStatus=ref(false);
const parameters=ref<CompanyParameter[]>([]),loadingParameters=ref(false);
const newStatus=ref({name:"",color:"#3B82F6",sort_order:90,active:true,is_initial:false,is_final:false,marks_completed:false,marks_delivered:false});
async function loadParameters(){if(!session.activeCompany)return;loadingParameters.value=true;try{parameters.value=await apiGet<CompanyParameter[]>("/company-parameters")}catch(e){toast.push(getApiErrorMessage(e),"error")}finally{loadingParameters.value=false}}
async function saveParameter(p:CompanyParameter){try{await apiPatch("/company-parameters/"+p.parameter,{value:p.value});toast.push("Personalización guardada","success")}catch(e){toast.push(getApiErrorMessage(e),"error");await loadParameters()}}
async function loadStatuses(){if(!session.activeCompany)return;loadingStatuses.value=true;try{statuses.value=await apiGet<OtStatus[]>("/work-orders/statuses")}catch(e){toast.push(getApiErrorMessage(e),"error")}finally{loadingStatuses.value=false}}
async function saveStatus(st:OtStatus){try{await apiPatch("/work-orders/statuses/"+st.id,st);await loadStatuses();toast.push("Estado guardado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function createStatus(){try{await apiPost("/work-orders/statuses",newStatus.value);showNewStatus.value=false;newStatus.value={name:"",color:"#3B82F6",sort_order:90,active:true,is_initial:false,is_final:false,marks_completed:false,marks_delivered:false};await loadStatuses();toast.push("Estado creado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
onMounted(()=>{loadStatuses();loadParameters()});
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
    <div class="settings-heading"><h2>Personalización de la empresa</h2><p class="text-secondary">Define cómo trabaja {{session.activeCompany.name}}. Estas opciones simplifican o amplían el circuito sin borrar información histórica.</p></div>
    <div v-if="loadingParameters" class="text-muted">Cargando personalización…</div>
    <div v-else class="parameter-grid">
      <div v-for="p in parameters" :key="p.parameter" class="parameter-card">
        <div class="parameter-card__copy"><strong>{{p.description}}</strong><small>{{p.category}} · {{p.parameter}} <span v-if="p.is_overridden">· personalizado</span><span v-else>· valor general</span></small></div>
        <label v-if="p.data_type==='bool'" class="switch"><input v-model="p.value" type="checkbox" :disabled="!p.editable" @change="saveParameter(p)"><span></span></label>
        <div v-else class="parameter-value"><input v-model="p.value" :type="p.data_type==='decimal'||p.data_type==='integer'?'number':'text'" :step="p.data_type==='decimal'?'0.01':undefined" :disabled="!p.editable"><button class="btn btn--ghost btn--sm" @click="saveParameter(p)">Guardar</button></div>
      </div>
    </div>
  </div>

  <div v-if="session.activeCompany" class="card">
    <div class="flex flex--between settings-heading"><div><h2>Estados de órdenes de trabajo</h2><p class="text-secondary">Configuración propia de {{session.activeCompany.name}}. Estos estados se usan en todo el circuito de las OT.</p></div><button class="btn btn--primary" @click="showNewStatus=true">+ Nuevo estado</button></div>
    <div v-if="loadingStatuses" class="text-muted">Cargando estados…</div>
    <div v-else class="status-admin">
      <div v-for="st in statuses" :key="st.id" class="status-admin__row" :style="{'--status-color':st.color,background:st.color+'16',borderColor:st.color+'55'}">
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
.settings-stack{display:flex;flex-direction:column;gap:24px}.parameter-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:18px}.parameter-card{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px;border:1px solid rgba(148,163,184,.14);border-radius:12px;background:rgba(148,163,184,.04)}.parameter-card__copy{display:flex;flex-direction:column;gap:5px}.parameter-card__copy small{color:var(--text-muted,#94a3b8)}.parameter-value{display:flex;gap:8px;align-items:center}.parameter-value input{max-width:110px}.switch input{position:absolute;opacity:0}.switch span{display:block;width:46px;height:26px;border-radius:999px;background:rgba(148,163,184,.35);position:relative;cursor:pointer}.switch span:after{content:"";position:absolute;width:20px;height:20px;left:3px;top:3px;border-radius:50%;background:white;transition:.15s}.switch input:checked+span{background:#3b82f6}.switch input:checked+span:after{transform:translateX(20px)}@media(max-width:800px){.parameter-grid{grid-template-columns:1fr}.parameter-card{align-items:flex-start;flex-direction:column}.parameter-value{width:100%}.parameter-value input{max-width:none;flex:1}}.settings-heading{align-items:flex-start;gap:16px}.settings-heading h2{margin:0 0 6px;font-size:20px}.status-admin{display:flex;flex-direction:column;margin-top:18px}.status-admin__row{display:grid;grid-template-columns:52px minmax(150px,1fr) 80px repeat(4,auto) auto;align-items:end;gap:12px;margin:6px 0;padding:12px;border:1px solid;border-left:4px solid var(--status-color);border-radius:12px;transition:background .15s ease,border-color .15s ease}.color-input{width:44px;height:40px;padding:2px;border-radius:9px;cursor:pointer}.color-input--large{width:72px}.status-name,.order-field{margin:0}.check{display:flex;align-items:center;gap:6px;min-height:40px;white-space:nowrap;font-size:13px}.semantics-note{margin:16px 0 0}.modal-backdrop{position:fixed;inset:0;z-index:140;background:rgba(2,6,23,.72);display:grid;place-items:center;padding:20px}.status-modal{width:min(620px,100%)}.flags{display:flex;gap:18px;flex-wrap:wrap;margin-top:12px}@media(max-width:1000px){.status-admin__row{grid-template-columns:52px 1fr 80px;align-items:center}.status-admin__row .check,.status-admin__row .btn{grid-column:2/4}.settings-heading{flex-direction:column}}@media(max-width:600px){.status-admin__row{grid-template-columns:48px 1fr}.order-field{grid-column:2}.status-admin__row .check,.status-admin__row .btn{grid-column:1/3}.field__row{grid-template-columns:1fr}}
</style>