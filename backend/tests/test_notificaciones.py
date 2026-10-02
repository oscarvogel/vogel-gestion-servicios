"""Avisos al cliente por cambio de estado de OT (#45).

La matriz del issue: se dispara, no se dispara, falta de contacto, aislamiento entre
empresas, idempotencia, y que un fallo del proveedor no revierta el cambio de estado.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.customer import Customer, Equipment, EquipmentCategory
from app.models.work_order import WorkOrder, WorkOrderEvent, WorkOrderNotification, WorkOrderStatus
from app.services.notifications import enqueue as enqueue_module
from app.services.notifications.channels import EMAIL, WHATSAPP, SendResult
from app.services.notifications.enqueue import FAILED, PENDING, QUEUED, SENT, SKIPPED
from app.services.notifications.templates import build_context, render, unknown_variables
from tests.test_work_orders import login, setup


class RecordingSender:
    """Doble de prueba: no toca la red y deja ver que se le entrego."""

    def __init__(self, channel, result=None, raises=None):
        self.channel = channel
        self.calls = []
        self._result = result or SendResult(ok=True)
        self._raises = raises

    def send(self, db, notification, company):
        self.calls.append((notification.id, notification.recipient, notification.body))
        if self._raises is not None:
            raise self._raises
        return self._result


@pytest.fixture
def senders(monkeypatch):
    """Reemplaza el registro de canales por dobles y lo restaura al final."""
    created = {}

    def install(email_result=None, whatsapp_result=None, email_raises=None, whatsapp_raises=None):
        email = RecordingSender(EMAIL, email_result, email_raises)
        whatsapp = RecordingSender(WHATSAPP, whatsapp_result, whatsapp_raises)
        monkeypatch.setitem(enqueue_module.SENDERS, EMAIL, email)
        monkeypatch.setitem(enqueue_module.SENDERS, WHATSAPP, whatsapp)
        created[EMAIL] = email
        created[WHATSAPP] = whatsapp
        return email, whatsapp

    created["install"] = install
    return created


def _set_contact(db, company, **fields):
    customer = db.query(Customer).filter_by(company_id=company.id).first()
    for key, value in fields.items():
        setattr(customer, key, value)
    db.commit()
    return customer


def _configure(client, headers, name, **fields):
    payload = {"name": name, "color": "#F59E0B", "sort_order": 55, "active": True, **fields}
    created = client.post("/api/v1/work-orders/statuses", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_status_change_enqueues_one_row_per_configured_channel(client, db_session, senders):
    company, user, customer, equipment = setup(db_session, "notif-basic")
    headers = login(client, f"ot.notif-basic@example.com", company.id)
    _set_contact(db_session, company, whatsapp="5493764000000", email="cliente@example.com")
    senders["install"]()

    status_id = _configure(
        client, headers, "Listo para retirar",
        notify_whatsapp=True, notify_email=True,
        notification_template="Hola {{cliente}}, tu OT N° {{numero_ot}} está: {{estado}}.",
    )
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "No enciende"},
    ).json()
    changed = client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id})
    assert changed.status_code == 200, changed.text

    rows = db_session.query(WorkOrderNotification).order_by(WorkOrderNotification.id).all()
    assert {r.channel for r in rows} == {WHATSAPP, EMAIL}
    assert all(r.status == SENT for r in rows), [(r.channel, r.status, r.error) for r in rows]
    whatsapp = next(r for r in rows if r.channel == WHATSAPP)
    assert "tu OT N° 1 está: Listo para retirar" in whatsapp.body, whatsapp.body
    assert whatsapp.recipient == "5493764000000"
    assert whatsapp.sent_at is not None
    # El outbound de la gateway es "encolado", no entregado: el estado lo dice.
    queued = RecordingSender(WHATSAPP, SendResult(ok=True, queued=True, provider_message_id="m-1"))
    senders["install"](whatsapp_result=SendResult(ok=True, queued=True, provider_message_id="m-1"))
    other = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Otra"},
    ).json()
    client.post(f"/api/v1/work-orders/{other['id']}/status", headers=headers, json={"status_id": status_id})
    latest = db_session.query(WorkOrderNotification).filter_by(channel=WHATSAPP).order_by(WorkOrderNotification.id.desc()).first()
    assert latest.status == QUEUED, latest.status
    assert latest.provider_message_id == "m-1"


def test_channels_that_are_not_configured_are_not_queued(client, db_session, senders):
    company, user, customer, equipment = setup(db_session, "notif-off")
    headers = login(client, "ot.notif-off@example.com", company.id)
    _set_contact(db_session, company, whatsapp="5493764000000", email="cliente@example.com")
    senders["install"]()

    # Sin ningun canal prendido no se encola nada.
    status_id = _configure(client, headers, "Sin avisos", notifications_active=True)
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"},
    ).json()
    client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id})
    assert db_session.query(WorkOrderNotification).count() == 0

    # Con el interruptor maestro apagado tampoco, aunque los canales esten prendidos.
    status_id2 = _configure(client, headers, "Avisos apagados", notify_whatsapp=True, notify_email=True, notifications_active=False)
    client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id2})
    assert db_session.query(WorkOrderNotification).count() == 0


def test_missing_contact_is_recorded_as_skipped_with_the_reason(client, db_session, senders):
    company, user, customer, equipment = setup(db_session, "notif-nocontact")
    headers = login(client, "ot.notif-nocontact@example.com", company.id)
    _set_contact(db_session, company, whatsapp=None, phone=None, email=None)
    senders["install"]()

    status_id = _configure(client, headers, "Avisar igual", notify_whatsapp=True, notify_email=True)
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"},
    ).json()
    client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id})

    rows = db_session.query(WorkOrderNotification).all()
    assert len(rows) == 2, rows
    assert all(r.status == SKIPPED for r in rows), [(r.channel, r.status) for r in rows]
    assert "telefono" in next(r for r in rows if r.channel == WHATSAPP).error
    assert "email" in next(r for r in rows if r.channel == EMAIL).error
    # No se intentó enviar a nadie.
    assert senders[EMAIL].calls == [] and senders[WHATSAPP].calls == []


def test_whatsapp_falls_back_to_phone_when_there_is_no_whatsapp_field(client, db_session, senders):
    company, user, customer, equipment = setup(db_session, "notif-fallback")
    headers = login(client, "ot.notif-fallback@example.com", company.id)
    _set_contact(db_session, company, whatsapp=None, phone="5493764111111", email=None)
    senders["install"](whatsapp_result=SendResult(ok=True, queued=True, provider_message_id="m-2"))
    status_id = _configure(client, headers, "Avisar por telefono", notify_whatsapp=True)
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"},
    ).json()
    client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id})
    row = db_session.query(WorkOrderNotification).one()
    assert row.recipient == "5493764111111", row.recipient
    assert row.status == QUEUED


def test_a_provider_failure_never_reverts_the_status_change(client, db_session, senders):
    company, user, customer, equipment = setup(db_session, "notif-fail")
    headers = login(client, "ot.notif-fail@example.com", company.id)
    _set_contact(db_session, company, whatsapp="5493764000000")
    senders["install"](whatsapp_result=SendResult(ok=False, error="Gateway respondio 500"))
    status_id = _configure(client, headers, "Aviso que falla", notify_whatsapp=True)
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"},
    ).json()
    changed = client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id})

    # El cambio de estado quedo guardado aunque el proveedor haya fallado.
    assert changed.status_code == 200, changed.text
    assert changed.json()["status_id"] == status_id
    row = db_session.query(WorkOrderNotification).one()
    assert row.status == FAILED and "500" in row.error
    assert row.attempts == 1


def test_an_adapter_that_raises_does_not_break_the_status_change(client, db_session, senders):
    company, user, customer, equipment = setup(db_session, "notif-raise")
    headers = login(client, "ot.notif-raise@example.com", company.id)
    _set_contact(db_session, company, whatsapp="5493764000000")
    senders["install"](whatsapp_raises=RuntimeError("se cayo el adapter"))
    status_id = _configure(client, headers, "Aviso que explota", notify_whatsapp=True)
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"},
    ).json()
    changed = client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id})
    assert changed.status_code == 200, changed.text
    row = db_session.query(WorkOrderNotification).one()
    assert row.status == FAILED and "RuntimeError" in row.error


def test_notifications_never_cross_companies(client, db_session, senders):
    a, _, ca, ea = setup(db_session, "notif-iso-a")
    b, _, cb, eb = setup(db_session, "notif-iso-b")
    ha = login(client, "ot.notif-iso-a@example.com", a.id)
    hb = login(client, "ot.notif-iso-b@example.com", b.id)
    _set_contact(db_session, a, whatsapp="5493764000000", email="a@example.com")
    _set_contact(db_session, b, whatsapp="5493764999999", email="b@example.com")
    senders["install"]()

    status_a = _configure(client, ha, "Avisar A", notify_whatsapp=True, notify_email=True)
    status_b = _configure(client, hb, "Avisar B", notify_whatsapp=True, notify_email=True)
    order_a = client.post("/api/v1/work-orders", headers=ha, json={"customer_id": ca.id, "equipment_id": ea.id, "reported_fault": "A"}).json()
    order_b = client.post("/api/v1/work-orders", headers=hb, json={"customer_id": cb.id, "equipment_id": eb.id, "reported_fault": "B"}).json()
    client.post(f"/api/v1/work-orders/{order_a['id']}/status", headers=ha, json={"status_id": status_a})
    client.post(f"/api/v1/work-orders/{order_b['id']}/status", headers=hb, json={"status_id": status_b})

    rows_a = db_session.query(WorkOrderNotification).filter_by(company_id=a.id).all()
    rows_b = db_session.query(WorkOrderNotification).filter_by(company_id=b.id).all()
    assert {r.recipient for r in rows_a} == {"5493764000000", "a@example.com"}
    assert {r.recipient for r in rows_b} == {"5493764999999", "b@example.com"}
    # La empresa B no puede leer los avisos de la A, ni de una OT que no es suya.
    assert client.get(f"/api/v1/work-orders/{order_a['id']}/notifications", headers=hb).status_code == 404
    assert client.get(f"/api/v1/work-orders/{order_a['id']}/notifications", headers=ha).json()["total"] == 2


def test_the_same_event_cannot_produce_two_rows_of_the_same_channel(client, db_session, senders):
    """La idempotencia la impone la base, no una convencion del codigo."""
    company, user, customer, equipment = setup(db_session, "notif-idem")
    headers = login(client, "ot.notif-idem@example.com", company.id)
    _set_contact(db_session, company, whatsapp="5493764000000")
    senders["install"]()
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"},
    ).json()
    client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers,
                json={"status_id": _configure(client, headers, "Avisar", notify_whatsapp=True)})

    event = db_session.query(WorkOrderEvent).order_by(WorkOrderEvent.id.desc()).first()
    with pytest.raises(IntegrityError):
        db_session.add(
            WorkOrderNotification(
                company_id=company.id, work_order_id=order["id"], work_order_event_id=event.id,
                channel=WHATSAPP, recipient="5493764000000", body="duplicado",
            )
        )
        db_session.commit()
    db_session.rollback()


def test_drain_retries_only_what_is_still_pending_or_failed(client, db_session, senders, monkeypatch):
    company, user, customer, equipment = setup(db_session, "notif-drain")
    headers = login(client, "ot.notif-drain@example.com", company.id)
    _set_contact(db_session, company, whatsapp="5493764000000")
    failing = RecordingSender(WHATSAPP, SendResult(ok=False, error="gateway caida"))
    monkeypatch.setitem(enqueue_module.SENDERS, WHATSAPP, failing)
    status_id = _configure(client, headers, "Avisar", notify_whatsapp=True)
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"},
    ).json()
    client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id})
    row = db_session.query(WorkOrderNotification).one()
    assert row.status == FAILED and row.attempts == 1

    # El drenaje reintenta y ahora el proveedor responde bien.
    ok = RecordingSender(WHATSAPP, SendResult(ok=True, queued=True, provider_message_id="m-9"))
    monkeypatch.setitem(enqueue_module.SENDERS, WHATSAPP, ok)
    summary = enqueue_module.dispatch_pending(db_session, limit=10)
    assert summary["queued"] == 1, summary
    db_session.refresh(row)
    assert row.status == QUEUED and row.attempts == 2

    # Un segundo drenaje no vuelve a tocar lo ya entregado.
    summary = enqueue_module.dispatch_pending(db_session, limit=10)
    assert summary == {"sent": 0, "queued": 0, "failed": 0}, summary
    assert len(ok.calls) == 1, ok.calls


def test_drain_respects_the_attempt_limit(client, db_session, monkeypatch):
    company, user, customer, equipment = setup(db_session, "notif-maxatt")
    headers = login(client, "ot.notif-maxatt@example.com", company.id)
    _set_contact(db_session, company, whatsapp="5493764000000")
    failing = RecordingSender(WHATSAPP, SendResult(ok=False, error="siempre falla"))
    monkeypatch.setitem(enqueue_module.SENDERS, WHATSAPP, failing)
    monkeypatch.setattr(settings, "notification_max_attempts", 2)
    status_id = _configure(client, headers, "Avisar", notify_whatsapp=True)
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"},
    ).json()
    client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id})

    enqueue_module.dispatch_pending(db_session, limit=10)
    enqueue_module.dispatch_pending(db_session, limit=10)
    row = db_session.query(WorkOrderNotification).one()
    assert row.attempts == 2, row.attempts
    # Agotados los intentos, el drenaje ya no insiste: queda para revision manual.
    enqueue_module.dispatch_pending(db_session, limit=10)
    db_session.refresh(row)
    assert row.attempts == 2, row.attempts


def test_templates_only_resolve_known_variables(client, db_session, senders):
    company, user, customer, equipment = setup(db_session, "notif-tpl")
    headers = login(client, "ot.notif-tpl@example.com", company.id)
    _set_contact(db_session, company, whatsapp="5493764000000")
    senders["install"]()
    status_id = _configure(
        client, headers, "Avisar con plantilla",
        notify_whatsapp=True,
        notification_template="{{cliente}} / {{equipo}} / {{client}} / {{__class__}}",
    )
    order = client.post(
        "/api/v1/work-orders", headers=headers,
        json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"},
    ).json()
    client.post(f"/api/v1/work-orders/{order['id']}/status", headers=headers, json={"status_id": status_id})
    body = db_session.query(WorkOrderNotification).one().body
    # Los conocidos se resuelven; los desconocidos quedan a la vista en vez de vaciarse.
    assert "Cliente notif-tpl" in body
    assert "{{client}}" in body
    assert "{{__class__}}" in body
    assert "__class__" not in body.replace("{{__class__}}", "")

    row = db_session.query(WorkOrder).first()
    context = build_context(db_session, company, row)
    assert unknown_variables("{{cliente}} {{client}}", context) == ["client"]


def test_notification_variables_endpoint_documents_the_allowlist(client, db_session):
    company, _, _, _ = setup(db_session, "notif-vars")
    headers = login(client, "ot.notif-vars@example.com", company.id)
    body = client.get("/api/v1/work-orders/notifications/variables", headers=headers).json()
    assert "cliente" in body["variables"] and "numero_ot" in body["variables"]
    assert "{{cliente}}" in body["example"]


def test_status_config_is_readable_after_saving(client, db_session, senders):
    company, _, _, _ = setup(db_session, "notif-config")
    headers = login(client, "ot.notif-config@example.com", company.id)
    senders["install"]()
    status_id = _configure(
        client, headers, "Listo para retirar", notify_whatsapp=True, notify_email=False,
        notifications_active=True,
        notification_template="Hola {{cliente}}",
        notification_email_subject="Tu OT {{numero_ot}}",
    )
    saved = next(s for s in client.get("/api/v1/work-orders/statuses", headers=headers).json() if s["id"] == status_id)
    assert saved["notify_whatsapp"] is True
    assert saved["notify_email"] is False
    assert saved["notification_template"] == "Hola {{cliente}}"
    assert saved["notification_email_subject"] == "Tu OT {{numero_ot}}"


def test_company_can_configure_its_instance_and_sender_without_superadmin(client, db_session):
    """La instancia y el remitente son de la empresa, no de la plataforma.

    El PATCH de empresa pide superadmin; esto lo configura la propia empresa con su
    permiso, porque son sus numeros de salida. Y sigue sin haber credencial por tenant.
    """
    company, _, _, _ = setup(db_session, "notif-settings")
    headers = login(client, "ot.notif-settings@example.com", company.id)
    vacio = client.get("/api/v1/work-orders/notification-settings", headers=headers).json()
    assert vacio["whatsapp_instance_id"] is None
    guardado = client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={
        "whatsapp_instance_id": "ceramica",
        "notification_sender_name": "Taller Ceramica",
        "notification_sender_email": "taller@ceramica.example.com",
    })
    assert guardado.status_code == 200, guardado.text
    assert guardado.json()["whatsapp_instance_id"] == "ceramica"
    leido = client.get("/api/v1/work-orders/notification-settings", headers=headers).json()
    assert leido["notification_sender_name"] == "Taller Ceramica"
    # Update parcial: mandar un solo campo no borra los demas.
    client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={
        "whatsapp_instance_id": "otro",
    })
    assert client.get("/api/v1/work-orders/notification-settings", headers=headers).json()["notification_sender_name"] == "Taller Ceramica"
    # Otra empresa no lee ni escribe estos datos.
    otra, _, _, _ = setup(db_session, "notif-settings-b")
    h2 = login(client, "ot.notif-settings-b@example.com", otra.id)
    assert client.get("/api/v1/work-orders/notification-settings", headers=h2).json()["whatsapp_instance_id"] is None
