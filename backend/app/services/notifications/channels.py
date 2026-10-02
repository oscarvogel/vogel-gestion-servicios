"""Adaptadores de canal para los avisos al cliente.

Cada canal es un adaptador detras de la misma interfaz, para agregar otro (SMS, portal)
sin tocar el dominio de la OT. Ninguno de los dos lanza excepcion hacia arriba: devuelven
un resultado, porque un proveedor caido no puede tumbar el flujo de la orden.
"""
from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.core.config import settings
from app.models.company import Company
from app.models.work_order import WorkOrderNotification

WHATSAPP = "WHATSAPP"
EMAIL = "EMAIL"


@dataclass
class SendResult:
    ok: bool
    # La gateway responde 202 = encolado, NO entregado. Por eso el resultado distingue
    # "aceptado" de "entregado": marcar SENT cuando solo se encolo seria mentir en la
    # auditoria que el usuario lee desde la OT.
    queued: bool = False
    provider_message_id: str | None = None
    error: str | None = None


def _sender_for(company: Company) -> tuple[str, str | None]:
    """Remitente de la empresa si lo definio; si no, el de la plataforma."""
    address = company.notification_sender_email or settings.email_from_address
    name = company.notification_sender_name or settings.email_from_name
    if not address:
        return "", None
    return address, formataddr((name, address))


def _instance_for(company: Company) -> str | None:
    """Instancia de la gateway. La de la empresa; la de plataforma solo con opt-in."""
    if company.whatsapp_instance_id:
        return company.whatsapp_instance_id
    if company.whatsapp_use_platform_key:
        return settings.whatsapp_default_instance
    return None


def _whatsapp_key_for(company: Company) -> tuple[str | None, str | None]:
    """Devuelve (api_key, motivo_del_fallo).

    La key de la empresa manda siempre. La de plataforma solo si la empresa lo pidio
    explicitamente: sin ese opt-in, una empresa sin key propia falla en vez de mandar
    desde el numero de otro, que es lo que el cliente recibiria sin entender de quien es.
    """
    from app.services import credentials

    if company.whatsapp_api_key_encrypted:
        try:
            return credentials.decrypt(company.whatsapp_api_key_encrypted), None
        except credentials.CredentialError as exc:
            return None, str(exc)[:500]
    if company.whatsapp_use_platform_key and settings.whatsapp_api_key:
        return settings.whatsapp_api_key, None
    if company.whatsapp_use_platform_key:
        return None, "Usa la linea de Vogel pero la plataforma no tiene WHATSAPP_API_KEY"
    return None, "La empresa no tiene API key de WhatsApp configurada"


class EmailSender:
    """SMTP de la plataforma. No hay credenciales por empresa, solo remitente."""

    channel = EMAIL

    def send(self, db, notification: WorkOrderNotification, company: Company) -> SendResult:
        if not settings.smtp_host:
            return SendResult(ok=False, error="SMTP no configurado en la plataforma (SMTP_HOST)")
        address, from_header = _sender_for(company)
        if not address:
            return SendResult(ok=False, error="Sin remitente: falta SMTP_FROM o el remitente de la empresa")
        to_addr, _ = parseaddr(notification.recipient or "")
        if not to_addr:
            return SendResult(ok=False, error="Destinatario de email invalido")

        message = EmailMessage()
        message["From"] = from_header or address
        message["To"] = to_addr
        message["Subject"] = (notification.subject or "").strip() or f"Orden de trabajo #{notification.work_order_id}"
        message.set_content(notification.body or "")
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password or "")
                smtp.send_message(message)
            return SendResult(ok=True)
        except Exception as exc:  # noqa: BLE001 - el proveedor puede fallar de mil maneras
            return SendResult(ok=False, error=f"{type(exc).__name__}: {exc}"[:500])


class WhatsAppSender:
    """Gateway de WhatsApp de Vogel.

    Contrato (vogel_whatsapp_api docs/API_V1.md):
        POST {base}/api/v1/instances/{instanceId}/messages   con header x-api-key
        body: phone, message, externalRef, actorId, actorName, sourceApp
        202 -> {"success":true,"data":{"messageId":"...","status":"queued"}}
    El 202 es "encolado", no entregado.
    """

    channel = WHATSAPP

    def send(self, db, notification: WorkOrderNotification, company: Company) -> SendResult:
        api_key, motivo = _whatsapp_key_for(company)
        if not api_key:
            return SendResult(ok=False, error=motivo or "Sin API key de WhatsApp para la empresa")
        instance = _instance_for(company)
        if not instance:
            return SendResult(ok=False, error="La empresa no tiene instancia de WhatsApp configurada")
        phone = (notification.recipient or "").strip()
        if not phone:
            return SendResult(ok=False, error="Sin numero de WhatsApp del cliente")

        # Import perezoso: si solo se usa email, la app no necesita httpx cargado.
        import httpx

        url = f"{settings.whatsapp_base_url.rstrip('/')}/api/v1/instances/{instance}/messages"
        payload = {
            "phone": phone,
            "message": notification.body or "",
            # externalRef es la correlación del lado de la gateway. Lleva el id de la fila
            # de la cola, asi se puede rastrear el mismo aviso en los dos sistemas.
            "externalRef": f"vgs:notif:{notification.id}",
            "actorName": "Vogel Gestión de Servicios",
            "sourceApp": settings.whatsapp_source_app,
        }
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={"x-api-key": api_key},
                timeout=settings.whatsapp_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            return SendResult(ok=False, error=f"{type(exc).__name__}: {exc}"[:500])

        if response.status_code in (401, 403):
            return SendResult(ok=False, error=f"Gateway rechazo la API key o la instancia ({response.status_code})")
        if response.status_code >= 400:
            return SendResult(ok=False, error=f"Gateway respondio {response.status_code}: {response.text[:300]}")
        try:
            data = response.json().get("data") or {}
        except Exception:  # noqa: BLE001
            return SendResult(ok=False, error=f"Respuesta de la gateway ilegible: {response.text[:200]}")
        message_id = data.get("messageId")
        if not message_id:
            return SendResult(ok=False, error=f"La gateway no devolvio messageId: {response.text[:200]}")
        return SendResult(ok=True, queued=True, provider_message_id=str(message_id))
