<script setup lang="ts">
import {computed,onMounted,ref,watch} from "vue";
import {useRoute,useRouter} from "vue-router";
import SparePartPicker,{type SparePart} from "../components/SparePartPicker.vue";
import WorkAreaPicker from "../components/WorkAreaPicker.vue";
import {apiDelete,apiGet,apiPatch,apiPost,apiPut,getApiErrorMessage} from "../lib/api";
import {useToastStore} from "../stores/toasts";
import {useSessionStore} from "../stores/session";
interface Customer{id:number;name:string;phone:string|null;whatsapp:string|null}
interface Equipment{id:number;category_name:string;brand:string|null;model:string|null;serial_number:string|null}
interface Technician{id:number;name:string;active:boolean}
interface Order{id:number;number:number;customer_id:number;customer_name:string;customer_phone:string|null;equipment_id:number;equipment_label:string;serial_number:string|null;received_at:string;expected_delivery_at:string|null;completed_at:string|null;delivered_at:string|null;reported_fault:string;physical_condition:string|null;accessories:string|null;notes:string|null;received_by_name:string;status:string;status_id:number|null;status_name:string;status_color:string;technicians:Technician[];work_area_id:number|null;work_area_name:string|null;warranty_type:number|null;warranty_label:string|null;billing_customer_id:number|null;billing_customer_name:string|null}
interface OtStatus{id:number;name:string;color:string;sort_order:number;active:boolean;is_initial:boolean;is_final:boolean;marks_completed:boolean;marks_delivered:boolean}
interface Event{id:number;event_type:string;status:string|null;detail:string|null;user_name:string;created_at:string}
interface Diagnosis{id:number;diagnosis:string;technical_notes:string|null;diagnosed_at:string;updated_at:string;is_open:boolean;revision:number}
interface QuoteItem{id:number;item_type:"PART"|"LABOR";description:string;quantity:number;unit_cost:number;markup_percent:number;unit_price:number;line_total:number;item_code:string|null;price_source:string|null;price_synced_at:string|null}
interface Quote{id:number;work_order_id:number;version:number;status:string;notes:string|null;diagnosis_snapshot:string|null;diagnosis_revision:number|null;subtotal_parts:number;subtotal_labor:number;total:number;created_at:string;sent_at:string|null;decided_at:string|null;items:QuoteItem[]}
interface ExecutionItem{id:number;item_type:"PART"|"LABOR";description:string;quantity:number;unit_cost:number;unit_price:number;item_code:string|null;price_source:string|null;price_synced_at:string|null;created_at:string}

/**
 * Como se rotula un evento del historial.
 *
 * Antes era `e.status==="RECEIVED"?"Recibido":e.event_type`, con lo que cualquier evento que
 * no fuera una recepcion se mostraba con el enum crudo: "STATUS_CHANGE" en el historial, que es
 * justo lo que escribe el cambio de estado automatico al emitir un presupuesto. El `status`
 * ya trae el nombre del estado, asi que se usa para esos casos y el `detail` de al lado ya
 * explica que paso.
 */
const ETIQUETAS_EVENTO:Record<string,string>={RECEPTION:"Recepción",STATUS_CHANGE:"Cambio de estado",NOTICE:"Aviso preparado",DIAGNOSIS:"Diagnóstico",DIAGNOSIS_REOPENED:"Diagnóstico reabierto",QUOTE_CREATED:"Presupuesto generado",QUOTE_SENT:"Presupuesto enviado",QUOTE_APPROVED:"Presupuesto aprobado",QUOTE_REJECTED:"Presupuesto rechazado",WORK_EXECUTED:"Trabajo registrado",FINAL_TEST:"Prueba final",EXPECTED_DELIVERY_CHANGE:"Cambio de entrega prevista",DOCUMENT_DELETED:"Documento dado de baja",technician_assigned:"Técnico asignado",technician_unassigned:"Técnico quitado"};
function etiquetaEvento(e:Event):string{
  // El mapa se consulta **antes** que el caso RECEIVED. Un aviso preparado tambien nace con
  // el estado que tenia la orden en su campo `status`, asi que si la orden estaba en Recibido
  // el evento salia rotulado "Recibido", como si la recepcion se hubiera repetido.
  const etiqueta=ETIQUETAS_EVENTO[e.event_type];
  if(etiqueta)return etiqueta;
  return e.status==="RECEIVED"?"Recibido":e.event_type;
}
interface FinalTest{id:number;passed:boolean;notes:string|null;tested_at:string}
const toast=useToastStore(),session=useSessionStore(),orders=ref<Order[]>([]),total=ref(0),search=ref(""),customers=ref<Customer[]>([]),equipment=ref<Equipment[]>([]),selected=ref<Order|null>(null),events=ref<Event[]>([]),statuses=ref<OtStatus[]>([]),showReception=ref(false),showStatuses=ref(false);
// Cuantas OT por pagina: 10 por defecto y se recuerda en el navegador entre visitas.
const PAGE_SIZE_KEY="vogel.workOrdersPageSize",PAGE_SIZES=[5,10,25,50,100];
function readPageSize(){try{const v=Number(localStorage.getItem(PAGE_SIZE_KEY));return PAGE_SIZES.includes(v)?v:10}catch{return 10}}
const page=ref(1),pageSize=ref(readPageSize()),statusIds=ref<number[]>([]),customerFilter=ref(""),dateFrom=ref(""),dateTo=ref(""),showFilters=ref(false);
const openOnly=ref(false);
watch(pageSize,(v)=>{try{localStorage.setItem(PAGE_SIZE_KEY,String(v))}catch{/* sin storage: vale hasta recargar */}});
const activeFilterCount=computed(()=>(statusIds.value.length?1:0)+(customerFilter.value.trim()?1:0)+(dateFrom.value?1:0)+(dateTo.value?1:0)+(openOnly.value?1:0));
const totalPages=computed(()=>Math.max(1,Math.ceil(total.value/pageSize.value))),firstResult=computed(()=>total.value?((page.value-1)*pageSize.value)+1:0),lastResult=computed(()=>Math.min(page.value*pageSize.value,total.value));
const form=ref({customer_id:0,equipment_id:0,technician_id:0,reported_fault:"",physical_condition:"",accessories:"",notes:"",work_area_id:0});
// El area de trabajo de la orden: de ella salen la garantia y la empresa a liquidar, y
// por lo tanto si la orden entra al cierre a marcas. `areaCoincide` dice si lo escrito
// es un area del maestro: si no, la orden no se manda.
const areaCoincide=ref(true);
// El area de una orden ya abierta: se puede corregir, y queda escrito en el historial.
const areaOrdenId=ref<number|null>(null),areaOrdenCoincide=ref(true),guardandoArea=ref(false);
const areaCambiada=computed(()=>!!selected.value&&areaOrdenId.value!==selected.value.work_area_id);
async function guardarArea(){
  if(!selected.value)return;
  if(!areaOrdenCoincide.value){toast.push("El área escrita no está en el maestro. Elegí una de la lista o borrá el texto.","error");return}
  guardandoArea.value=true;
  try{
    const row=await apiPatch<Order>(`/work-orders/${selected.value.id}/work-area`,{work_area_id:areaOrdenId.value});
    selected.value=row;
    events.value=await apiGet<Event[]>(`/work-orders/${row.id}/events`);
    toast.push(row.work_area_name?`Área de la OT: ${row.work_area_name}`:"La orden quedó sin área: no entra al cierre a marcas","success");
  }catch(e){toast.push(getApiErrorMessage(e),"error")}
  finally{guardandoArea.value=false}
}
const companyTimezone=ref("America/Argentina/Cordoba");
const statusMenuOpen=ref(false),pendingStatus=ref<OtStatus|null>(null),statusNote=ref(""),expectedDeliveryInput=ref("");
const featureParams=ref<Record<string,string|number|boolean>>({});
const diagnosisEnabled=computed(()=>featureParams.value["work_orders.use_diagnosis"]!==false),budgetEnabled=computed(()=>featureParams.value["work_orders.use_budget"]!==false),showInternalCosts=computed(()=>featureParams.value["work_orders.show_internal_costs"]!==false),finalTestsEnabled=computed(()=>featureParams.value["work_orders.use_final_tests"]!==false);
const diagnosis=ref<Diagnosis|null>(null),diagnosisForm=ref({diagnosis:"",technical_notes:""}),quotes=ref<Quote[]>([]);
interface OtNotification{id:number;channel:string;recipient:string;subject:string|null;body:string;status:string;attempts:number;error:string|null;provider_message_id:string|null;created_at:string;sent_at:string|null}
const notifications=ref<OtNotification[]>([]);
interface PreviewItem{channel:string;recipient:string;subject:string|null;body:string;skipped:boolean;reason:string|null;originalRecipient?:string}
const preview=ref<PreviewItem[]>([]),showPreview=ref(false),previewLoading=ref(false);
function isDirtyPreview(it:PreviewItem){const st=stById(it.channel);return !!st&&!!st.notification_template&&st.notification_template!==it.body}
function stById(_ch:string){return pendingStatus.value}
async function openStatusPreview(target:OtStatus){
  if(!selected.value)return;
  pendingStatus.value=target;
  const tieneAvisos=target.notifications_active&&(target.notify_whatsapp||target.notify_email);
  if(!tieneAvisos){await applyStatus();return}
  previewLoading.value=true;preview.value=[];showPreview.value=true;
  try{const r=await apiPost<{items:PreviewItem[]}>("/work-orders/"+selected.value.id+"/notification-preview",{status_id:target.id});preview.value=r.items.map(i=>({...i,originalRecipient:i.recipient}))}
  catch(e){toast.push(getApiErrorMessage(e,"No se pudo preparar el aviso"),"error");showPreview.value=false;await applyStatus();return}
  finally{previewLoading.value=false}
}
async function applyStatus(overrides?:Record<string,PreviewItem>){
  if(!selected.value||!pendingStatus.value)return;
  try{
    const body:Record<string,unknown>={status_id:pendingStatus.value.id,note:statusNote.value.trim()||null};
    if(overrides)body.notification_overrides=overrides;
    selected.value=await apiPost<Order>("/work-orders/"+selected.value.id+"/status",body);
    pendingStatus.value=null;statusNote.value="";showPreview.value=false;
    await load();events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");
    await loadNotifications(selected.value.id);
    toast.push("Estado actualizado","success")
  }catch(e){toast.push(getApiErrorMessage(e),"error")}
}
async function confirmWithNotice(){
  const edited:Record<string,PreviewItem>={};
  for(const it of preview.value){
  // Si el backend lo marco como skipped, el motivo era que faltaba el destino.
  // Si el usuario completo uno a mano, ahora se envia igual.
  if(!(it.recipient||"").trim())continue;
  const ov:Record<string,string>={body:it.body};
  if(it.subject!==null)ov.subject=it.subject;
  if((it.recipient||"").trim()!==(it.originalRecipient||"").trim())ov.recipient=(it.recipient||"").trim();
  edited[it.channel]=ov;
}
  await applyStatus(Object.keys(edited).length?edited:undefined)
}
async function copiarRef(v:string){try{await navigator.clipboard.writeText(v);toast.push("ID copiado","success")}catch(_){toast.push("No se pudo copiar","error")}}
const notificationLabels:Record<string,string>={SENT:"Enviado",QUEUED:"Encolado en la gateway",FAILED:"Falló",SKIPPED:"No se envió",PENDING:"Pendiente"};
async function loadNotifications(oid:number){try{const r=await apiGet<{items:OtNotification[]}>("/work-orders/"+oid+"/notifications");notifications.value=Array.isArray(r?.items)?r.items:[]}catch(_){notifications.value=[]}}
const showDiagnosisModal=ref(false),showQuoteModal=ref(false),printQuote=ref<Quote|null>(null),decisionQuote=ref<Quote|null>(null),decisionAction=ref<"approve"|"reject"|null>(null),decisionNote=ref(""),showReopenDiagnosis=ref(false),reopenReason=ref("");
// `part` es el articulo del catalogo de Flexxus que backs la linea. Si el
// catalogo aplica a esta empresa y la linea no tiene `part`, el texto no
// coincide con ningun articulo y la linea no se guarda (#114).
const quoteItems=ref([{item_type:"PART" as "PART"|"LABOR",description:"",quantity:1,unit_cost:0,unit_price:null as number|null,part:null as SparePart|null}]),quoteNotes=ref("");
const execution=ref<ExecutionItem[]>([]),finalTests=ref<FinalTest[]>([]);
const executionForm=ref({item_type:"LABOR" as "PART"|"LABOR",description:"",quantity:1,unit_cost:0,unit_price:0,part:null as SparePart|null});
// Si el catalogo de Flexxus aplica a esta empresa. `null` = todavia no se
// consulto. Lo define el picker cuando le pregunta al backend.
const catalogoDisponible=ref<boolean|null>(null);
const finalTestForm=ref({passed:true,notes:""});
const currentStatus=computed(()=>statuses.value.find(s=>s.id===selected.value?.status_id)||null);
const isFinal=computed(()=>currentStatus.value?.is_final===true);
// Primer paso del taller sin completar: es el único que lleva el botón primario.
const currentStep=computed(()=>{if(isFinal.value)return null;if(diagnosisEnabled.value&&!diagnosis.value)return "diagnosis";if(budgetEnabled.value&&!quotes.value.some(q=>q.status==="APPROVED"))return "quote";if(!execution.value.length)return "execution";if(finalTestsEnabled.value&&!finalTests.value.length)return "tests";return null});
function parseUtc(value:string){return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value)?value:value+"Z")}
// Una fecha vacia o invalida no puede romper el render de la OT entera: se muestra "—".
function formatCompanyDate(value:string){const d=parseUtc(value);if(!value||Number.isNaN(d.getTime()))return "—";return new Intl.DateTimeFormat("es-AR",{timeZone:companyTimezone.value,dateStyle:"short",timeStyle:"medium"}).format(d)}
async function loadCompanyTimezone(){try{const c=await apiGet<{timezone:string}>("/companies/current");companyTimezone.value=c.timezone||"America/Argentina/Cordoba"}catch(_){companyTimezone.value="America/Argentina/Cordoba"}}
function requestStatus(st:OtStatus){statusMenuOpen.value=false;if(st.id===selected.value?.status_id)return;void openStatusPreview(st)}
function cancelStatus(){pendingStatus.value=null;statusNote.value=""}
function toDateTimeLocal(value:string|null){if(!value)return "";const d=parseUtc(value);const parts=new Intl.DateTimeFormat("sv-SE",{timeZone:companyTimezone.value,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).formatToParts(d);const get=(t:string)=>parts.find(p=>p.type===t)?.value||"";return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`}
async function saveExpectedDelivery(){if(!selected.value)return;try{const value=expectedDeliveryInput.value?new Date(expectedDeliveryInput.value).toISOString():null;selected.value=await apiPatch<Order>("/work-orders/"+selected.value.id+"/expected-delivery",{expected_delivery_at:value});expectedDeliveryInput.value=toDateTimeLocal(selected.value.expected_delivery_at);events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");await load();toast.push("Entrega prevista actualizada","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
const customerQuery=ref(""),customerOpen=ref(false),showQuickCustomer=ref(false);
// Maestro de tecnicos: se carga una vez y se usa tanto en la recepcion como en el detalle.
// El filtro es local (acento y mayusculas) porque el maestro es chico.
const technicians=ref<Technician[]>([]),technicianQuery=ref(""),technicianOpen=ref(false);
const quickCustomer=ref({customer_type:"PERSON",name:"",document:"",phone:"",whatsapp:"",email:"",address:"",notes:""});
interface EquipmentCategory{id:number;name:string;active:boolean}
const showQuickEquipment=ref(false),categoryQuery=ref(""),categories=ref<EquipmentCategory[]>([]),categoryOpen=ref(false);
const quickEquipment=ref({category_id:0,brand:"",model:"",serial_number:"",description:"",notes:""});
async function loadStatuses(){try{statuses.value=await apiGet<OtStatus[]>("/work-orders/statuses")}catch(_){statuses.value=[]}}
async function load(){try{const r=await apiGet<{items:Order[];total:number;page:number;page_size:number}>("/work-orders",{params:{search:search.value||undefined,status_id:statusIds.value.length?statusIds.value:undefined,customer:customerFilter.value||undefined,date_from:dateFrom.value||undefined,date_to:dateTo.value||undefined,open_only:openOnly.value?true:undefined,page:page.value,page_size:pageSize.value}});orders.value=Array.isArray(r?.items)?r.items:[];total.value=typeof r?.total==="number"?r.total:0;if(page.value>totalPages.value){page.value=totalPages.value;return load()}}catch(e){toast.push(getApiErrorMessage(e,"No se pudieron cargar las órdenes"),"error")}}
function filtersChanged(){page.value=1;load()}
function applyFilters(){page.value=1;load()}
function clearFilters(){statusIds.value=[];customerFilter.value="";dateFrom.value="";dateTo.value="";page.value=1;load()}
function changePage(next:number){if(next<1||next>totalPages.value)return;page.value=next;load();window.scrollTo({top:0,behavior:"smooth"})}
async function newReception(){if(showReception.value)return;receptionFiles.value=[];form.value={customer_id:0,equipment_id:0,technician_id:0,reported_fault:"",physical_condition:"",accessories:"",notes:"",work_area_id:0};areaCoincide.value=true;equipment.value=[];customers.value=[];customerQuery.value="";customerOpen.value=false;technicianQuery.value="";technicianOpen.value=false;await loadTechnicians();showReception.value=true}
async function findCustomers(){customerOpen.value=true;customers.value=(await apiGet<{items:Customer[]}>("/customers",{params:{search:customerQuery.value||undefined,active:true,page_size:20}})).items}
async function chooseCustomer(c:Customer){form.value.customer_id=c.id;customerQuery.value=c.name;customerOpen.value=false;await customerChanged()}
function openQuickCustomer(){quickCustomer.value={customer_type:"PERSON",name:customerQuery.value.trim(),document:"",phone:"",whatsapp:"",email:"",address:"",notes:""};showQuickCustomer.value=true;customerOpen.value=false}
async function saveQuickCustomer(){try{const p=quickCustomer.value;const c=await apiPost<Customer>("/customers",{...p,email:p.email||null,document:p.document||null,phone:p.phone||null,whatsapp:p.whatsapp||null,address:p.address||null,notes:p.notes||null});showQuickCustomer.value=false;customers.value=[c];await chooseCustomer(c);toast.push("Cliente creado y seleccionado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function customerChanged(){form.value.equipment_id=0;equipment.value=form.value.customer_id?await apiGet<Equipment[]>("/customers/"+form.value.customer_id+"/equipment"):[]}
// --- Tecnicos ---------------------------------------------------------------------
// El combo filtra por "contiene", sin distinguir mayusculas ni acentos, y solo deja
// elegir a alguien que esta en la lista: no se guardan nombres sueltos.
function normalizarTexto(texto:string){return texto.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").trim()}
const tecnicosAsignables=computed(()=>{
  const q=normalizarTexto(technicianQuery.value);
  return technicians.value.filter(t=>t.active&&(!q||normalizarTexto(t.name).includes(q)));
});
// Los que todavia no estan en esta OT.
const tecnicosDisponibles=computed(()=>tecnicosAsignables.value.filter(t=>!selected.value?.technicians?.some(a=>a.id===t.id)));
async function loadTechnicians(){try{technicians.value=await apiGet<Technician[]>("/technicians")}catch(_){technicians.value=[]}}
function chooseTechnician(t:Technician){form.value.technician_id=t.id;technicianQuery.value=t.name;technicianOpen.value=false}
async function assignTechnician(t:Technician){if(!selected.value)return;try{selected.value=await apiPost<Order>("/work-orders/"+selected.value.id+"/technicians",{technician_id:t.id});events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");technicianQuery.value="";toast.push(t.name+" asignado a la OT","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function unassignTechnician(t:Technician){if(!selected.value)return;try{selected.value=await apiDelete<Order>("/work-orders/"+selected.value.id+"/technicians/"+t.id);events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");toast.push(t.name+" quitado de la OT","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
function openQuickEquipment(){if(!form.value.customer_id)return;quickEquipment.value={category_id:0,brand:"",model:"",serial_number:"",description:"",notes:""};categoryQuery.value="";categories.value=[];showQuickEquipment.value=true}
async function findCategories(){categoryOpen.value=true;categories.value=await apiGet<EquipmentCategory[]>("/customers/equipment-categories/search",{params:{q:categoryQuery.value}})}
function chooseCategory(cat:EquipmentCategory){quickEquipment.value.category_id=cat.id;categoryQuery.value=cat.name;categoryOpen.value=false}
function exactCategory(){return categories.value.some(c=>c.name.toLocaleLowerCase()===categoryQuery.value.trim().toLocaleLowerCase())}
async function createCategory(){const name=categoryQuery.value.trim();if(!name)return;try{const cat=await apiPost<EquipmentCategory>("/customers/equipment-categories",{name});chooseCategory(cat);toast.push("Categoría creada","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function saveQuickEquipment(){if(!form.value.customer_id)return;if(!quickEquipment.value.category_id){toast.push("Seleccioná o creá una categoría","error");return}try{const e=await apiPost<Equipment>("/customers/"+form.value.customer_id+"/equipment",{customer_id:form.value.customer_id,...quickEquipment.value});showQuickEquipment.value=false;await customerChanged();form.value.equipment_id=e.id;toast.push("Equipo creado y seleccionado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
const receptionFiles=ref<File[]>([]),uploadingDocs=ref(false);
const canManageWorkOrders=session.hasPermission("work_orders.manage");
interface OtDocument{id:number;equipment_id:number;work_order_id:number|null;original_filename:string;mime_type:string;size_bytes:number;size_mb:number;description:string|null;uploaded_by_user_id:number;created_at:string;is_previewable:boolean}
const orderDocuments=ref<OtDocument[]>([]);
function pickReceptionFiles(event:Event){const input=event.target as HTMLInputElement;receptionFiles.value=[...(input.files||[])];input.value=""}
function dropReceptionFile(index:number){receptionFiles.value.splice(index,1)}
function formatBytes(n:number){return n<1048576?Math.max(1,Math.round(n/1024))+" KB":(n/1048576).toFixed(1)+" MB"}
function formatDocDate(v:string){const d=new Date(/[zZ]|[+-]\d\d:\d\d$/.test(v)?v:v+"Z");return Number.isNaN(d.getTime())?"—":d.toLocaleDateString("es-AR",{day:"2-digit",month:"2-digit",year:"2-digit"})}
async function uploadFiles(equipmentId:number,workOrderId:number|null,files:File[]){if(!files.length)return;uploadingDocs.value=true
  let ok=0;let fallos:string[]=[]
  for(const file of files){
    const body=new FormData();body.append("file",file);if(workOrderId)body.append("work_order_id",String(workOrderId))
    try{await apiPost(`/equipment/${equipmentId}/documents`,body);ok++}catch(e){fallos.push(`${file.name}: ${getApiErrorMessage(e)}`)}
  }
  uploadingDocs.value=false
  return {ok,fallos}}
async function loadOrderDocuments(orderId:number){try{const r=await apiGet<{items:OtDocument[]}>(`/work-orders/${orderId}/documents`);orderDocuments.value=Array.isArray(r?.items)?r.items:[]}catch(_){orderDocuments.value=[]}}
async function pickOrderFiles(event:Event){const input=event.target as HTMLInputElement;const files=[...(input.files||[])];input.value="";if(!files.length||!selected.value)return
  const res=await uploadFiles(selected.value.equipment_id,selected.value.id,files)
  if(res){if(res.ok)toast.push(`${res.ok} archivo(s) adjunto(s) a la orden`,"success")
    res.fallos.forEach(f=>toast.push(f,"error"))}
  await loadOrderDocuments(selected.value.id)}
async function deleteOrderDocument(doc:OtDocument){if(!window.confirm(`Dar de baja "${doc.original_filename}"?`))return
  try{await apiDelete(`/documents/${doc.id}`);toast.push("Archivo dado de baja","success");if(selected.value)await loadOrderDocuments(selected.value.id)}
  catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function save(){
// El area escrita tiene que ser un area del maestro: si no, la orden se crearia sin
// garantia ni empresa a liquidar, y nadie se enteraria hasta el cierre.
if(!areaCoincide.value){toast.push("El área escrita no está en el maestro. Elegí una de la lista o borrá el texto.","error");return}
try{const row=await apiPost<Order>("/work-orders",{...form.value,technician_id:form.value.technician_id||null,work_area_id:form.value.work_area_id||null})
  // Los archivos se suben DESPUES de crear la OT: el documento necesita su id para
  // quedar vinculado. Si alguno falla, la OT ya esta creada y se avisa cual salio mal.
  if(receptionFiles.value.length){const res=await uploadFiles(row.equipment_id,row.id,receptionFiles.value)
    if(res&&res.ok)toast.push(`${res.ok} archivo(s) adjunto(s)`,"success")
    if(res)res.fallos.forEach(f=>toast.push(f,"error"))}
  receptionFiles.value=[]
  showReception.value=false;toast.push("OT #"+row.number+" generada","success");await load();await open(row)
  await loadOrderDocuments(row.id)}
catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function loadFeatureParams(){try{const rows=await apiGet<Array<{parameter:string;value:string|number|boolean}>>("/company-parameters");featureParams.value=Object.fromEntries(rows.map(p=>[p.parameter,p.value]))}catch(_){featureParams.value={}}}

/**
 * Manda a mano un aviso que quedo pendiente.
 *
 * Los avisos se mandan solos cuando cambia el estado, pero los que deja preparados el
 * asistente se quedan esperando a que alguien los mire y los mande. Sin esta accion, preparar
 * un aviso seria un callejon sin salida.
 *
 * El backend es el que decide: rechaza los que ya salieron, para que un doble clic no mande
 * dos veces el mismo mensaje.
 */
const sendingNotification=ref<number|null>(null);
async function sendNotification(n:OtNotification){
  if(!selected.value||sendingNotification.value!==null)return;
  sendingNotification.value=n.id;
  try{
    const mandada=await apiPost<OtNotification>(`/work-orders/${selected.value.id}/notifications/${n.id}/send`);
    notifications.value=notifications.value.map(x=>x.id===n.id?mandada:x);
    if(mandada.status==="FAILED")toast.push("El aviso no se pudo enviar. Mirá el error y volvé a intentarlo.","error");
    else toast.push("Aviso enviado","success");
    if(mandada.error)toast.push(mandada.error,"error");
  }catch(e){toast.push(getApiErrorMessage(e),"error")}
  finally{sendingNotification.value=null}
}
// Un aviso pendiente se puede abrir para leerlo. Mandarlo sin leerlo seria mandar a ciegas.
const mensajeAbierto=ref<number|null>(null);
function toggleMensaje(id:number){mensajeAbierto.value=mensajeAbierto.value===id?null:id}

async function loadWorkshop(oid:number){diagnosis.value=await apiGet<Diagnosis|null>("/work-orders/"+oid+"/diagnosis");diagnosisForm.value={diagnosis:diagnosis.value?.diagnosis||"",technical_notes:diagnosis.value?.technical_notes||""};quotes.value=await apiGet<Quote[]>("/work-orders/"+oid+"/quotes");execution.value=await apiGet<ExecutionItem[]>("/work-orders/"+oid+"/execution");finalTests.value=finalTestsEnabled.value?await apiGet<FinalTest[]>("/work-orders/"+oid+"/final-tests"):[]}
async function addExecution(){if(!selected.value||!executionForm.value.description.trim())return;if(repuestoSinElegir(executionForm.value)){toast.push("Elegí el repuesto de la lista del catálogo","error");return}try{await apiPost("/work-orders/"+selected.value.id+"/execution",{item_type:executionForm.value.item_type,description:executionForm.value.description,quantity:executionForm.value.quantity,unit_cost:executionForm.value.unit_cost,unit_price:executionForm.value.unit_price,item_code:executionForm.value.part?.code??null,price_source:executionForm.value.part?.price_source??null,price_synced_at:executionForm.value.part?.price_synced_at??null});executionForm.value={item_type:"LABOR",description:"",quantity:1,unit_cost:0,unit_price:0,part:null};await loadWorkshop(selected.value.id);events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");toast.push("Ejecución registrada","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function addFinalTest(){if(!selected.value)return;try{await apiPost("/work-orders/"+selected.value.id+"/final-tests",{passed:finalTestForm.value.passed,notes:finalTestForm.value.notes.trim()||null});finalTestForm.value={passed:true,notes:""};await loadWorkshop(selected.value.id);events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");toast.push("Prueba final registrada","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function open(row:Order){selected.value=await apiGet<Order>("/work-orders/"+row.id);areaOrdenId.value=selected.value.work_area_id;areaOrdenCoincide.value=true;expectedDeliveryInput.value=toDateTimeLocal(selected.value.expected_delivery_at);events.value=await apiGet<Event[]>("/work-orders/"+row.id+"/events");await loadWorkshop(row.id);await loadNotifications(row.id);await loadOrderDocuments(row.id);window.scrollTo({top:0,behavior:"smooth"})}
function closeOrder(){selected.value=null;statusMenuOpen.value=false;window.scrollTo({top:0,behavior:"smooth"})}
function openDiagnosisEditor(){if(diagnosis.value&&!diagnosis.value.is_open){showReopenDiagnosis.value=true;reopenReason.value="";return}diagnosisForm.value={diagnosis:diagnosis.value?.diagnosis||"",technical_notes:diagnosis.value?.technical_notes||""};showDiagnosisModal.value=true}
async function saveDiagnosis(){if(!selected.value)return;try{diagnosis.value=await apiPut<Diagnosis>("/work-orders/"+selected.value.id+"/diagnosis",diagnosisForm.value);events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");showDiagnosisModal.value=false;toast.push("Diagnóstico guardado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
function addQuoteItem(type:"PART"|"LABOR"){quoteItems.value.push({item_type:type,description:"",quantity:1,unit_cost:0,unit_price:null,part:null})}
function removeQuoteItem(index:number){if(quoteItems.value.length>1)quoteItems.value.splice(index,1)}
function openQuoteEditor(){quoteItems.value=[{item_type:"PART",description:"",quantity:1,unit_cost:0,unit_price:null,part:null}];quoteNotes.value="";showQuoteModal.value=true}

/**
 * El picker aviva que articulo se eligio. Se completan el costo interno y el
 * precio al cliente con los del ERP: el precio del presupuesto es el del ERP,
 * no el markup sobre un costo que alguien cargo a mano.
 */
function onQuotePart(index:number,payload:{description:string;part:SparePart|null}){
  const item=quoteItems.value[index];if(!item)return;
  item.part=payload.part;
  if(!payload.part)return;
  if(payload.part.cost!==null&&payload.part.cost!==undefined)item.unit_cost=payload.part.cost;
  if(payload.part.sale_price!==null&&payload.part.sale_price!==undefined)item.unit_price=payload.part.sale_price;
}
function onExecutionPart(payload:{description:string;part:SparePart|null}){
  executionForm.value.part=payload.part;
  if(!payload.part)return;
  if(payload.part.cost!==null&&payload.part.cost!==undefined)executionForm.value.unit_cost=payload.part.cost;
  if(payload.part.sale_price!==null&&payload.part.sale_price!==undefined)executionForm.value.unit_price=payload.part.sale_price;
}
/** Con el catalogo activo, un repuesto tiene que salir de una opcion de la lista. */
function repuestoSinElegir(item:{item_type:string;description:string;part:SparePart|null}|undefined):boolean{
  if(catalogoDisponible.value!==true)return false;
  return !!item&&item.item_type==="PART"&&!item.part;
}
/**
 * Si la linea cambia de Repuesto a Mano de obra, se limpia la eleccion del
 * catalogo y el precio: si no, la linea de mano de obra se queda con el
 * precio de venta del repuesto que estaba antes.
 */
function onQuoteTypeChange(index:number){
  const item=quoteItems.value[index];if(!item)return;
  if(item.item_type==="LABOR"){item.part=null;item.unit_price=null}
}
function onExecutionTypeChange(){
  if(executionForm.value.item_type==="LABOR"){executionForm.value.part=null;executionForm.value.unit_price=0}
}
async function createQuote(){if(!selected.value)return;try{const items=quoteItems.value.filter(x=>x.description.trim());if(!items.length){toast.push("Agregá al menos un ítem","error");return}const sinElegir=items.find(repuestoSinElegir);if(sinElegir){toast.push(`Elegí “${sinElegir.description}” de la lista del catálogo`,"error");return}const q=await apiPost<Quote>("/work-orders/"+selected.value.id+"/quotes",{items:items.map(x=>({item_type:x.item_type,description:x.description,quantity:x.quantity,unit_cost:x.unit_cost,unit_price:x.unit_price||null,item_code:x.part?.code??null,price_source:x.part?.price_source??null,price_synced_at:x.part?.price_synced_at??null})),notes:quoteNotes.value||null});quotes.value.unshift(q);quoteItems.value=[{item_type:"PART",description:"",quantity:1,unit_cost:0,unit_price:null,part:null}];quoteNotes.value="";events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");selected.value=await apiGet<Order>("/work-orders/"+selected.value.id);showQuoteModal.value=false;toast.push("Presupuesto v"+q.version+" generado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
function askQuoteDecision(q:Quote,action:"approve"|"reject"){decisionQuote.value=q;decisionAction.value=action;decisionNote.value=""}
async function confirmQuoteDecision(){if(!selected.value||!decisionQuote.value||!decisionAction.value)return;if(decisionAction.value==="reject"&&!decisionNote.value.trim()){toast.push("Indicá el motivo del rechazo","error");return}try{await apiPost("/work-orders/"+selected.value.id+"/quotes/"+decisionQuote.value.id+"/"+decisionAction.value,{note:decisionNote.value.trim()||null});decisionQuote.value=null;decisionAction.value=null;await loadWorkshop(selected.value.id);selected.value=await apiGet<Order>("/work-orders/"+selected.value.id);events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");await load();toast.push("Decisión registrada","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function sendQuote(q:Quote){if(!selected.value)return;try{await apiPost("/work-orders/"+selected.value.id+"/quotes/"+q.id+"/send",{note:null});await loadWorkshop(selected.value.id);selected.value=await apiGet<Order>("/work-orders/"+selected.value.id);events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");await load();toast.push("Presupuesto enviado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function reopenDiagnosis(){if(!selected.value||!reopenReason.value.trim())return;try{diagnosis.value=await apiPost<Diagnosis>("/work-orders/"+selected.value.id+"/diagnosis/reopen",{reason:reopenReason.value.trim()});showReopenDiagnosis.value=false;diagnosisForm.value={diagnosis:diagnosis.value.diagnosis,technical_notes:diagnosis.value.technical_notes||""};showDiagnosisModal.value=true;events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");toast.push("Diagnóstico reabierto","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function confirmStatus(){if(!selected.value||!pendingStatus.value)return;try{selected.value=await apiPost<Order>("/work-orders/"+selected.value.id+"/status",{status_id:pendingStatus.value.id,note:statusNote.value.trim()||null});pendingStatus.value=null;statusNote.value="";await load();events.value=await apiGet<Event[]>("/work-orders/"+selected.value.id+"/events");await loadNotifications(selected.value.id);toast.push("Estado actualizado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
async function saveStatus(st:OtStatus){try{await apiPatch("/work-orders/statuses/"+st.id,{name:st.name,color:st.color,sort_order:st.sort_order,active:st.active,is_initial:st.is_initial,is_final:st.is_final,marks_completed:st.marks_completed,marks_delivered:st.marks_delivered});await loadStatuses();await load();toast.push("Estado guardado","success")}catch(e){toast.push(getApiErrorMessage(e),"error")}}
function printReceipt(){printQuote.value=null;document.body.classList.add("printing-receipt");const cleanup=()=>{document.body.classList.remove("printing-receipt");window.removeEventListener("afterprint",cleanup)};window.addEventListener("afterprint",cleanup);setTimeout(()=>window.print(),60)}
function printBudget(q:Quote){printQuote.value=q;setTimeout(()=>{window.print();printQuote.value=null},80)}
let timer:number|undefined;function searchChanged(){window.clearTimeout(timer);page.value=1;timer=window.setTimeout(load,250)}
const route=useRoute(),router=useRouter();
async function openById(id:number){
  try{
    const row=await apiGet<Order>("/work-orders/"+id);
    await open(row);
  }catch(e){toast.push(getApiErrorMessage(e,"No se pudo abrir la orden"),"error")}
}
async function handleDeepLinks(){
  const q=route.query as Record<string,unknown>;
  const openId=q.open ?? q.openId ?? q.id;
  const wantsNew=q.new==="1"||q.action==="new";
  if(openId!==undefined&&openId!==null&&String(openId).trim()!==""){
    const id=Number(String(openId));
    if(Number.isInteger(id)&&id>0){await openById(id)}
  }else if(wantsNew&&session.hasPermission("work_orders.manage")){
    await newReception();
  }
  if(openId!==undefined||wantsNew){
    router.replace({path:route.path,query:{...route.query,open:undefined,openId:undefined,id:undefined,new:undefined,action:undefined}});
  }
}
// Aplica los filtros que llegan por URL. El dashboard los manda al linkear una alerta,
// asi que sin esto el link abre el listado completo y no la seccion que dice.
function applyFilterQuery(){
  const q=route.query as Record<string,unknown>;
  const ids=q.status_id===undefined?[]:(Array.isArray(q.status_id)?q.status_id:[q.status_id])
    .map(v=>Number(String(v)))
    .filter(v=>Number.isInteger(v)&&v>0);
  if(ids.length) statusIds.value=ids;
  if(typeof q.date_from==="string") dateFrom.value=q.date_from;
  if(typeof q.date_to==="string") dateTo.value=q.date_to;
  if(q.open_only!==undefined) openOnly.value=q.open_only==="true"||q.open_only==="1";
  if(ids.length||q.date_to||q.open_only!==undefined) showFilters.value=true;
}

onMounted(async()=>{
  applyFilterQuery();
  // Cada carga va por separado y sin cortar el flujo: si una falla (por ejemplo, la base
  // se reinicia y el backend responde 500), el deep-link se pierde igual. Con allSettled
  // el modal de nueva recepcion abre siempre, y cada carga avisa su propio error.
  await Promise.allSettled([load(),loadStatuses(),loadCompanyTimezone(),loadFeatureParams(),loadTechnicians()]);
  await handleDeepLinks();
});
// El deep-link tiene que reaccionar a cualquier cambio de la URL, no solo a "open": el
// dashboard manda ?new=1 para abrir la recepcion, y si el usuario ya esta en esta pantalla
// la vista no se vuelve a montar (misma ruta, distinta query) y el modal no abria nunca.
watch(()=>[route.query.open,route.query.openId,route.query.id,route.query.new,route.query.action],async()=>{await handleDeepLinks()});
watch(()=>[route.query.status_id,route.query.date_to,route.query.open_only],async()=>{
  applyFilterQuery();page.value=1;await load();
});
</script>
<template>
<div v-if="!selected" class="card page-header"><div><h2 style="margin:0">Órdenes de trabajo</h2><p class="text-secondary" style="margin:4px 0 0">{{total}} órdenes en esta empresa</p></div><div class="toolbar"><input v-model="search" class="toolbar__search" placeholder="N° OT, cliente, teléfono, equipo o serie" @input="searchChanged"><button class="btn btn--ghost filters-toggle" aria-controls="work-order-filters" @click="showFilters=!showFilters" :aria-expanded="showFilters">Filtros{{activeFilterCount?` · ${activeFilterCount}`:""}} {{showFilters?"▲":"▼"}}</button><RouterLink v-if="session.hasPermission('work_orders.manage')" class="btn btn--ghost" to="/app/work-orders/import">Importar trabajos</RouterLink><button class="btn btn--primary desktop-primary-action" @click="newReception">+ Nueva recepción</button></div><button class="mobile-fab" aria-label="Nueva recepción" @click="newReception">+<span>Recepción</span></button></div>
<div v-if="!selected&&showFilters" id="work-order-filters" class="card work-order-filters"><div class="filters-grid"><div class="field"><label>Estado</label><select v-model="statusIds" multiple size="3"><option v-for="s in statuses.filter(x=>x.active)" :key="s.id" :value="s.id">{{s.name}}</option></select></div><div class="field"><label>Cliente</label><input v-model="customerFilter" placeholder="Nombre, DNI/CUIT o teléfono"></div><div class="field"><label>Desde</label><input v-model="dateFrom" type="date"></div><div class="field"><label>Hasta</label><input v-model="dateTo" type="date"></div><div class="filter-actions"><button class="btn btn--primary" @click="applyFilters">Filtrar</button><button class="btn btn--ghost" @click="clearFilters">Limpiar filtros</button></div></div></div>
<div v-if="!selected" class="card work-orders-list"><table v-if="orders.length" class="table table--cards-mobile"><thead><tr><th>OT</th><th>Recepción</th><th>Cliente</th><th>Equipo</th><th>Falla informada</th><th>Estado</th></tr></thead><tbody><tr v-for="o in orders" :key="o.id" class="work-order-row" @click="open(o)"><td data-label="OT"><button type="button" class="work-order-link" :aria-label="`Abrir OT #${o.number}`" @click.stop="open(o)">#{{o.number}}</button></td><td data-label="Recepción">{{formatCompanyDate(o.received_at)}}</td><td data-label="Cliente">{{o.customer_name}}<div class="text-muted">{{o.customer_phone||"—"}}</div></td><td data-label="Equipo">{{o.equipment_label}}<div class="text-muted">{{o.serial_number||"Sin serie"}}</div></td><td data-label="Falla"><span class="fault-clamp" :title="o.reported_fault">{{o.reported_fault}}</span></td><td data-label="Estado"><span class="status-chip" :style="{'--dot':o.status_color}">{{o.status_name}}</span></td></tr></tbody></table><div v-else class="empty-state">Todavía no hay órdenes de trabajo en esta empresa.</div></div>
<div v-if="!selected && total>0" class="card pagination-bar"><span>{{firstResult}}–{{lastResult}} de {{total}}</span><div class="pagination-actions"><label>Por página <select v-model.number="pageSize" @change="filtersChanged"><option :value="5">5</option><option :value="10">10</option><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option></select></label><button class="btn btn--ghost btn--sm" :disabled="page<=1" @click="changePage(page-1)">← Anterior</button><strong>{{page}} / {{totalPages}}</strong><button class="btn btn--ghost btn--sm" :disabled="page>=totalPages" @click="changePage(page+1)">Siguiente →</button></div></div>
<div v-if="selected" class="order-detail-shell"><button type="button" class="btn btn--ghost order-detail-back no-print" @click="closeOrder">← Volver a órdenes</button><div class="card receipt"><div class="flex flex--between order-head"><div><h2 class="order-head__title">OT #{{selected.number}}</h2><p class="text-secondary order-head__sub">{{selected.customer_name}} · {{selected.equipment_label}}</p></div><div class="toolbar no-print"><div class="status-picker"><button type="button" class="status-picker__trigger" :style="{borderColor:(currentStatus?.color||selected.status_color)+'88'}" :disabled="isFinal" :title="isFinal?'La OT está en un estado final (entregada) y no admite cambios.':undefined" @click="statusMenuOpen=!statusMenuOpen"><span class="status-dot" :style="{background:currentStatus?.color||selected.status_color}"></span><strong>{{currentStatus?.name||selected.status_name}}</strong><span>⌄</span></button><div v-if="statusMenuOpen" class="status-picker__menu"><button v-for="s in statuses.filter(x=>x.active)" :key="s.id" type="button" class="status-picker__option" :class="{'status-picker__option--active':s.id===selected.status_id}" @click="requestStatus(s)"><span class="status-dot" :style="{background:s.color}"></span><span>{{s.name}}</span><small v-if="s.id===selected.status_id">Actual</small></button></div></div><button class="btn btn--ghost" @click="printReceipt">Imprimir comprobante</button></div></div>
<section class="receipt-print" aria-label="Comprobante de recepción">
  <header class="receipt-print__header">
    <div class="receipt-print__brand"><h1>{{session.activeCompany?.name||"Servicio técnico"}}</h1><p>Comprobante de recepción de equipo</p></div>
    <div class="receipt-print__number"><span>ORDEN DE TRABAJO</span><strong>#{{selected.number}}</strong><small>{{formatCompanyDate(selected.received_at)}}</small></div>
  </header>
  <div class="receipt-print__status"><span>Estado al imprimir</span><strong>{{selected.status_name}}</strong></div>
  <section class="receipt-print__section"><h2>Cliente y equipo</h2><div class="receipt-print__facts">
    <div><span>Cliente</span><strong>{{selected.customer_name}}</strong></div><div><span>Teléfono</span><strong>{{selected.customer_phone||"No informado"}}</strong></div>
    <div><span>Equipo</span><strong>{{selected.equipment_label}}</strong></div><div><span>N° de serie</span><strong>{{selected.serial_number||"No informado"}}</strong></div>
  </div></section>
  <section class="receipt-print__section"><h2>Condiciones de recepción</h2>
    <div class="receipt-print__block"><span>Falla informada por el cliente</span><p>{{selected.reported_fault}}</p></div>
    <div class="receipt-print__twocol"><div class="receipt-print__block"><span>Estado físico</span><p>{{selected.physical_condition||"Sin observaciones"}}</p></div><div class="receipt-print__block"><span>Accesorios entregados</span><p>{{selected.accessories||"Ninguno informado"}}</p></div></div>
    <div v-if="selected.notes" class="receipt-print__block"><span>Observaciones</span><p>{{selected.notes}}</p></div>
  </section>
  <section class="receipt-print__section receipt-print__dates"><div><span>Recibido por</span><strong>{{selected.received_by_name}}</strong></div><div><span>Fecha de recepción</span><strong>{{formatCompanyDate(selected.received_at)}}</strong></div><div><span>Entrega estimada</span><strong>{{selected.expected_delivery_at?formatCompanyDate(selected.expected_delivery_at):"A confirmar"}}</strong></div></section>
  <p class="receipt-print__notice">Este comprobante documenta el equipo, su estado y los accesorios declarados al momento de la recepción. Conserve el número de orden para futuras consultas.</p>
  <footer class="receipt-print__signatures"><div><span>Firma / conformidad del cliente</span></div><div><span>Firma / sello del servicio técnico</span></div></footer>
  <div class="receipt-print__footer"><strong>OT #{{selected.number}}</strong><span>{{session.activeCompany?.name||"Servicio técnico"}}</span></div>
</section>
<div class="order-layout no-print">
<aside class="order-summary">
  <section class="summary-block"><h3>Cliente y equipo</h3><dl class="facts"><div><dt>Cliente</dt><dd>{{selected.customer_name}}<small class="text-muted">{{selected.customer_phone||"Sin teléfono"}}</small></dd></div><div><dt>Equipo</dt><dd>{{selected.equipment_label}}<small class="text-muted">{{selected.serial_number||"Sin serie"}}</small></dd></div></dl></section>
  <section class="summary-block"><h3>Recepción</h3><dl class="facts"><div><dt>Falla informada</dt><dd>{{selected.reported_fault}}</dd></div><div><dt>Estado físico</dt><dd>{{selected.physical_condition||"Sin observaciones"}}</dd></div><div><dt>Accesorios</dt><dd>{{selected.accessories||"Ninguno informado"}}</dd></div><div v-if="selected.notes"><dt>Observaciones</dt><dd>{{selected.notes}}</dd></div><div><dt>Recibió</dt><dd>{{selected.received_by_name}}</dd></div></dl></section>
  <section class="summary-block"><h3>Fechas</h3><div class="lifecycle-card"><div><span class="text-muted">Recepción</span><strong>{{formatCompanyDate(selected.received_at)}}</strong></div><div><span class="text-muted">Entrega prevista</span><div class="expected-editor no-print"><input v-model="expectedDeliveryInput" type="datetime-local" :disabled="isFinal"><button class="btn btn--ghost btn--sm" :disabled="isFinal" @click="saveExpectedDelivery">Guardar</button></div><strong class="print-only">{{selected.expected_delivery_at?formatCompanyDate(selected.expected_delivery_at):"Sin definir"}}</strong></div><div><span class="text-muted">Finalización técnica</span><strong>{{selected.completed_at?formatCompanyDate(selected.completed_at):"Pendiente"}}</strong></div><div><span class="text-muted">Entrega real</span><strong>{{selected.delivered_at?formatCompanyDate(selected.delivered_at):"Pendiente"}}</strong></div></div></section>
  <section class="summary-block area-block"><h3>Garantía y liquidación</h3><div v-if="selected.work_area_name" class="area-detail"><div><span class="text-muted">Área</span><strong>{{selected.work_area_name}}</strong></div><div><span class="text-muted">Garantía</span><strong>{{selected.warranty_label||"—"}}</strong></div><div><span class="text-muted">Se liquida a</span><strong v-if="selected.billing_customer_name">{{selected.billing_customer_name}}</strong><strong v-else class="area-detail__warn">Ninguna empresa: esta OT no entra al cierre</strong></div></div><p v-else class="text-secondary">Esta orden no tiene área de trabajo: no tiene garantía asignada y no entra al cierre a marcas.</p><div v-if="session.hasPermission('work_orders.manage')&&!isFinal" class="area-edit"><WorkAreaPicker v-model="areaOrdenId" placeholder="Buscar marca o política…" @change="p=>areaOrdenCoincide=p.coincide"/><button class="btn btn--primary btn--sm" type="button" :disabled="guardandoArea||!areaOrdenCoincide||!areaCambiada" @click="guardarArea">{{guardandoArea?"Guardando…":"Guardar"}}</button></div></section>
  <section class="summary-block"><h3>Técnicos asignados</h3><p v-if="!selected.technicians||!selected.technicians.length" class="text-secondary">Todavía no hay un técnico asignado a esta OT.</p><div v-else class="technician-chips"><span v-for="t in selected.technicians" :key="t.id" class="technician-chip" :class="{'technician-chip--inactive':!t.active}"><strong>{{t.name}}</strong><span v-if="!t.active" class="technician-chip__state">Inactivo</span><button v-if="session.hasPermission('work_orders.manage')&&!isFinal" type="button" class="technician-chip__remove" :title="'Quitar a '+t.name" @click="unassignTechnician(t)">×</button></span></div><div v-if="session.hasPermission('work_orders.manage')&&!isFinal" class="technician-assign"><input v-model="technicianQuery" placeholder="Agregar un técnico…" autocomplete="off" aria-label="Agregar un técnico" @focus="technicianOpen=true" @input="technicianOpen=true"><div v-if="technicianOpen" class="customer-picker__menu"><button v-for="t in tecnicosDisponibles" :key="t.id" type="button" class="customer-picker__option" @click="assignTechnician(t)"><strong>{{t.name}}</strong><span>Asignar</span></button><p v-if="!tecnicosDisponibles.length" class="customer-picker__option customer-picker__create">No hay técnicos activos para asignar.</p></div></div></section>
</aside>
<div class="order-main">
<ol class="workflow">
  <li v-if="diagnosisEnabled" class="workflow-step" :class="{'workflow-step--current':currentStep==='diagnosis'}"><div class="workflow-step__head"><div><h3>Diagnóstico técnico</h3><p v-if="diagnosis" class="diagnosis-text">{{diagnosis.diagnosis}}</p><p v-else class="text-secondary">Todavía no se registró el diagnóstico técnico.</p><small v-if="diagnosis" class="text-muted">{{formatCompanyDate(diagnosis.updated_at||diagnosis.diagnosed_at)}}</small></div><button :class="currentStep==='diagnosis'?'btn btn--primary':'btn btn--ghost'" :disabled="isFinal" :title="isFinal?'La OT está en un estado final (entregada) y no admite diagnóstico.':undefined" @click="openDiagnosisEditor">{{diagnosis?(diagnosis.is_open?'Ver / editar diagnóstico':'Reabrir diagnóstico'):'Registrar diagnóstico'}}</button></div></li>
  <li v-if="budgetEnabled" class="workflow-step" :class="{'workflow-step--current':currentStep==='quote'}"><div class="workflow-step__head"><div><h3>Presupuesto</h3><template v-if="quotes.length"><p><strong>Presupuesto v{{quotes[0].version}}</strong> · $ {{Number(quotes[0].total).toLocaleString('es-AR',{minimumFractionDigits:2})}}</p><small class="text-muted">{{formatCompanyDate(quotes[0].created_at)}}</small></template><p v-else class="text-secondary">Todavía no se generó un presupuesto.</p></div><button :class="currentStep==='quote'&&!quotes.some(q=>q.status==='PENDING_APPROVAL')?'btn btn--primary':'btn btn--ghost'" :disabled="(diagnosisEnabled&&!diagnosis) || isFinal" :title="isFinal?'La OT está en un estado final (entregada) y no admite presupuestos.':undefined" @click="openQuoteEditor">{{quotes.length?'Crear nueva versión':'Crear presupuesto'}}</button></div><div v-for="q in quotes" :key="q.id" class="quote-card"><div><strong>Presupuesto v{{q.version}}</strong><small>{{formatCompanyDate(q.created_at)}}</small></div><strong>$ {{Number(q.total).toLocaleString('es-AR',{minimumFractionDigits:2})}}</strong><div class="toolbar"><button class="btn btn--ghost btn--sm" @click="printBudget(q)">Imprimir</button><button v-if="!q.sent_at&&q.status!=='REJECTED'" class="btn btn--ghost btn--sm" :disabled="isFinal" @click="sendQuote(q)">Enviar</button><button v-if="q.status==='PENDING_APPROVAL'" class="btn btn--primary btn--sm" :disabled="isFinal" @click="askQuoteDecision(q,'approve')">Aprobar</button><button v-if="q.status==='PENDING_APPROVAL'" class="btn btn--ghost btn--sm" :disabled="isFinal" @click="askQuoteDecision(q,'reject')">Rechazar</button><span class="text-muted">{{q.status==='APPROVED'?'Aprobado':q.status==='REJECTED'?'Rechazado':q.status==='PENDING_APPROVAL'?'Esperando aprobación':q.sent_at?'Enviado':'Generado'}}</span></div></div></li>
  <li class="workflow-step" :class="{'workflow-step--current':currentStep==='execution'}"><h3>Trabajo realizado y repuestos</h3><p v-if="!execution.length" class="text-secondary">Todavía no se registró la ejecución real de esta OT.</p><div v-for="it in execution" :key="it.id" class="execution-row"><strong>{{it.item_type==='PART'?'Repuesto':'Trabajo'}}</strong><span>{{it.description}}</span><span>{{it.quantity}}</span><small>{{formatCompanyDate(it.created_at)}}</small></div><div v-if="!isFinal" class="execution-editor-head" aria-hidden="true"><span>Tipo</span><span>Descripción</span><span>Cant.</span><span v-if="showInternalCosts">Costo</span><span>Precio</span><span></span></div><div v-if="!isFinal" class="execution-editor"><select v-model="executionForm.item_type" aria-label="Tipo" @change="onExecutionTypeChange"><option value="LABOR">Trabajo</option><option value="PART">Repuesto</option></select><SparePartPicker v-if="executionForm.item_type==='PART'" v-model="executionForm.description" @change="onExecutionPart" @availability="catalogoDisponible=$event" placeholder="Buscar repuesto por código, descripción, rubro o marca…"/><input v-else v-model="executionForm.description" aria-label="Descripción" placeholder="Qué se hizo"><input v-model.number="executionForm.quantity" type="number" min=".001" step=".001" aria-label="Cantidad" title="Cantidad"><input v-if="showInternalCosts" v-model.number="executionForm.unit_cost" type="number" min="0" step=".01" aria-label="Costo interno" placeholder="Costo"><input v-model.number="executionForm.unit_price" type="number" min="0" step=".01" aria-label="Precio al cliente" placeholder="Precio"><button :class="currentStep==='execution'?'btn btn--primary btn--sm':'btn btn--ghost btn--sm'" :disabled="!executionForm.description.trim()||(catalogoDisponible===true&&executionForm.item_type==='PART'&&!executionForm.part)" @click="addExecution">Registrar</button></div></li>
  <li v-if="finalTestsEnabled" class="workflow-step" :class="{'workflow-step--current':currentStep==='tests'}"><h3>Pruebas finales</h3><p v-if="!finalTests.length" class="text-secondary">Todavía no se registraron pruebas finales.</p><div v-for="t in finalTests" :key="t.id" class="final-test-row"><strong>{{t.passed?'✓ Satisfactoria':'✕ No satisfactoria'}}</strong><span>{{t.notes||'Sin observaciones'}}</span><small>{{formatCompanyDate(t.tested_at)}}</small></div><div v-if="!isFinal" class="final-test-editor"><select v-model="finalTestForm.passed"><option :value="true">Satisfactoria</option><option :value="false">No satisfactoria</option></select><input v-model="finalTestForm.notes" placeholder="Observaciones de la prueba"><button :class="currentStep==='tests'?'btn btn--primary btn--sm':'btn btn--ghost btn--sm'" @click="addFinalTest">Registrar prueba</button></div></li>
</ol>
<section class="workshop-panel"><h3>Documentos de la orden</h3><div class="doc-panel"><div v-for="d in orderDocuments" :key="d.id" class="doc-item"><div class="doc-item__main"><strong>{{ d.original_filename }}</strong><small class="text-muted">{{ d.mime_type }} · {{ formatBytes(d.size_bytes) }} · {{ formatDocDate(d.created_at) }}</small></div><div class="doc-item__actions"><a class="btn btn--ghost btn--sm" :href="`/api/v1/documents/${d.id}/download`" :download="d.original_filename">Ver</a><button v-if="canManageWorkOrders" class="btn btn--ghost btn--sm" @click="deleteOrderDocument(d)">Dar de baja</button></div></div><p v-if="!orderDocuments.length" class="text-muted doc-empty">Esta orden todavía no tiene fotos ni PDF.</p><label v-if="canManageWorkOrders" class="btn btn--ghost btn--sm doc-upload"><input type="file" multiple hidden :disabled="uploadingDocs" @change="pickOrderFiles">{{ uploadingDocs?"Subiendo…":"+ Adjuntar foto o PDF" }}</label></div></section>
<details class="workshop-panel order-collapsible"><summary>Avisos al cliente <span class="text-muted">({{notifications.length}})</span></summary><template v-if="notifications.length"><div v-for="n in notifications" :key="n.id" class="notification-row"><span class="notification-channel">{{ n.channel==="WHATSAPP"?"WhatsApp":"Email" }}</span><span class="notification-recipient">{{ n.recipient||"sin destinatario" }}</span><span class="status-pill" :class="'notification-status--'+n.status">{{ notificationLabels[n.status]||n.status }}</span><small class="text-muted">{{ formatCompanyDate(n.created_at) }}<template v-if="n.attempts>1"> · {{ n.attempts }} intentos</template></small><small v-if="n.error" class="notification-error">{{ n.error }}</small><div class="notification-acciones" v-if="(n.status==='PENDING'||n.status==='FAILED')&&canManageWorkOrders"><button type="button" class="btn btn--ghost btn--sm" @click="toggleMensaje(n.id)">{{ mensajeAbierto===n.id?"Ocultar mensaje":"Ver mensaje" }}</button><button type="button" class="btn btn--primary btn--sm" :disabled="sendingNotification!==null" @click="sendNotification(n)">{{ sendingNotification===n.id?"Enviando…":n.status==="FAILED"?"Reintentar":"Enviar ahora" }}</button></div><pre v-if="mensajeAbierto===n.id" class="notification-body">{{ n.body }}</pre><div v-if="n.provider_message_id" class="notification-ref"><span>ID en la gateway: <code>{{ n.provider_message_id }}</code></span><button type="button" class="btn btn--ghost btn--sm" @click="copiarRef(n.provider_message_id)">Copiar</button></div></div></template><p v-else class="text-secondary">Este estado no tiene avisos al cliente configurados, o todavía no se envió ninguno.</p></details>
<details class="workshop-panel order-collapsible"><summary>Historial <span class="text-muted">({{events.length}})</span></summary><div v-for="e in events" :key="e.id" class="timeline"><strong>{{etiquetaEvento(e)}}</strong><span>{{e.detail}} · {{e.user_name}} · {{formatCompanyDate(e.created_at)}}</span></div></details>
</div>
</div>
</div>
</div>
<div v-if="showReopenDiagnosis" class="modal-backdrop workshop-modal-layer"><div class="modal card confirm-status-modal"><h2>Reabrir diagnóstico</h2><p class="text-secondary">El presupuesto existente conservará una copia del diagnóstico anterior. El próximo presupuesto será una nueva versión.</p><div class="field"><label>Motivo *</label><textarea v-model="reopenReason" rows="3" placeholder="¿Por qué se modifica el diagnóstico?"></textarea></div><div class="flex flex--between"><button class="btn btn--ghost" @click="showReopenDiagnosis=false">Cancelar</button><button class="btn btn--primary" :disabled="reopenReason.trim().length<3" @click="reopenDiagnosis">Reabrir</button></div></div></div>
<div v-if="showPreview" class="modal-backdrop workshop-modal-layer"><div class="modal card confirm-status-modal"><div class="flex flex--between"><h2>Avisar al cliente</h2><button type="button" class="btn btn--ghost" @click="showPreview=false">×</button></div><p class="text-secondary">Vas a pasar la OT a <strong>{{pendingStatus?.name}}</strong>. Revisa a quien le llega y que dice antes de enviar.</p><div v-if="previewLoading" class="text-muted">Preparando el aviso…</div><template v-else><div class="preview-list"><div v-for="it in preview" :key="it.channel" class="preview-item" :class="{ 'preview-item--skipped': it.skipped }"><div class="preview-item__head"><strong>{{it.channel==="WHATSAPP"?"WhatsApp":"Email"}}</strong><span v-if="(it.recipient||'').trim()">{{it.recipient}}</span><span v-else class="text-muted">sin destinatario</span></div><div class="field"><label>Numero o email de destino</label><input v-model="it.recipient" :placeholder="it.channel==='WHATSAPP'?'Completar el numero a mano para enviar':'Completar el email a mano para enviar'"></div><p v-if="!(it.recipient||'').trim()" class="preview-item__reason">No se va a enviar: {{it.reason}}</p><template v-else><div class="field"><label>Mensaje</label><textarea v-model="it.body" rows="4"></textarea></div><div class="field" v-if="it.subject!==null"><label>Asunto</label><input v-model="it.subject"></div></template></div></div><div class="flex flex--between" style="margin-top:18px"><button type="button" class="btn btn--ghost" @click="applyStatus()">Cambiar sin avisar</button><button type="button" class="btn btn--primary" @click="confirmWithNotice">Cambiar y avisar</button></div></template></div></div><div v-if="decisionQuote&&decisionAction" class="modal-backdrop workshop-modal-layer"><div class="modal card confirm-status-modal"><h2>{{decisionAction==='approve'?'Aprobar presupuesto':'Rechazar presupuesto'}}</h2><p>Presupuesto v{{decisionQuote.version}} · $ {{Number(decisionQuote.total).toLocaleString('es-AR',{minimumFractionDigits:2})}}</p><div class="field"><label>{{decisionAction==='reject'?'Motivo del rechazo *':'Observación (opcional)'}}</label><textarea v-model="decisionNote" rows="3"></textarea></div><div class="flex flex--between"><button class="btn btn--ghost" @click="decisionQuote=null;decisionAction=null">Cancelar</button><button class="btn btn--primary" :disabled="decisionAction==='reject'&&!decisionNote.trim()" @click="confirmQuoteDecision">Confirmar</button></div></div></div>
<div v-if="showDiagnosisModal" class="modal-backdrop workshop-modal-layer"><div class="modal card workshop-modal"><div class="flex flex--between"><h2>{{diagnosis?'Diagnóstico técnico':'Registrar diagnóstico'}}</h2><button class="btn btn--ghost" @click="showDiagnosisModal=false">×</button></div><div class="field"><label>Diagnóstico *</label><textarea v-model="diagnosisForm.diagnosis" rows="5"></textarea></div><div class="field"><label>Notas técnicas internas</label><textarea v-model="diagnosisForm.technical_notes" rows="3"></textarea></div><div class="flex flex--between"><button class="btn btn--ghost" @click="showDiagnosisModal=false">Cancelar</button><button class="btn btn--primary" :disabled="!diagnosisForm.diagnosis.trim()" @click="saveDiagnosis">Guardar diagnóstico</button></div></div></div>
<div v-if="showQuoteModal" class="modal-backdrop workshop-modal-layer"><div class="modal card quote-modal"><div class="flex flex--between"><div><h2>{{quotes.length?'Nueva versión de presupuesto':'Crear presupuesto'}}</h2><p class="text-secondary">OT #{{selected?.number}} · {{selected?.customer_name}}</p></div><button class="btn btn--ghost" @click="showQuoteModal=false">×</button></div><div class="quote-editor-head"><span>Tipo</span><span>Descripción</span><span>Cant.</span><span v-if="showInternalCosts">Costo interno</span><span>Precio cliente</span><span></span></div><div v-for="(item,i) in quoteItems" :key="i" class="quote-line"><select v-model="item.item_type" @change="onQuoteTypeChange(i)"><option value="PART">Repuesto</option><option value="LABOR">Mano de obra</option></select><SparePartPicker v-if="item.item_type==='PART'" v-model="item.description" @change="onQuotePart(i,$event)" @availability="catalogoDisponible=$event" placeholder="Buscar repuesto por código, descripción, rubro o marca…"/><input v-else v-model="item.description" placeholder="Descripción"><input v-model.number="item.quantity" type="number" min=".001" step=".001"><input v-if="showInternalCosts" v-model.number="item.unit_cost" type="number" min="0" step=".01"><input v-else v-model.number="item.unit_cost" type="hidden"><input v-model.number="item.unit_price" type="number" min="0" step=".01" placeholder="Automático"><button class="btn btn--ghost btn--sm" @click="removeQuoteItem(i)">×</button></div><div class="toolbar"><button class="btn btn--ghost btn--sm" @click="addQuoteItem('PART')">+ Repuesto</button><button class="btn btn--ghost btn--sm" @click="addQuoteItem('LABOR')">+ Mano de obra</button></div><div class="field"><label>Observaciones para el cliente</label><textarea v-model="quoteNotes" rows="3"></textarea></div><div class="flex flex--between"><button class="btn btn--ghost" @click="showQuoteModal=false">Cancelar</button><button class="btn btn--primary" @click="createQuote">Generar presupuesto</button></div></div></div>
<div v-if="printQuote&&selected" class="budget-print"><h1>Presupuesto</h1><p><strong>OT #{{selected.number}} · Presupuesto v{{printQuote.version}}</strong></p><p>{{selected.customer_name}} · {{selected.equipment_label}}</p><p><strong>Diagnóstico:</strong> {{printQuote.diagnosis_snapshot||diagnosis?.diagnosis||'—'}}</p><table><thead><tr><th>Descripción</th><th>Cant.</th><th>Precio</th><th>Total</th></tr></thead><tbody><tr v-for="it in printQuote.items" :key="it.id"><td>{{it.description}}</td><td>{{it.quantity}}</td><td>$ {{Number(it.unit_price).toLocaleString('es-AR',{minimumFractionDigits:2})}}</td><td>$ {{Number(it.line_total).toLocaleString('es-AR',{minimumFractionDigits:2})}}</td></tr></tbody></table><p v-if="printQuote.notes"><strong>Observaciones:</strong> {{printQuote.notes}}</p><h2>Total: $ {{Number(printQuote.total).toLocaleString('es-AR',{minimumFractionDigits:2})}}</h2></div>
<div v-if="pendingStatus && selected" class="modal-backdrop confirm-status-layer"><div class="modal card confirm-status-modal"><h2>Confirmar cambio de estado</h2><p class="text-secondary">La OT #{{selected.number}} cambiará de <strong>{{selected.status_name}}</strong> a:</p><div class="status-confirm-target" :style="{borderColor:pendingStatus.color+'88'}"><span class="status-dot" :style="{background:pendingStatus.color}"></span><strong>{{pendingStatus.name}}</strong></div><div class="field"><label>Observación / motivo (opcional)</label><textarea v-model="statusNote" rows="3" placeholder="Ej.: diagnóstico iniciado, cliente avisado, equipo derivado…"></textarea></div><div v-if="pendingStatus.marks_completed||pendingStatus.marks_delivered" class="status-consequence"><strong>Este cambio también:</strong><span v-if="pendingStatus.marks_completed">• registrará la fecha de finalización técnica.</span><span v-if="pendingStatus.marks_delivered">• registrará la fecha de entrega real al cliente.</span></div><p class="text-muted">El cambio y esta observación quedarán registrados en el historial. Si luego se revierte el estado, las fechas registradas se conservan para no perder trazabilidad.</p><div class="flex flex--between"><button type="button" class="btn btn--ghost" @click="cancelStatus">Cancelar</button><button type="button" class="btn btn--primary" @click="confirmStatus">Confirmar cambio</button></div></div></div>
<div v-if="showStatuses" class="modal-backdrop"><div class="modal card reception-modal"><div class="flex flex--between"><h2>Estados de órdenes</h2><button class="btn btn--ghost" @click="showStatuses=false">×</button></div><p class="text-secondary">Los estados son propios de esta empresa. Elegí sus colores acá; no se crean desde una OT.</p><div v-for="st in statuses" :key="st.id" class="status-row"><input v-model="st.color" type="color"><strong>{{st.name}}</strong><span v-if="st.is_initial" class="text-muted">Inicial</span><span v-if="st.is_final" class="text-muted">Final</span><button class="btn btn--ghost btn--sm" @click="saveStatus(st)">Guardar</button></div></div></div>
<div v-if="showReception" class="modal-backdrop"><div class="modal card reception-modal"><div class="flex flex--between"><h2>Nueva recepción</h2><button class="btn btn--ghost" @click="showReception=false">×</button></div><form @submit.prevent="save"><div class="field customer-picker"><label>Cliente *</label><div class="customer-picker__input"><input v-model="customerQuery" placeholder="Buscar por nombre, DNI/CUIT o teléfono…" autocomplete="off" required @focus="findCustomers" @input="form.customer_id=0;equipment=[];findCustomers()"><button type="button" class="btn btn--ghost btn--sm" @click="openQuickCustomer">+ Nuevo</button></div><div v-if="customerOpen" class="customer-picker__menu"><button v-for="c in customers" :key="c.id" type="button" class="customer-picker__option" @click="chooseCustomer(c)"><strong>{{c.name}}</strong><span>{{c.phone||c.whatsapp||"Sin teléfono"}}</span></button><button type="button" class="customer-picker__option customer-picker__create" @click="openQuickCustomer">+ Crear cliente{{customerQuery.trim()?' “'+customerQuery.trim()+'”':''}}</button></div></div><div class="field"><label>Equipo *</label><div class="customer-picker__input"><select v-model.number="form.equipment_id" required :disabled="!form.customer_id"><option :value="0" disabled>Seleccionar equipo</option><option v-for="e in equipment" :key="e.id" :value="e.id">{{[e.category_name,e.brand,e.model,e.serial_number].filter(Boolean).join(" · ")}}</option></select><button type="button" class="btn btn--ghost btn--sm" :disabled="!form.customer_id" @click="openQuickEquipment">+ Nuevo</button></div><small class="text-muted">{{form.customer_id?"Seleccioná un equipo existente o crealo sin salir de la recepción.":"Primero seleccioná o creá el cliente."}}</small></div><div class="field"><label>Área / política (garantía y empresa a liquidar)</label><WorkAreaPicker v-model="form.work_area_id" placeholder="Buscar marca o política…" @change="p=>areaCoincide=p.coincide"/><small class="text-muted">De esta área salen la garantía de la orden y a quién se le liquida. Sin área, la orden no entra al cierre a marcas.</small></div><div class="field technician-picker"><label>Técnico (opcional)</label><div class="customer-picker__input"><input v-model="technicianQuery" placeholder="Buscar por nombre…" autocomplete="off" @focus="technicianOpen=true" @input="form.technician_id=0;technicianOpen=true"><button v-if="form.technician_id" type="button" class="btn btn--ghost btn--sm" @click="form.technician_id=0;technicianQuery=''">Quitar</button></div><div v-if="technicianOpen" class="customer-picker__menu"><button v-for="t in tecnicosAsignables" :key="t.id" type="button" class="customer-picker__option" @click="chooseTechnician(t)"><strong>{{t.name}}</strong></button><p v-if="!tecnicosAsignables.length" class="customer-picker__option customer-picker__create">No hay técnicos activos que coincidan. Cargalos desde el maestro de técnicos.</p></div><small class="text-muted">Se puede dejar sin asignar y hacerlo más adelante, con la OT abierta en el taller. Solo se ofrecen los técnicos activos del maestro.</small></div><div class="field"><label>Falla informada por el cliente *</label><textarea v-model="form.reported_fault" rows="3" required/></div><div class="field__row"><div class="field"><label>Estado físico</label><textarea v-model="form.physical_condition" rows="2"/></div><div class="field"><label>Accesorios entregados</label><textarea v-model="form.accessories" rows="2"/></div></div><div class="field"><label>Observaciones</label><textarea v-model="form.notes" rows="2"/></div><div class="field"><label>Fotos o PDF del equipo (opcional)</label><label class="btn btn--ghost doc-upload"><input type="file" multiple hidden @change="pickReceptionFiles">Elegir archivos</label><ul v-if="receptionFiles.length" class="file-pick-list"><li v-for="(f,i) in receptionFiles" :key="f.name+i"><span>{{f.name}} · {{formatBytes(f.size)}}</span><button type="button" class="btn btn--ghost btn--sm" @click="dropReceptionFile(i)">Quitar</button></li></ul><p v-else class="text-muted file-pick-help">Se adjuntan a la orden y quedan en el historial del equipo.</p></div><div class="flex flex--between" style="margin-top:18px"><button type="button" class="btn btn--ghost" @click="showReception=false">Cancelar</button><button class="btn btn--primary">Generar OT</button></div></form></div></div>
<div v-if="showQuickEquipment" class="modal-backdrop quick-customer-layer"><div class="modal card reception-modal"><div class="flex flex--between"><h2>Nuevo equipo · {{customerQuery}}</h2><button class="btn btn--ghost" type="button" @click="showQuickEquipment=false">×</button></div><form @submit.prevent="saveQuickEquipment"><div class="field__row"><div class="field customer-picker"><label>Tipo / categoría *</label><input v-model="categoryQuery" placeholder="Buscar o crear categoría…" autocomplete="off" required @focus="findCategories" @input="quickEquipment.category_id=0;findCategories()"><div v-if="categoryOpen && categoryQuery.trim()" class="customer-picker__menu"><button v-for="cat in categories" :key="cat.id" type="button" class="customer-picker__option" @click="chooseCategory(cat)"><strong>{{cat.name}}</strong></button><button v-if="!exactCategory()" type="button" class="customer-picker__option customer-picker__create" @click="createCategory">+ Crear “{{categoryQuery.trim()}}”</button></div></div><div class="field"><label>Marca</label><input v-model="quickEquipment.brand"></div></div><div class="field__row"><div class="field"><label>Modelo</label><input v-model="quickEquipment.model"></div><div class="field"><label>N° de serie</label><input v-model="quickEquipment.serial_number"></div></div><div class="field"><label>Descripción</label><input v-model="quickEquipment.description"></div><div class="field"><label>Observaciones</label><textarea v-model="quickEquipment.notes" rows="2"/></div><div class="flex flex--between" style="margin-top:18px"><button type="button" class="btn btn--ghost" @click="showQuickEquipment=false">Cancelar</button><button class="btn btn--primary">Crear y seleccionar</button></div></form></div></div>
<div v-if="showQuickCustomer" class="modal-backdrop quick-customer-layer"><div class="modal card reception-modal"><div class="flex flex--between"><h2>Nuevo cliente</h2><button class="btn btn--ghost" type="button" @click="showQuickCustomer=false">×</button></div><form @submit.prevent="saveQuickCustomer"><div class="field__row"><div class="field"><label>Tipo</label><select v-model="quickCustomer.customer_type"><option value="PERSON">Persona</option><option value="COMPANY">Empresa</option></select></div><div class="field"><label>Nombre / Razón social *</label><input v-model="quickCustomer.name" required autofocus></div></div><div class="field__row"><div class="field"><label>DNI / CUIT</label><input v-model="quickCustomer.document"></div><div class="field"><label>Teléfono</label><input v-model="quickCustomer.phone"></div></div><div class="field__row"><div class="field"><label>WhatsApp</label><input v-model="quickCustomer.whatsapp"></div><div class="field"><label>Email</label><input v-model="quickCustomer.email" type="email"></div></div><div class="field"><label>Domicilio</label><input v-model="quickCustomer.address"></div><div class="flex flex--between" style="margin-top:18px"><button type="button" class="btn btn--ghost" @click="showQuickCustomer=false">Cancelar</button><button class="btn btn--primary">Crear y seleccionar</button></div></form></div></div>
</template>
<style scoped>
.technician-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.technician-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:rgba(59,130,246,.14);color:#3B82F6;border:1px solid rgba(59,130,246,.4);font-size:13px}
.technician-chip--inactive{background:rgba(100,116,139,.16);color:#94A3B8;border-color:rgba(100,116,139,.45)}
.technician-chip__state{font-size:11px;letter-spacing:.06em;text-transform:uppercase;opacity:.85}
.technician-chip__remove{border:0;background:transparent;color:inherit;cursor:pointer;font-size:16px;line-height:1;padding:0 0 2px;opacity:.7}
.technician-chip__remove:hover{opacity:1}
.technician-assign{position:relative;margin-top:10px;max-width:320px}
.technician-assign input{width:100%;background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);padding:10px 12px;color:var(--color-text-primary);outline:none;transition:border .18s ease,background .18s ease}
.technician-assign input:focus{border-color:var(--color-primary);background:var(--color-surface-elevated)}
.technician-assign input::placeholder{color:var(--color-text-muted)}
.technician-assign .customer-picker__menu{top:calc(100% + 4px);left:0;right:0}
/* La garantia y la empresa a liquidar de la orden: tres datos en linea, para que se
   vean de un vistazo sin abrir el maestro de areas. */
.area-detail{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:8px}
.area-detail>div{display:flex;flex-direction:column;gap:4px;min-width:0}
.area-detail .text-muted{font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.area-detail__warn{color:var(--color-warning-text,#fbbf24)}
.area-edit{display:flex;gap:8px;align-items:flex-start;margin-top:12px;max-width:460px}
.area-edit>*:first-child{flex:1;min-width:0}
@media(max-width:700px){.area-detail{grid-template-columns:1fr;gap:8px}.area-edit{flex-direction:column;align-items:stretch}}
/* El desplegable del técnico de la recepción necesita su propio contenedor posicionado:
   sin esto el menu se ancla al .modal-backdrop (fixed, toda la pantalla) y aparece en el
   borde inferior, lejos del campo: se ve la lista pero no se puede hacer clic en ella. */
.technician-picker{position:relative}
.technician-picker .customer-picker__menu{top:calc(100% + 4px);left:0;right:0}
.receipt-print{display:none}
@page{size:A4;margin:12mm}
@media print{
  body.printing-receipt *{visibility:hidden!important}
  body.printing-receipt .receipt-print,body.printing-receipt .receipt-print *{visibility:visible!important}
  body.printing-receipt .receipt-print{display:block!important;position:fixed;left:0;top:0;width:100%;height:auto;background:#fff;color:#111827;font-family:Arial,Helvetica,sans-serif;font-size:10pt;line-height:1.3;box-sizing:border-box}
  .receipt-print__header{display:grid;grid-template-columns:1fr auto;gap:24px;align-items:start;padding-bottom:16px;border-bottom:3px solid #111827}
  .receipt-print__eyebrow{margin:0 0 4px;text-transform:uppercase;letter-spacing:.12em;font-size:8pt;font-weight:700;color:#475569}.receipt-print__header h1{font-size:19pt;margin:0 0 4px;color:#111827}.receipt-print__header p{margin:0;color:#475569}
  .receipt-print__number{text-align:right;border:1.5px solid #111827;border-radius:8px;padding:10px 14px;min-width:150px}.receipt-print__number span,.receipt-print__number small{display:block;font-size:8pt;color:#475569}.receipt-print__number strong{display:block;font-size:24pt;line-height:1.05;margin:3px 0 5px}
  .receipt-print__status{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;margin:12px 0;background:#f1f5f9;border-left:4px solid #334155}.receipt-print__status span{font-size:8pt;text-transform:uppercase;letter-spacing:.08em;color:#64748b}
  .receipt-print__section{margin-top:16px;break-inside:avoid}.receipt-print__section h2{font-size:10pt;text-transform:uppercase;letter-spacing:.08em;margin:0 0 8px;padding-bottom:5px;border-bottom:1px solid #cbd5e1}
  .receipt-print__facts{display:grid;grid-template-columns:1fr 1fr;gap:9px 20px}.receipt-print__facts div,.receipt-print__dates div{display:flex;flex-direction:column;gap:2px}.receipt-print__facts span,.receipt-print__dates span,.receipt-print__block>span{font-size:8pt;text-transform:uppercase;color:#64748b;font-weight:700;letter-spacing:.04em}
  .receipt-print__block{border:1px solid #cbd5e1;border-radius:6px;padding:9px 11px;margin-bottom:8px;min-height:38px}.receipt-print__block p{margin:4px 0 0;white-space:pre-wrap}.receipt-print__twocol{display:grid;grid-template-columns:1fr 1fr;gap:8px}.receipt-print__dates{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;padding:10px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px}
  .receipt-print__notice{margin:14px 0 20px;padding:9px 11px;border:1px solid #cbd5e1;border-radius:6px;color:#475569;font-size:8.5pt}
  .receipt-print__signatures{display:grid;grid-template-columns:1fr 1fr;gap:40px;margin-top:28px;break-inside:avoid}.receipt-print__signatures div{height:38px;border-top:1px solid #64748b;padding-top:6px;text-align:center;color:#475569;font-size:8pt}
  .receipt-print__footer{display:flex;justify-content:space-between;margin-top:16px;padding-top:7px;border-top:1px solid #cbd5e1;color:#64748b;font-size:8pt}
}

.modal-backdrop{position:fixed;inset:0;z-index:100;background:rgba(2,6,23,.72);display:grid;place-items:center;padding:20px}.reception-modal{width:min(760px,100%);max-height:92vh;overflow:auto}.timeline{display:flex;flex-direction:column;border-left:2px solid rgba(96,165,250,.45);padding:6px 0 12px 14px}.timeline span{color:var(--text-secondary);margin-top:3px}@media print{body *{visibility:hidden}.receipt,.receipt *{visibility:visible}.receipt{position:absolute;inset:0;background:white;color:black;box-shadow:none}.no-print{display:none!important}}
.customer-picker{position:relative}.customer-picker__input{display:grid;grid-template-columns:1fr auto;gap:8px}.customer-picker__menu{position:absolute;z-index:30;top:100%;left:0;right:0;margin-top:6px;padding:6px;background:var(--surface,#152238);border:1px solid rgba(148,163,184,.25);border-radius:12px;box-shadow:0 18px 45px rgba(0,0,0,.35);max-height:260px;overflow:auto}.customer-picker__option{display:flex;width:100%;align-items:center;justify-content:space-between;gap:12px;text-align:left;padding:10px 12px;border:0;border-radius:8px;background:transparent;color:inherit;cursor:pointer}.customer-picker__option span{font-size:12px;color:var(--text-secondary)}.customer-picker__option:hover{background:rgba(59,130,246,.14)}.customer-picker__create{display:block;color:#60a5fa;font-weight:700;border-top:1px solid rgba(148,163,184,.15);margin-top:4px}.quick-customer-layer{z-index:120}
.status-picker{position:relative}.status-picker__trigger{display:flex;align-items:center;gap:9px;min-width:180px;justify-content:space-between;padding:9px 12px;border:1px solid;border-radius:12px;background:var(--color-surface);color:var(--color-text);cursor:pointer}.status-dot{width:10px;height:10px;min-width:10px;border-radius:50%;box-shadow:0 0 0 3px rgba(255,255,255,.05)}.status-picker__menu{position:absolute;right:0;top:calc(100% + 7px);z-index:60;min-width:230px;padding:6px;background:var(--color-surface);color:var(--color-text);border:1px solid var(--color-border);border-radius:12px;box-shadow:0 18px 45px rgba(0,0,0,.25)}.status-picker__option{display:grid;grid-template-columns:14px 1fr auto;align-items:center;gap:9px;width:100%;padding:10px;border:0;border-radius:8px;background:transparent;color:var(--color-text);text-align:left;cursor:pointer}.status-picker__option:hover{background:var(--color-surface-hover)}.status-picker__option--active{background:rgba(96,165,250,.1)}.status-picker__option small{color:var(--color-text-muted)}.confirm-status-layer{z-index:130}.confirm-status-modal{width:min(520px,100%)}.status-confirm-target{display:flex;align-items:center;gap:10px;margin:14px 0 18px;padding:13px 15px;border:1px solid;border-radius:12px;background:rgba(255,255,255,.025)}.lifecycle-card{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0;padding:14px;border:1px solid rgba(148,163,184,.15);border-radius:14px;background:rgba(255,255,255,.02)}.lifecycle-card>div{display:flex;flex-direction:column;gap:6px}.expected-editor{display:flex;gap:6px;align-items:center}.expected-editor input{min-width:0;background:var(--color-surface);color:var(--color-text);border:1px solid var(--color-border);color-scheme:light dark}.expected-editor input::-webkit-calendar-picker-indicator{opacity:.9;cursor:pointer}.expected-editor input::-webkit-datetime-edit,.expected-editor input::-webkit-datetime-edit-fields-wrapper,.expected-editor input::-webkit-datetime-edit-text,.expected-editor input::-webkit-datetime-edit-month-field,.expected-editor input::-webkit-datetime-edit-day-field,.expected-editor input::-webkit-datetime-edit-year-field,.expected-editor input::-webkit-datetime-edit-hour-field,.expected-editor input::-webkit-datetime-edit-minute-field,.expected-editor input::-webkit-datetime-edit-ampm-field{color:var(--color-text)}.print-only{display:none}.status-consequence{display:flex;flex-direction:column;gap:5px;padding:10px 12px;margin-bottom:12px;border-radius:10px;background:rgba(59,130,246,.09);color:var(--text-secondary)}@media(max-width:800px){.lifecycle-card{grid-template-columns:1fr 1fr}}@media(max-width:520px){.lifecycle-card{grid-template-columns:1fr}}@media print{.print-only{display:block!important}}.work-order-row{cursor:pointer}.work-order-link{border:0;background:none;padding:0;color:inherit;font:inherit;font-weight:700;cursor:pointer}.work-order-link:hover{text-decoration:underline}.work-order-link:focus-visible{outline:2px solid var(--color-primary);outline-offset:3px;border-radius:4px}.fault-clamp{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.status-pill{display:inline-flex;padding:4px 10px;border:1px solid;border-radius:999px;font-size:12px;font-weight:700}.status-row{display:grid;grid-template-columns:48px 1fr auto auto auto;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid rgba(148,163,184,.12)}.status-row input[type=color]{width:40px;height:32px;padding:2px;border-radius:8px}
.workshop-panel{padding:16px;border:1px solid rgba(148,163,184,.16);border-radius:14px;background:rgba(255,255,255,.02)}.workshop-panel h3{margin-top:0}.preview-list{display:flex;flex-direction:column;gap:14px;margin-top:12px}.preview-item{border:1px solid var(--border,#263a57);border-radius:12px;padding:12px}.preview-item--skipped{opacity:.75}.preview-item__head{display:flex;justify-content:space-between;gap:10px;font-size:13px;margin-bottom:8px}.preview-item__reason{margin:0;font-size:12px;color:var(--color-warning-text)}.preview-item label{display:block;margin:8px 0 4px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted,#8290a5)}.preview-item .field{margin:0}.notification-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--border,#263a57);font-size:13px}.notification-row:last-child{border-bottom:0}.notification-channel{font-weight:700;flex:none}.notification-recipient{min-width:0;overflow:hidden;text-overflow:ellipsis}.notification-status--SENT,.notification-status--QUEUED{background:#22c55e22;color:#22c55e;border-color:#22c55e55}.notification-status--FAILED{background:#ef444422;color:#ef4444;border-color:#ef444455}.notification-status--SKIPPED,.notification-status--PENDING{background:#8290a522;color:#8290a5;border-color:#8290a555}.notification-error{width:100%;color:#ef4444}.notification-acciones{width:100%;display:flex;gap:8px;margin-top:6px}.notification-body{width:100%;margin:6px 0 0;padding:10px;border-radius:10px;background:var(--color-surface-inset);border:1px solid rgba(148,163,184,.22);font:inherit;font-size:13px;line-height:1.5;white-space:pre-wrap;color:var(--color-text,#e5edf7)}.notification-ref{width:100%;display:flex;align-items:center;gap:8px;margin-top:4px;font-size:11px;color:var(--text-muted,#8290a5)}.notification-ref code{background:rgba(148,163,184,.14);padding:1px 6px;border-radius:5px;word-break:break-all}.status-pill{border:1px solid;border-radius:99px;padding:2px 10px;font-size:11px;white-space:nowrap}.workshop-panel--wide{grid-column:1/-1}.quote-line{display:grid;grid-template-columns:130px 2fr 90px 120px 130px 40px;gap:7px;margin:8px 0}.quote-line input,.quote-line select{min-width:0;background:var(--color-field);color:var(--color-text);border:1px solid rgba(125,170,210,.35);color-scheme: var(--color-scheme)}.quote-version{padding:12px 0;border-top:1px solid rgba(148,163,184,.15)}.quote-version summary{display:grid;grid-template-columns:1fr auto auto;gap:20px;cursor:pointer}.quote-totals{display:flex;justify-content:flex-end;gap:20px;padding:12px}@media(max-width:1000px){.workshop-panel--wide{grid-column:auto}.quote-line{grid-template-columns:1fr 1fr}.quote-version summary{grid-template-columns:1fr}}
.diagnosis-text{font-weight:700}.quote-card{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:18px;padding:12px 0;border-top:1px solid rgba(148,163,184,.15)}.quote-card div:first-child{display:flex;flex-direction:column;gap:4px}.workshop-modal-layer{z-index:145}.workshop-modal{width:min(720px,100%)}.quote-modal{width:min(1100px,96vw);max-height:92vh;overflow:auto}.quote-editor-head{display:grid;grid-template-columns:130px 2fr 90px 120px 130px 40px;gap:7px;margin:16px 0 2px;color:var(--text-secondary);font-size:12px}.budget-print{display:none}@media(max-width:700px){.quote-card{grid-template-columns:1fr}.quote-editor-head{display:none}.quote-modal .quote-line{grid-template-columns:1fr}}@media print{.budget-print,.budget-print *{visibility:visible!important}.budget-print{display:block!important;position:absolute;inset:0;background:white;color:black;padding:28px}.budget-print table{width:100%;border-collapse:collapse;margin:20px 0}.budget-print th,.budget-print td{padding:8px;border-bottom:1px solid #ccc;text-align:left}.budget-print th:nth-child(n+2),.budget-print td:nth-child(n+2){text-align:right}}

@media(max-width:700px){
  .work-orders-list{padding:0;background:transparent;border:0;box-shadow:none}
  .work-orders-list .table--cards-mobile tbody{gap:12px}
  .work-orders-list .work-order-row{padding:14px;border:1px solid var(--color-border)!important;border-radius:16px!important;background:var(--color-surface)!important}
  .work-orders-list .work-order-row>td{display:block;padding:0;border:0!important;background:transparent!important}
  .work-orders-list .work-order-row>td::before{display:none}
  .work-orders-list .work-order-row>td:nth-child(1){display:inline-block;font-size:18px;margin-bottom:10px}
  .work-orders-list .work-order-row>td:nth-child(6){float:right;display:inline-block;margin-bottom:10px}
  .work-orders-list .work-order-row>td:nth-child(2){clear:both;color:var(--color-text-muted);font-size:12px;margin-bottom:10px}
  .work-orders-list .work-order-row>td:nth-child(3){font-size:16px;font-weight:700;margin-bottom:5px}
  .work-orders-list .work-order-row>td:nth-child(3) .text-muted{font-size:12px;font-weight:400;margin-top:2px}
  .work-orders-list .work-order-row>td:nth-child(4){font-size:14px;margin-bottom:9px}
  .work-orders-list .work-order-row>td:nth-child(4) .text-muted{font-size:12px;margin-top:2px}
  .work-orders-list .work-order-row>td:nth-child(5){padding:10px 0;margin-top:6px;border-top:1px solid var(--color-border)!important;color:var(--color-text-secondary)}
  .receipt{margin:0}
}

/* Receipt print isolation: keep this block last so older generic print rules cannot leak UI into the document. */
@media print{
  body.printing-receipt .receipt{position:static!important;margin:0!important;padding:0!important;border:0!important;box-shadow:none!important;background:#fff!important;}
  body.printing-receipt .receipt > *:not(.receipt-print){display:none!important;}
  body.printing-receipt .receipt-print{display:block!important;visibility:visible!important;position:static!important;width:100%!important;}
  body.printing-receipt .receipt-print *{visibility:visible!important;}
}

.execution-row,.final-test-row{display:grid;grid-template-columns:100px 1fr auto auto;gap:12px;align-items:center;padding:9px 0;border-bottom:1px solid rgba(148,163,184,.12)}.execution-editor-head,.execution-editor{display:grid;grid-template-columns:110px 2fr 80px 110px 110px 96px;gap:8px;margin-top:14px}.execution-editor-head{margin-bottom:-8px;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--color-text-muted)}.final-test-editor{display:grid;grid-template-columns:160px 1fr auto;gap:8px;margin-top:14px}.execution-editor input,.execution-editor select,.final-test-editor input,.final-test-editor select{min-width:0;background:var(--color-surface);color:var(--color-text);border:1px solid var(--color-border)}.execution-editor input::placeholder,.final-test-editor input::placeholder{color:var(--color-text-muted)}@media(max-width:800px){.execution-editor,.final-test-editor,.execution-row,.final-test-row{grid-template-columns:1fr}.execution-editor .btn,.final-test-editor .btn{width:100%}}
.work-order-filters{margin-bottom:12px}.filters-grid{display:grid;grid-template-columns:1.2fr 1.6fr 1fr 1fr auto;gap:12px;align-items:end}.filters-grid .field{margin:0}.filters-grid select[multiple]{min-height:78px}.filter-actions{display:flex;align-items:end;gap:8px}.work-order-filters select,.pagination-actions select{background:var(--color-surface);color:var(--color-text);border:1px solid var(--color-border);color-scheme: var(--color-scheme)}.work-order-filters select option,.pagination-actions select option{background:var(--color-field);color:var(--color-text-primary)}.work-order-filters select option:checked{background:#2563eb;color:#fff}.pagination-bar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-top:12px}.pagination-actions{display:flex;align-items:center;gap:10px}.pagination-actions label{display:flex;align-items:center;gap:6px}.pagination-actions select{width:auto}@media(max-width:700px){.filters-grid{grid-template-columns:1fr}.filter-actions .btn{width:100%}.pagination-bar,.pagination-actions{align-items:stretch;flex-direction:column}.pagination-actions label{justify-content:space-between}}

.file-pick-list{list-style:none;margin:8px 0 0;padding:0;display:flex;flex-direction:column;gap:6px}
.file-pick-list li{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:12px;background:var(--color-surface);border:1px solid var(--border,#263a57);border-radius:8px;padding:6px 10px}
.file-pick-list li span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-pick-help{margin:6px 0 0;font-size:12px}

/* El input del picker de repuestos vive en otro componente, asi que el scoped
   CSS de esta vista no llega adentro: hay que darle el mismo look que el
   resto de los campos de la fila con :deep(). */
.quote-line :deep(.spare-picker__input){min-width:0;background:var(--color-field);color:var(--color-text);border:1px solid rgba(125,170,210,.35);color-scheme: var(--color-scheme)}
.execution-editor :deep(.spare-picker__input){min-width:0;background:var(--color-surface);color:var(--color-text);border:1px solid var(--color-border)}
.execution-editor :deep(.spare-picker__input::placeholder){color:var(--color-text-muted)}
/* Detalle de OT: resumen fijo a la izquierda, pasos del taller a la derecha. */
.order-detail-shell{display:grid;gap:12px}
.order-detail-back{justify-self:start}
.order-head{align-items:flex-start;gap:16px;margin-bottom:20px}
.order-head__title{margin:0;font-size:26px;line-height:1.15}
.order-head__sub{margin:4px 0 0}
.order-layout{display:grid;grid-template-columns:minmax(260px,320px) minmax(0,1fr);gap:20px;align-items:start}
.order-summary{position:sticky;top:76px;display:grid;gap:12px}
.summary-block{padding:14px 16px;border:1px solid var(--color-border);border-radius:14px;background:rgba(255,255,255,.02)}
.summary-block h3,.order-main h3{margin:0 0 10px;font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--color-text-muted)}
.facts{display:grid;gap:10px;margin:0}
.facts dt{font-size:12px;color:var(--color-text-muted)}
.facts dd{margin:2px 0 0;display:flex;flex-direction:column;gap:2px;overflow-wrap:anywhere}
.order-summary .lifecycle-card{grid-template-columns:1fr;margin:0;padding:0;border:0;background:transparent;gap:10px}
.order-summary .lifecycle-card>div{gap:2px}
.order-summary .lifecycle-card .text-muted{font-size:12px}
.order-summary .expected-editor{display:flex;gap:6px}
.order-summary .expected-editor input{min-width:0;flex:1}
.order-summary .technician-assign{max-width:none}
.order-main{display:grid;gap:12px;min-width:0}
.workflow{list-style:none;margin:0;padding:0;display:grid;gap:12px;counter-reset:paso}
.workflow-step{counter-increment:paso;position:relative;padding:16px 16px 16px 56px;border:1px solid var(--color-border);border-radius:14px;background:rgba(255,255,255,.02)}
.workflow-step::before{content:counter(paso);position:absolute;left:16px;top:14px;width:26px;height:26px;border-radius:50%;display:grid;place-items:center;font-size:13px;font-weight:700;border:1px solid var(--color-border);color:var(--color-text-muted)}
.workflow-step--current{border-color:var(--color-primary)}
.workflow-step--current::before{background:var(--color-primary);border-color:var(--color-primary);color:#fff}
.workflow-step__head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
.workflow-step__head p{margin:0 0 4px}
.order-collapsible summary{cursor:pointer;font-weight:700}
.order-collapsible[open] summary{margin-bottom:12px}
@media(max-width:900px){
  .order-layout{grid-template-columns:1fr}
  .order-summary{position:static}
}
@media(max-width:700px){
  .order-head__title{font-size:22px}
  .workflow-step{padding-left:48px}
  .workflow-step::before{left:12px}
  .workflow-step__head{flex-direction:column;align-items:stretch}
  .execution-editor-head{display:none}
}
</style>