<script setup lang="ts">
import { onMounted, ref } from "vue";
import Modal from "../components/Modal.vue";
import { apiDelete, apiGet, apiPatch, apiPost, getApiErrorMessage } from "../lib/api";
import { useSessionStore } from "../stores/session";
import { useToastStore } from "../stores/toasts";

interface Customer { id:number; name:string; customer_type:"PERSON"|"COMPANY"; document:string|null; phone:string|null; whatsapp:string|null; email:string|null; address:string|null; notes:string|null; active:boolean }
interface EquipmentCategory { id:number; name:string; active:boolean }
interface Equipment { id:number; customer_id:number; category_id:number; category_name:string; brand:string|null; model:string|null; serial_number:string|null; description:string|null; notes:string|null; active:boolean }
const toast=useToastStore(),session=useSessionStore(); const items=ref<Customer[]>([]); const total=ref(0); const search=ref(""); const loading=ref(false);
const showCustomer=ref(false); const editing=ref<Customer|null>(null); const selected=ref<Customer|null>(null); const equipment=ref<Equipment[]>([]); const showEquipment=ref(false);
const form=ref({customer_type:"PERSON",name:"",document:"",phone:"",whatsapp:"",email:"",address:"",notes:""});
const eq=ref({category_id:0,brand:"",model:"",serial_number:"",description:"",notes:""});
const categoryQuery=ref(""); const categories=ref<EquipmentCategory[]>([]); const categoryOpen=ref(false);

async function load(){loading.value=true;try{const r=await apiGet<{items:Customer[];total:number}>("/customers",{params:{search:search.value||undefined,page_size:100}});items.value=r.items;total.value=r.total}catch(e){toast.push(getApiErrorMessage(e,"No se pudieron cargar los clientes"),"error")}finally{loading.value=false}}
function newCustomer(){editing.value=null;form.value={customer_type:"PERSON",name:"",document:"",phone:"",whatsapp:"",email:"",address:"",notes:""};showCustomer.value=true}
function editCustomer(c:Customer){editing.value=c;form.value={customer_type:c.customer_type,name:c.name,document:c.document||"",phone:c.phone||"",whatsapp:c.whatsapp||"",email:c.email||"",address:c.address||"",notes:c.notes||""};showCustomer.value=true}
async function saveCustomer(){try{const payload={...form.value,email:form.value.email||null,document:form.value.document||null,phone:form.value.phone||null,whatsapp:form.value.whatsapp||null,address:form.value.address||null,notes:form.value.notes||null};if(editing.value)await apiPatch("/customers/"+editing.value.id,payload);else await apiPost("/customers",payload);showCustomer.value=false;toast.push("Cliente guardado","success");await load()}catch(e){toast.push(getApiErrorMessage(e),"error")}}
interface EquipmentDocument{id:number;equipment_id:number;work_order_id:number|null;original_filename:string;mime_type:string;size_bytes:number;size_mb:number;description:string|null;uploaded_by_user_id:number;created_at:string;is_previewable:boolean}
const documents=ref<EquipmentDocument[]>([]),documentsFor=ref<number|null>(null),uploading=ref(false),uploadError=ref("");
const canManageEquipment=session.hasPermission("equipment.manage");
function formatBytes(n:number){return n<1048576?Math.max(1,Math.round(n/1024))+" KB":(n/1048576).toFixed(1)+" MB"}
function formatDocDate(v:string){const d=new Date(/[zZ]|[+-]\d\d:\d\d$/.test(v)?v:v+"Z");return Number.isNaN(d.getTime())?"—":d.toLocaleDateString("es-AR",{day:"2-digit",month:"2-digit",year:"2-digit"})}
async function loadDocuments(equipmentId:number){documentsFor.value=equipmentId;try{documents.value=(await apiGet<{items:EquipmentDocument[]}>(`/equipment/${equipmentId}/documents`)).items}catch(_){documents.value=[]}}
async function toggleDocuments(equipmentId:number){if(documentsFor.value===equipmentId){documentsFor.value=null;return}await loadDocuments(equipmentId)}
async function uploadDocument(equipmentId:number,event:Event){const input=event.target as HTMLInputElement;const file=input.files?.[0];if(!file)return
  uploading.value=true;uploadError.value=""
  try{const body=new FormData();body.append("file",file);await apiPost(`/equipment/${equipmentId}/documents`,body)
    await loadDocuments(equipmentId);toast.push("Archivo cargado","success")}
  catch(e){uploadError.value=getApiErrorMessage(e,"No se pudo cargar el archivo");toast.push(uploadError.value,"error")}
  finally{uploading.value=false;input.value=""}}
function downloadDocument(id:number,name:string){const a=document.createElement("a");a.href=`/api/v1/documents/${id}/download`;a.download=name;document.body.appendChild(a);a.click();a.remove()}
async function deleteDocument(doc:EquipmentDocument){if(!window.confirm(`Dar de baja "${doc.original_filename}"?`))return
  try{await apiDelete(`/documents/${doc.id}`);toast.push("Archivo dado de baja","success");if(documentsFor.value)await loadDocuments(documentsFor.value)}
  catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function saveDescription(doc:EquipmentDocument,value:string){try{await apiPatch(`/documents/${doc.id}`,{description:value||null});toast.push("Descripción guardada","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function openCustomer(c:Customer){selected.value=c;equipment.value=await apiGet<Equipment[]>("/customers/"+c.id+"/equipment");window.scrollTo({top:0,behavior:"smooth"})}
function closeCustomer(){selected.value=null;equipment.value=[];window.scrollTo({top:0,behavior:"smooth"})}
function newEquipment(){eq.value={category_id:0,brand:"",model:"",serial_number:"",description:"",notes:""};categoryQuery.value="";categories.value=[];showEquipment.value=true}
async function findCategories(){categoryOpen.value=true;categories.value=await apiGet<EquipmentCategory[]>("/customers/equipment-categories/search",{params:{q:categoryQuery.value}})}
function chooseCategory(cat:EquipmentCategory){eq.value.category_id=cat.id;categoryQuery.value=cat.name;categoryOpen.value=false}
function exactCategory(){return categories.value.some(c=>c.name.toLocaleLowerCase()===categoryQuery.value.trim().toLocaleLowerCase())}
async function createCategory(){const name=categoryQuery.value.trim();if(!name)return;try{const cat=await apiPost<EquipmentCategory>("/customers/equipment-categories",{name});chooseCategory(cat);toast.push("Categoría creada","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function saveEquipment(){if(!selected.value)return;if(!eq.value.category_id){toast.push("Seleccioná o creá una categoría","error");return}try{await apiPost("/customers/"+selected.value.id+"/equipment",{customer_id:selected.value.id,...eq.value});showEquipment.value=false;await openCustomer(selected.value);toast.push("Equipo agregado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
let timer:number|undefined;function searchChanged(){window.clearTimeout(timer);timer=window.setTimeout(load,250)}
onMounted(load);
</script>
<template>
  <div v-if="!selected">
    <div class="card page-header">
      <div><h2 style="margin:0">Clientes</h2><p class="text-secondary" style="margin:4px 0 0">{{ total }} clientes en esta empresa</p></div>
      <div class="toolbar"><input v-model="search" class="toolbar__search" placeholder="Nombre, DNI/CUIT, teléfono o email" @input="searchChanged"><button class="btn btn--primary desktop-primary-action" @click="newCustomer">+ Nuevo cliente</button></div>
    </div>
    <div class="card customers-list">
      <table v-if="items.length" class="table table--cards-mobile"><thead><tr><th>Cliente</th><th>DNI/CUIT</th><th>Contacto</th><th>Estado</th><th></th></tr></thead>
        <tbody><tr v-for="customer in items" :key="customer.id"><td data-label="Cliente"><strong>{{ customer.name }}</strong><div class="text-muted">{{ customer.customer_type==='COMPANY'?'Empresa':'Persona' }}</div></td><td data-label="DNI/CUIT">{{ customer.document||'—' }}</td><td data-label="Contacto">{{ customer.phone||customer.whatsapp||customer.email||'—' }}</td><td data-label="Estado"><span :class="['badge',customer.active?'badge--success':'badge--muted']">{{ customer.active?'Activo':'Inactivo' }}</span></td><td data-label="Acciones" class="mobile-card-actions"><button class="btn btn--ghost btn--sm" @click="openCustomer(customer)">Equipos</button> <button class="btn btn--ghost btn--sm" @click="editCustomer(customer)">Editar</button></td></tr></tbody>
      </table>
      <div v-else class="empty-state">{{ loading?'Cargando…':'Todavía no hay clientes en esta empresa.' }}</div>
    </div>
  </div>

  <div v-else class="customer-detail-shell">
    <button type="button" class="btn btn--ghost customer-detail-back" @click="closeCustomer">← Volver a clientes</button>
    <div class="card customer-equipment-card">
      <div class="flex flex--between"><div><p class="card__title">Equipos de {{ selected.name }}</p><p class="text-secondary">Cada equipo pertenece sólo a esta empresa.</p></div><button class="btn btn--primary" @click="newEquipment">+ Agregar equipo</button></div>
      <table v-if="equipment.length" class="table table--cards-mobile"><thead><tr><th>Tipo</th><th>Marca / modelo</th><th>Serie</th><th>Descripción</th><th>Documentos</th></tr></thead><tbody><tr v-for="equipmentItem in equipment" :key="equipmentItem.id"><td data-label="Tipo">{{equipmentItem.category_name}}</td><td data-label="Marca / modelo">{{[equipmentItem.brand,equipmentItem.model].filter(Boolean).join(' ')||'—'}}</td><td data-label="Serie">{{equipmentItem.serial_number||'—'}}</td><td data-label="Descripción">{{equipmentItem.description||'—'}}</td><td data-label="Documentos"><button type="button" class="btn btn--ghost btn--sm" @click="toggleDocuments(equipmentItem.id)">Documentos ({{ (documentsFor===equipmentItem.id?documents.length:0) }})</button><div v-if="documentsFor===equipmentItem.id" class="doc-panel"><div v-for="d in documents" :key="d.id" class="doc-item"><div class="doc-item__main"><strong>{{ d.original_filename }}</strong><small class="text-muted">{{ d.mime_type }} · {{ formatBytes(d.size_bytes) }} · {{ formatDocDate(d.created_at) }}<template v-if="d.work_order_id"> · de una OT</template></small><input v-if="canManageEquipment" class="doc-item__desc" :value="d.description||''" placeholder="Nota (opcional)" @change="saveDescription(d,($event.target as HTMLInputElement).value)"></div><div class="doc-item__actions"><a class="btn btn--ghost btn--sm" :href="`/api/v1/documents/${d.id}/download`" :download="d.original_filename">Ver</a><button v-if="canManageEquipment" class="btn btn--ghost btn--sm" @click="deleteDocument(d)">Dar de baja</button></div></div><p v-if="!documents.length" class="text-muted doc-empty">Todavía no hay archivos de este equipo.</p><label v-if="canManageEquipment" class="btn btn--primary btn--sm doc-upload"><input type="file" hidden :disabled="uploading" @change="uploadDocument(equipmentItem.id,$event)">{{ uploading?"Subiendo…":"+ Cargar archivo" }}</label><p v-if="uploadError" class="doc-error">{{ uploadError }}</p></div></td></tr></tbody></table>
      <div v-else class="empty-state">Este cliente todavía no tiene equipos cargados.</div>
    </div>
  </div>

  <Modal :open="showCustomer" :title="editing?'Editar cliente':'Nuevo cliente'" @close="showCustomer=false"><form @submit.prevent="saveCustomer">
    <div class="field__row"><div class="field"><label>Tipo</label><select v-model="form.customer_type"><option value="PERSON">Persona</option><option value="COMPANY">Empresa</option></select></div><div class="field"><label>Nombre / Razón social *</label><input v-model="form.name" required></div></div>
    <div class="field__row"><div class="field"><label>DNI / CUIT</label><input v-model="form.document"></div><div class="field"><label>Teléfono</label><input v-model="form.phone"></div></div>
    <div class="field__row"><div class="field"><label>WhatsApp</label><input v-model="form.whatsapp"></div><div class="field"><label>Email</label><input v-model="form.email" type="email"></div></div>
    <div class="field"><label>Domicilio</label><input v-model="form.address"></div><div class="field"><label>Observaciones</label><textarea v-model="form.notes" rows="3"/></div>
    <div class="flex flex--between" style="margin-top:18px"><button class="btn btn--ghost" type="button" @click="showCustomer=false">Cancelar</button><button class="btn btn--primary">Guardar</button></div>
  </form></Modal>

  <Modal :open="showEquipment" :title="'Nuevo equipo · '+(selected?.name||'')" @close="showEquipment=false"><form @submit.prevent="saveEquipment">
    <div class="field__row"><div class="field category-picker"><label>Tipo / categoría *</label><input v-model="categoryQuery" placeholder="Escribí para buscar o crear…" autocomplete="off" required @focus="findCategories" @input="eq.category_id=0;findCategories()"><div v-if="categoryOpen && categoryQuery.trim()" class="category-picker__menu"><button v-for="cat in categories" :key="cat.id" type="button" class="category-picker__option" @click="chooseCategory(cat)">{{cat.name}}</button><button v-if="!exactCategory()" type="button" class="category-picker__option category-picker__create" @click="createCategory">+ Crear “{{categoryQuery.trim()}}”</button></div></div><div class="field"><label>Marca</label><input v-model="eq.brand"></div></div>
    <div class="field__row"><div class="field"><label>Modelo</label><input v-model="eq.model"></div><div class="field"><label>N° de serie</label><input v-model="eq.serial_number"></div></div>
    <div class="field"><label>Descripción</label><input v-model="eq.description"></div><div class="field"><label>Observaciones</label><textarea v-model="eq.notes" rows="3"/></div>
    <div class="flex flex--between" style="margin-top:18px"><button class="btn btn--ghost" type="button" @click="showEquipment=false">Cancelar</button><button class="btn btn--primary">Agregar equipo</button></div>
  </form></Modal>
</template>
<style scoped>
.category-picker{position:relative}.category-picker__menu{position:absolute;z-index:20;top:100%;left:0;right:0;margin-top:6px;padding:6px;background:var(--surface,#152238);border:1px solid rgba(148,163,184,.25);border-radius:12px;box-shadow:0 18px 45px rgba(0,0,0,.35);max-height:220px;overflow:auto}.category-picker__option{display:block;width:100%;text-align:left;padding:10px 12px;border:0;border-radius:8px;background:transparent;color:inherit;cursor:pointer}.category-picker__option:hover{background:rgba(59,130,246,.14)}.category-picker__create{color:#60a5fa;font-weight:700;border-top:1px solid rgba(148,163,184,.15);margin-top:4px}
@media(max-width:700px){
.customers-list{padding:0;background:transparent;border:0;box-shadow:none}
.customers-list .table--cards-mobile tbody{gap:12px}
.customers-list .table--cards-mobile tr{padding:14px;border-radius:16px}
.customer-detail-shell{display:grid;gap:10px}
.customer-detail-back{justify-self:start}
.customer-equipment-card{margin:0}
.customer-equipment-card>.flex{align-items:flex-start;gap:12px;flex-direction:column}
.customer-equipment-card>.flex .btn{width:100%}
.customer-equipment-card .table--cards-mobile{margin-top:14px}
}

.doc-panel{margin-top:10px;display:flex;flex-direction:column;gap:10px}
.doc-item{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;padding:10px;border:1px solid var(--border,#263a57);border-radius:12px}
.doc-item__main{display:flex;flex-direction:column;gap:4px;min-width:0}
.doc-item__main strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.doc-item__actions{display:flex;gap:8px;flex:none}
.doc-item__desc{margin-top:4px;font-size:12px;padding:6px 8px;border:1px solid var(--border,#263a57);border-radius:8px;background:var(--color-surface);color:var(--color-text-primary);width:100%}
.doc-upload{align-self:flex-start;cursor:pointer}
.doc-empty{margin:0;font-size:12px}
.doc-error{margin:0;font-size:12px;color:#ef4444}
</style>