# Notificaciones al cliente por cambio de estado de OT (#45)

**Estado:** en curso, 2026-10-02
**Rama:** `feat/issue-45-notificaciones-estado`

## Objetivo

Que cada empresa decida, por estado de OT, si avisa al cliente y por qué canal, y que el
aviso llegue sin poder romper el cambio de estado ni duplicarse.

## Decisiones tomadas con el usuario

- **WhatsApp:** se implementa contra la API real (`vogel_whatsapp_api`), no un stub.
- **Email:** un SMTP de la plataforma por variable de entorno. **No** se guardan
  credenciales SMTP por empresa: es una decisión de seguridad, no de conveniencia. Cada
  empresa personaliza nombre y dirección de remitente, no la autenticación.
- **Despacho:** la notificación se encola **en la misma transacción** que el cambio de
  estado, se intenta entregar **después del commit** dentro de un `try/except` que no
  puede hacer fallar el request, y hay un **script de drenaje** para reintentar lo que
  quedó. No se agrega ningún proceso nuevo que haya que operar.

## Contrato de la gateway (de `vogel_whatsapp_api`, `docs/API_V1.md`)

```http
POST https://whatsapp.vogelconsultoria.com.ar/api/v1/instances/:instanceId/messages
x-api-key: <key>

{"phone":"...","message":"...","externalRef":"...","actorId":"...","actorName":"...","sourceApp":"..."}
```

- `202` con `{"success":true,"data":{"messageId":"...","status":"queued"}}`.
- **`202` significa encolado, no entregado.** El consumidor tiene que consultar
  `GET /api/v1/instances/:instanceId/messages/:messageId` hasta ver
  `accepted`, `delivered`, `read` o `failed`.
- Instancias: `GET /api/v1/instances` (scope `instances:read`).

Consecuencia de diseño: el estado `SENT` de la cola **no significa entregado**. Se modelan
`QUEUED` (la gateway aceptó) y el drenaje puede avanzar el estado consultando el
`messageId`. Confundir "aceptado" con "entregado" sería mentirle al usuario en la auditoría.

## Aislamiento por empresa

La gateway resuelve permisos por empresa: `cliente API -> empresa -> instancias de esa
empresa`, y "una empresa nunca hereda permisos legacy sobre otra". Eso sirve de segunda
barrera: si mandamos a un `instanceId` de otra empresa, la gateway responde `403`.

La primera barrera es propia: cada fila de la cola lleva `company_id`, se crea desde el
tenant ya validado de la sesión, y todas las consultas de auditoría filtran por él. La
`company_id` nunca viene del frontend.

Una sola API key de plataforma (variable de entorno) más `companies.whatsapp_instance_id`
por empresa. No se guarda una key por tenant.

## Modelo de datos

**`work_order_statuses`** agrega la configuración por estado que pedía el issue:

- `notify_whatsapp` bool
- `notify_email` bool
- `notifications_active` bool (interruptor maestro del estado)
- `notification_template` text (cuerpo, con `{{variable}}`)
- `notification_email_subject` varchar(200)

**`companies`** agrega: `whatsapp_instance_id`, `notification_sender_name`,
`notification_sender_email`.

**`work_order_notifications`** es la cola y la auditoría en la misma tabla:

- `company_id`, `work_order_id`, `work_order_event_id` (**NOT NULL**)
- `channel` (`WHATSAPP` | `EMAIL`), `recipient`, `subject`, `body`
- `status` (`PENDING` | `QUEUED` | `SENT` | `FAILED` | `SKIPPED`)
- `attempts`, `error`, `provider_message_id`
- `created_at`, `sent_at`, `updated_at`
- **UniqueConstraint `(company_id, work_order_event_id, channel)`**

Esa restricción es la idempotencia. Cada cambio de estado produce exactamente un
`WorkOrderEvent`, así que reprocesar el mismo evento no puede generar un segundo envío. El
`work_order_event_id` es NOT NULL a propósito: si fuera nullable, en SQL los NULL no se
consideran iguales entre sí y la deduplicación dejaría de funcionar en silencio.

## Plantillas: solo una lista blanca

Las variables salen de una lista blanca y se resuelven contra la OT **de la empresa del
tenant**. No hay forma de llegar a datos de otra empresa ni de escribir properties
arbitrarias.

Un `{{placeholder}}` desconocido **se deja literal** en el mensaje en vez de vaciarse. Si
un administrador escribe `{{client}}` en vez de `{{cliente}}`, el cliente ve `{{client}}` y
el error se ve solo. Vaciarlo mandaría un mensaje roto sin señal.

Si falta el dato de contacto del canal, **no se encola nada**: se registra una fila
`SKIPPED` con el motivo, que es lo que pedía el issue ("no enviar si falta el dato de
contacto requerido; registrar la causa").

## Orden en `change_status`

```python
row.status_id = target.id
event = WorkOrderEvent(...)          # el evento que dispara las notificaciones
db.add(event)
db.flush()                            # necesita event.id
enqueue_for_event(db, event)          # filas de la cola, MISMA transaccion
db.commit()                           # estado + evento + cola, todo junto
dispatch(ids)                         # DESPUES del commit, en try/except
```

Si el proceso muere entre el commit y el envío, la fila queda `PENDING` y el drenaje la
recupera. Si el envío falla, el estado de la OT ya está guardado y la fila queda `FAILED`
con el error. Ningún camino revierte el cambio de estado.

## Verificación

Tests que cubren la matriz del issue: se dispara, no se dispara, falta de contacto,
aislamiento entre empresas, idempotencia del mismo evento, y que un fallo del proveedor no
revierte el cambio de estado.

## Fuera de alcance

- **WhatsApp media** (`POST /instances/:id/media` y `/media/upload`, con nota de voz vía
  `voiceNote=true`): el gateway ya lo soporta y es lo que va a necesitar #43, pero acá solo
  va texto.
- **Consulta del estado del mensaje** para avanzar `QUEUED` a entregado: el contrato la
  ofrece; queda como paso opcional del drenaje, no en el camino del request.
- **Inbound**: el gateway tiene webhook `message.received`. Es otro flujo (mensajes que
  entran) y no es parte de este issue.
