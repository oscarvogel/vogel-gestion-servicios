# WhatsApp

Integración con la plataforma de WhatsApp de Vogel Consultoría
(`oscarvogel/vogel_whatsapp_api`, contrato en `docs/API_V1.md` de ese repo).

El dominio no habla con la gateway: lo hace un adaptador
(`app/services/notifications/channels.py`), igual que cualquier otro canal.

## Modelo: una empresa, una key, una instancia

Cada empresa manda **desde su propio número**, no desde una línea de Vogel. Eso obliga a
que la credencial sea por empresa:

| Dónde | Qué |
|---|---|
| `companies.whatsapp_instance_id` | Instancia de la gateway que usa esa empresa |
| `companies.whatsapp_api_key_encrypted` | API key de esa empresa, **cifrada** con Fernet |
| `companies.whatsapp_use_platform_key` | Opt-in para usar la key y la línea de Vogel |

La key se cifra con `CREDENTIALS_ENCRYPTION_KEY`, una clave maestra de plataforma. **Si esa
variable no está, el endpoint de configuración devuelve 503 y no guarda nada.** Es
deliberado: se prefiere fallar antes que tener credenciales en claro en la base.

La key es de **solo escritura**: el GET devuelve `whatsapp_api_key_configured: true/false`
y nunca el valor. Solo el admin de la empresa puede cargarla.

Para los talleres que no tienen WhatsApp propio existe el opt-in
`whatsapp_use_platform_key`. **Sin ese opt-in, una empresa sin key propia falla con el
motivo en la auditoría en vez de mandar desde el número de otro.**

## Aislamiento

La gateway resuelve permisos por empresa: `cliente API -> empresa -> instancias de esa
empresa`, y *"si ambos tienen companyId, una empresa nunca hereda permisos legacy sobre
otra"*. Eso sirve de segunda barrera: si se manda a un `instanceId` de otra empresa, la
gateway responde `403`.

La primera barrera es propia: cada fila de `work_order_notifications` lleva `company_id`,
derivado del tenant ya validado de la sesión, y toda consulta de auditoría filtra por él.

## El 202 no es "se envió"

La gateway responde `202` con `{"success":true,"data":{"messageId":"...","status":"queued"}}`.
**Eso es encolado, no entregado.** El consumidor tiene que consultar
`GET /api/v1/instances/:instanceId/messages/:messageId` para ver
`accepted`, `delivered`, `read` o `failed`.

Por eso el estado de la cola distingue:

- `QUEUED` — la gateway lo aceptó. **No sabemos si llegó.**
- `SENT` — entregado (solo email; el SMTP no tiene esa ambigüedad).
- `FAILED` — error del proveedor, con el motivo.

Confundir los dos sería mentirle al usuario en la auditoría que lee desde la OT.

## Tres trampas que costaron tiempo

### 1. El `instanceId` tiene que existir

Un nombre de instancia inventado no falla con un error visible para el usuario: puede
quedar encolado sin salir. En vogel-gestion el `instanceId` viene de
`companies.whatsapp_instance_id`, así que un valor mal cargado rompe el envío sin
avisar. **Verificá con `GET /api/v1/instances` cuál es el nombre real.**

### 2. El `403` no se arregla copiando y pegando la key

Un `403` significa "falta scope o acceso a instancia". Si la key está bien escrita pero el
cliente API tiene una `companyId` distinta a la de la instancia, la gateway lo rechaza
aunque el texto sea perfecto. Hay que revisar, del lado de la gateway:

- que el cliente API tenga la **misma empresa** que la instancia, o
- que el cliente no tenga empresa y quede vinculado en `api_client_instances`.

### 3. La auditoría de la gateway está filtrada por empresa

`GET /api/v1/admin/messages` *"respeta el ámbito de empresa del cliente autenticado: nunca
devuelve mensajes de instancias no autorizadas"*. **Que el mensaje no aparezca en esa lista
no prueba que no haya llegado.** Para verificar, consultá el mensaje por su `messageId`,
que no pasa por ese filtro.

Por eso la auditoría de vogel-gestion muestra el `messageId` con un botón para copiarlo: sin
ese identificador, "no llegó" y "no lo encuentro" son indistinguibles.

## Configuración de plataforma

```
WHATSAPP_BASE_URL=https://whatsapp.vogelconsultoria.com.ar
WHATSAPP_TIMEOUT_SECONDS=15
WHATSAPP_SOURCE_APP=vogel-gestion
CREDENTIALS_ENCRYPTION_KEY=<clave Fernet de plataforma>
```

Opcionales, solo para el opt-in de la línea de Vogel:

```
WHATSAPP_API_KEY=<key de plataforma>
WHATSAPP_DEFAULT_INSTANCE=<instancia por defecto>
```

Si se rota `CREDENTIALS_ENCRYPTION_KEY`, las credenciales ya guardadas dejan de descifrar
y el error lo dice explícitamente: hay que volver a cargarlas.

##Fuera de alcance por ahora

- **Multimedia** (`/media`, `/media/upload`, nota de voz con `voiceNote=true`): la gateway
  ya lo soporta y es lo que va a necesitar #43. Acá solo va texto.
- **Consulta del estado del mensaje** para avanzar `QUEUED` a entregado: el contrato la
  ofrece, pero hoy no se llama.
- **Inbound** (webhook `message.received`): es otro flujo, mensajes que entran.

## Drenaje

```powershell
python backend/scripts/drain_notifications.py --dry-run   # ver la cola
python backend/scripts/drain_notifications.py             # reintentar
```

Reintenta lo `PENDING` (por ejemplo, si el proceso murió entre el commit del cambio de
estado y el envío) y lo `FAILED` mientras tenga intentos disponibles. Nunca reintenta en
caliente sin límite, y nunca vuelve a tocar lo ya `QUEUED` o `SENT`.
