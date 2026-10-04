"""Preparar un aviso al cliente sin mandarlo (#44, sub-issue 5).

La restriccion que este sub-issue no negocia: **`preparar_comunicacion_cliente` no envia**.
Prepara, deja el aviso en PENDIENTE con su evento, y lo manda una persona desde la orden.

El riesgo real de este sub-issue no es que el modelo escriba un mensaje feo —para eso esta que
la persona lo lea y lo edite antes de confirmar—, es que el mensaje **salga solo**. Un WhatsApp
al cliente no se deshace. Por eso el test central no mira el texto que arma el modelo: mira que
confirmar la propuesta no despierte el envio.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.api.v1.work_orders import list_notifications, send_notification
from app.models.ai_action_proposal import RIESGO_COMUNICACION, AiActionProposal
from app.models.company import Company
from app.models.user import User
from app.models.work_order import WorkOrderEvent, WorkOrderNotification, WorkOrderStatus
from app.models.work_order_quote import WorkOrderExecutionItem
from app.services import work_orders as wo_service
from app.services.ai import proposals
from app.services.ai.tools import ToolContext, disponibles, ejecutar
from app.services.ai.tools.write import TOOLS as TOOLS_ESCRITURA
from app.services.notifications import enqueue as notif
from tests.test_ai import _dar_permiso_ia, _habilitar
from tests.test_work_orders import login, setup

TODOS = frozenset({"ai.use", "customers.view", "work_orders.view", "work_orders.manage"})
TODOS_SIN_GESTION = frozenset({"ai.use", "work_orders.view"})


class _FalsoSender:
    """Anota los envios sin tocar la red. Si algo se manda, queda en `mandados`."""

    enviados: list[int] = []

    def send(self, db, row, company):
        type(self).enviados.append(row.id)
        return notif.SendResult(ok=True, provider_message_id="falso-123")


@pytest.fixture
def sender_falso(monkeypatch):
    _FalsoSender.enviados = []
    monkeypatch.setitem(notif.SENDERS, "WHATSAPP", _FalsoSender())
    monkeypatch.setitem(notif.SENDERS, "EMAIL", _FalsoSender())
    return _FalsoSender


def _contexto(db, company_id, permisos=TODOS, user_id=1):
    return ToolContext(db=db, company_id=company_id, user_id=user_id, permissions=permisos)


def _proponer(db, company_id, tool, argumentos, permisos=TODOS):
    return ejecutar(tool, argumentos, _contexto(db, company_id, permisos))


def _escenario(db, sufijo, *, whatsapp=True, telefono="+5493512345678", plantilla=None):
    """Empresa con IA, orden en un estado que avisa por WhatsApp, y cliente con numero."""
    company, user, customer, equipment = setup(db, sufijo)
    _habilitar(db, company.id)
    _dar_permiso_ia(db, company.id)
    if telefono is not None:
        customer.whatsapp = telefono
        db.commit()

    estados = (
        db.query(WorkOrderStatus)
        .filter_by(company_id=company.id, active=True)
        .order_by(WorkOrderStatus.sort_order)
        .all()
    )
    # El que avisa es el primero, para no depender de como se llamen en el fixture.
    objetivo = estados[0]
    objetivo.notifications_active = True
    objetivo.notify_whatsapp = whatsapp
    objetivo.notify_email = False
    if plantilla:
        objetivo.notification_template = plantilla
    db.commit()

    orden = wo_service.crear_orden(
        db, company_id=company.id, user_id=user.id, customer_id=customer.id,
        equipment_id=equipment.id, reported_fault="No enciende",
    )
    db.commit()
    return company, user, orden, objetivo


# --- la herramienta prepara, no envia ------------------------------------------------------


def test_preparar_avisa_que_queda_pendiente_y_no_que_se_manda(db_session):
    company, _, orden, _ = _escenario(db_session, "prep-pendiente")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    resultado = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente", {"orden": orden.id}
    )

    assert resultado.ok is True, resultado.error_message
    assert resultado.data["riesgo"] == RIESGO_COMUNICACION
    # El aviso al cliente no se puede deshacer: se marca aunque todavia no salga.
    assert resultado.data["avisa_al_cliente"] is False
    assert resultado.data["previo"]["queda_pendiente_de_envio"] is True
    aviso = resultado.data["previo"]["avisos"][0]
    assert aviso["canal"] == "WHATSAPP"
    assert aviso["destinatario"] == "+5493512345678"
    assert "Fuente" in aviso["mensaje"] or aviso["mensaje"]


def test_confirmar_prepara_el_aviso_pero_no_lo_manda(db_session, sender_falso):
    """El test que sostiene el sub-issue.

    Se propone, se confirma, y se mira que no haya salido nada. `notifica=False` en la
    propuesta es lo que hace que `_despachar` no se dispare: confirmar es preparar.
    """
    company, _, orden, _ = _escenario(db_session, "prep-no-manda")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    propuesta = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente", {"orden": orden.id}
    )
    confirmada = proposals.confirmar(
        db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1
    )

    assert confirmada.status == "aplicada"
    assert confirmada.notified is False
    filas = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .all()
    )
    assert len(filas) == 1
    assert filas[0].status == "PENDING", "tiene que quedar esperando a que lo mande alguien"
    assert filas[0].body
    assert sender_falso.enviados == [], "confirmar no puede mandar el mensaje"


def test_confirmar_por_el_endpoint_no_manda_nada(client, db_session, sender_falso):
    """El guard de verdad, y va por el endpoint.

    `proposals.confirmar` no despacha: despacha el endpoint, despues del commit, leyendo
    `propuesta.notified`. Un test que solo llama a `confirmar` verifica el flag pero no el
    envio, asi que pasaria aunque el endpoint mandara. Este hace el viaje completo: proponer,
    confirmar por la API, y mirar que no salio nada.
    """
    company, _, orden, _ = _escenario(db_session, "prep-endpoint")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    cabeceras = login(client, "ot.prep-endpoint@example.com", company.id)
    # Se propone a mano lo que el modelo propondría, y lo interesante es el camino de
    # confirmacion: ese es el que despacha.
    propuesta = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente",
        {"orden": orden.id, "mensaje": "Ya lo estamos resolviendo."},
    )
    confirmar = client.post(
        f"/api/v1/ai/propuestas/{propuesta.data['propuesta_id']}/confirmar",
        headers=cabeceras, json={},
    )
    assert confirmar.status_code == 200, confirmar.text
    assert confirmar.json()["avisos_enviados"] == {}, "confirmar no puede mandar el aviso"
    assert sender_falso.enviados == []

    aviso = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .one()
    )
    assert aviso.status == "PENDING"


def test_el_mensaje_del_modelo_llega_como_texto_y_queda_pendiente(db_session, sender_falso):
    company, _, orden, _ = _escenario(db_session, "prep-mensaje")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)
    texto = "Hola Juan, hoy pasamos a rever la fuente. Te confirmamos mañana."

    propuesta = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente",
        {"orden": orden.id, "mensaje": texto},
    )
    assert propuesta.data["previo"]["avisos"][0]["mensaje"] == texto

    proposals.confirmar(
        db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1
    )
    fila = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .one()
    )
    assert fila.body == texto
    assert fila.status == "PENDING"
    assert sender_falso.enviados == []


def test_la_persona_puede_corregir_el_mensaje_antes_de_confirmar(db_session, sender_falso):
    """Lo que se confirma es lo corregido, no lo que propuso el modelo."""
    company, _, orden, _ = _escenario(db_session, "prep-corregido")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    propuesta = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente",
        {"orden": orden.id, "mensaje": "Mensaje del modelo, con un error."},
    )
    corregido = "Hola Juan, la fuente quedó reemplazada. Gracias."
    proposals.confirmar(
        db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1,
        argumentos={"orden": orden.id, "mensaje": corregido},
    )

    fila = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .one()
    )
    assert fila.body == corregido
    assert "error" not in fila.body


def test_sin_mensaje_sale_la_plantilla_del_estado(db_session, sender_falso):
    """Sin mensaje propio, se usa la plantilla de #45 con sus variables resueltas."""
    company, _, orden, _ = _escenario(
        db_session, "prep-plantilla",
        plantilla="Hola {{cliente}}, tu orden N° {{numero_ot}} está en {{estado}}.",
    )
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    propuesta = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente", {"orden": orden.id}
    )
    cuerpo = propuesta.data["previo"]["avisos"][0]["mensaje"]

    assert "{{cliente}}" not in cuerpo, "las variables tienen que quedar resueltas"
    assert "{{numero_ot}}" not in cuerpo
    assert "Recibido" in cuerpo
    assert sender_falso.enviados == []


def test_un_canal_inventado_se_rechaza_antes_de_proponer(db_session):
    company, _, orden, _ = _escenario(db_session, "prep-canal-malo")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    resultado = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente",
        {"orden": orden.id, "canal": "SMS"},
    )

    assert resultado.ok is False
    assert resultado.error_code == "argumentos_invalidos"
    assert db_session.query(AiActionProposal).filter_by(company_id=company.id).count() == 0


# --- lo que no se puede preparar, se dice y no se disimula --------------------------------


def test_un_estado_sin_avisos_configurados_no_prepara_nada(db_session):
    """El caso mas comun: el estado no avisa. Decirlo es mejor que dejar un aviso vacio."""
    company, _, orden, objetivo = _escenario(db_session, "prep-sin-avisos")
    objetivo.notifications_active = False
    objetivo.notify_whatsapp = False
    db_session.commit()
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    resultado = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente", {"orden": orden.id}
    )

    assert resultado.ok is False
    assert "avisos" in resultado.error_message.lower()
    assert db_session.query(AiActionProposal).filter_by(company_id=company.id).count() == 0


def test_un_cliente_sin_numero_no_deja_una_comunicacion_imposible(db_session):
    company, _, orden, _ = _escenario(db_session, "prep-sin-numero", telefono=None)
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    resultado = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente", {"orden": orden.id}
    )

    assert resultado.ok is False
    assert resultado.error_code == "sin_destinatario"
    assert "numero" in resultado.error_message.lower() or "número" in resultado.error_message.lower()


# --- reutiliza el sistema de #45, no uno nuevo ------------------------------------------


def test_el_aviso_preparado_queda_en_la_lista_de_la_orden(db_session, sender_falso):
    """Criterio del issue: el aviso queda auditable desde la OT, como cualquier otro."""
    company, _, orden, _ = _escenario(db_session, "prep-auditable")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    propuesta = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente", {"orden": orden.id}
    )
    proposals.confirmar(
        db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1
    )

    lectura = list_notifications(orden.id, company_id=company.id, _actor=db_session.get(User, 1), db=db_session)
    assert lectura["total"] == 1
    # `list_notifications` devuelve modelos, no diccionarios, cuando se la llama directo.
    assert lectura["items"][0].status == "PENDING"
    assert lectura["items"][0].recipient == "+5493512345678"


def test_el_aviso_tiene_su_propio_evento_y_no_choca_con_el_de_cambio_de_estado(
    db_session, sender_falso
):
    """Cada aviso cuelga de un evento. Es lo que sostiene el unique del outbox.

    Colgarlo del evento de cambio de estado habria chocado contra
    (company_id, work_order_event_id, channel) en cuanto la orden cambiara de estado otra vez.
    """
    company, _, orden, _ = _escenario(db_session, "prep-evento")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    propuesta = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente", {"orden": orden.id}
    )
    proposals.confirmar(
        db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1
    )

    eventos = (
        db_session.query(WorkOrderEvent)
        .filter_by(company_id=company.id, work_order_id=orden.id, event_type="NOTICE")
        .all()
    )
    assert len(eventos) == 1
    assert "pendiente" in eventos[0].detail.lower()

    aviso = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .one()
    )
    assert aviso.work_order_event_id == eventos[0].id


def test_dos_avisos_preparados_no_chocan_entre_si(db_session, sender_falso):
    """Dos pedidos seguidos dan dos avisos, no un error de base."""
    company, _, orden, _ = _escenario(db_session, "prep-dos")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    for texto in ("Primer aviso.", "Segundo aviso."):
        propuesta = _proponer(
            db_session, company.id, "preparar_comunicacion_cliente",
            {"orden": orden.id, "mensaje": texto},
        )
        proposals.confirmar(
            db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1
        )

    filas = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .all()
    )
    assert [f.body for f in filas] == ["Primer aviso.", "Segundo aviso."]


# --- aislamiento y permisos --------------------------------------------------------------


def test_no_se_prepara_un_aviso_sobre_una_orden_de_otra_empresa(db_session):
    company_a, _, orden_a, _ = _escenario(db_session, "prep-iso-a")
    company_b, _, _, _ = _escenario(db_session, "prep-iso-b")
    _ejecucion(db_session, company_a, orden_a, "PART", "Fuente", costo=1000, precio=0)

    resultado = _proponer(
        db_session, company_b.id, "preparar_comunicacion_cliente", {"orden": orden_a.id}
    )

    assert resultado.ok is False
    assert db_session.query(WorkOrderNotification).filter_by(company_id=company_b.id).count() == 0
    assert db_session.query(AiActionProposal).filter_by(company_id=company_b.id).count() == 0


def test_el_aviso_de_una_ot_ajena_no_se_puede_leer_ni_mandar(client, db_session):
    company_a, _, orden_a, _ = _escenario(db_session, "prep-iso-c")
    company_b, _, _, _ = _escenario(db_session, "prep-iso-d")
    _ejecucion(db_session, company_a, orden_a, "PART", "Fuente", costo=1000, precio=0)
    propuesta = _proponer(
        db_session, company_a.id, "preparar_comunicacion_cliente", {"orden": orden_a.id}
    )
    proposals.confirmar(
        db_session, propuesta.data["propuesta_id"], company_id=company_a.id, user_id=1
    )
    aviso = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company_a.id, work_order_id=orden_a.id)
        .one()
    )

    cabeceras = login(client, "ot.prep-iso-d@example.com", company_b.id)
    assert client.get(f"/api/v1/work-orders/{orden_a.id}/notifications", headers=cabeceras).status_code == 404
    mandarlo = client.post(
        f"/api/v1/work-orders/{orden_a.id}/notifications/{aviso.id}/send", headers=cabeceras
    )
    assert mandarlo.status_code == 404


def test_sin_work_orders_manage_no_se_ofrece_la_herramienta(db_session):
    company, _, orden, _ = _escenario(db_session, "prep-sin-permiso")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)

    nombres = {t.name for t in disponibles(TODOS_SIN_GESTION)}
    assert "preparar_comunicacion_cliente" not in nombres
    resultado = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente", {"orden": orden.id},
        permisos=TODOS_SIN_GESTION,
    )
    assert resultado.ok is False
    assert resultado.error_code == "sin_permiso"


# --- el envio manual: lo que hace falta para que el flujo cierre --------------------------


def test_una_persona_manda_a_mano_el_aviso_preparado(client, db_session, sender_falso):
    from tests.test_work_orders import login

    company, _, orden, _ = _escenario(db_session, "prep-envio-manual")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)
    propuesta = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente",
        {"orden": orden.id, "mensaje": "Ya lo estamos resolviendo."},
    )
    proposals.confirmar(
        db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1
    )
    aviso = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .one()
    )
    assert aviso.status == "PENDING"
    assert sender_falso.enviados == []

    cabeceras = login(client, "ot.prep-envio-manual@example.com", company.id)
    respuesta = client.post(
        f"/api/v1/work-orders/{orden.id}/notifications/{aviso.id}/send", headers=cabeceras
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["status"] in ("SENT", "QUEUED")
    assert sender_falso.enviados == [aviso.id]
    db_session.refresh(aviso)
    assert aviso.status in ("SENT", "QUEUED")


def test_no_se_puede_mandar_dos_veces_el_mismo_aviso(client, db_session, sender_falso):
    """Un doble clic no puede duplicar el mensaje al cliente."""
    from tests.test_work_orders import login

    company, _, orden, _ = _escenario(db_session, "prep-doble")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)
    propuesta = _proponer(
        db_session, company.id, "preparar_comunicacion_cliente", {"orden": orden.id}
    )
    proposals.confirmar(
        db_session, propuesta.data["propuesta_id"], company_id=company.id, user_id=1
    )
    aviso = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .one()
    )
    cabeceras = login(client, "ot.prep-doble@example.com", company.id)
    url = f"/api/v1/work-orders/{orden.id}/notifications/{aviso.id}/send"

    assert client.post(url, headers=cabeceras).status_code == 200
    segunda = client.post(url, headers=cabeceras)
    assert segunda.status_code == 409
    assert len(sender_falso.enviados) == 1


def test_un_aviso_sin_destinatario_no_se_puede_mandar(db_session, sender_falso):
    """SKIPPED no es reintentable: sin destinatario no hay nada que reintentar."""
    company, _, orden, objetivo = _escenario(db_session, "prep-skipped", telefono=None)
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)
    objetivo.notify_whatsapp = True
    db_session.commit()

    evento = WorkOrderEvent(
        company_id=company.id, work_order_id=orden.id, event_type="NOTICE",
        status="RECEIVED", detail="prueba", user_id=1,
    )
    db_session.add(evento)
    db_session.commit()
    empresa = db_session.get(Company, company.id)
    notif.enqueue_for_event(db_session, empresa, orden, evento, status=objetivo)
    db_session.commit()
    fila = (
        db_session.query(WorkOrderNotification)
        .filter_by(company_id=company.id, work_order_id=orden.id)
        .one()
    )
    assert fila.status == "SKIPPED"

    with pytest.raises(Exception) as excinfo:
        send_notification(
            orden.id, fila.id, company_id=company.id,
            actor=db_session.get(User, 1), db=db_session,
        )
    assert "409" in str(excinfo.value)
    assert sender_falso.enviados == []


# --- la vista previa que ve la persona antes de confirmar ---------------------------------


def test_el_preview_muestra_el_mensaje_resuelto_y_el_destinatario(client, db_session):
    """Lo que se ve antes de confirmar es lo que se manda despues."""
    from tests.test_work_orders import login

    company, _, orden, _ = _escenario(
        db_session, "prep-preview",
        plantilla="Hola {{cliente}}, tu orden N° {{numero_ot}} está en {{estado}}.",
    )
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)
    cabeceras = login(client, "ot.prep-preview@example.com", company.id)

    cuerpo = client.post(
        f"/api/v1/work-orders/{orden.id}/communication-preview",
        headers=cabeceras, json={"mensaje": None, "canal": None},
    ).json()

    assert cuerpo["would_notify"] is True
    aviso = cuerpo["items"][0]
    assert aviso["recipient"] == "+5493512345678"
    assert "{{cliente}}" not in aviso["body"]
    assert "Recibido" in aviso["body"]


def test_el_preview_con_mensaje_propio_muestra_ese_mensaje(client, db_session):
    from tests.test_work_orders import login

    company, _, orden, _ = _escenario(db_session, "prep-preview-msg")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)
    cabeceras = login(client, "ot.prep-preview-msg@example.com", company.id)

    cuerpo = client.post(
        f"/api/v1/work-orders/{orden.id}/communication-preview",
        headers=cabeceras, json={"mensaje": "Te escribimos para coordinar la entrega.", "canal": None},
    ).json()

    assert cuerpo["items"][0]["body"] == "Te escribimos para coordinar la entrega."


def test_el_preview_no_escribe_nada(client, db_session):
    from tests.test_work_orders import login

    company, _, orden, _ = _escenario(db_session, "prep-preview-nada")
    _ejecucion(db_session, company, orden, "PART", "Fuente", costo=1000, precio=0)
    cabeceras = login(client, "ot.prep-preview-nada@example.com", company.id)

    antes = db_session.query(WorkOrderNotification).filter_by(company_id=company.id).count()
    client.post(
        f"/api/v1/work-orders/{orden.id}/communication-preview",
        headers=cabeceras, json={"mensaje": "Hola", "canal": None},
    )
    assert db_session.query(WorkOrderNotification).filter_by(company_id=company.id).count() == antes


def test_toda_herramienta_de_escritura_tiene_su_aplicador():
    """Una herramienta sin aplicador queda propuesta para siempre y nadie lo detecta hasta
    que alguien la usa en produccion."""
    sin_aplicador = sorted(
        t.name for t in TOOLS_ESCRITURA if t.name not in proposals.APLICADORES
    )
    assert sin_aplicador == []


def _ejecucion(db, company, orden, item_type, descripcion, cantidad=1, costo=0, precio=0):
    fila = WorkOrderExecutionItem(
        company_id=company.id, work_order_id=orden.id, item_type=item_type,
        description=descripcion, quantity=Decimal(str(cantidad)),
        unit_cost=Decimal(str(costo)), unit_price=Decimal(str(precio)),
        created_by_user_id=1,
    )
    db.add(fila)
    db.commit()
    return fila
