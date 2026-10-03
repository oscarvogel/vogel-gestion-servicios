"""Herramientas de escritura con confirmacion humana (#44 sub-issue 3).

La regla de oro: **la IA propone, la persona confirma**. Lo que estos tests tienen que
demostrar es que la separacion es real, no de archivo. Si una herramienta de escritura
llegara a escribir por su cuenta, el sistema seria auditable en teoria y no en la practica.

Por eso los tests no preguntan "¿la propuesta quedo bien?". Preguntan:

- ¿se escribio algo sin que nadie confirmara? (no tiene que haber escrito nada)
- ¿se escribio lo que propuso el modelo o lo que confirmo la persona? (lo que confirmo)
- ¿un reintento duplica la operacion? (no)
- ¿la propuesta de otra empresa existe? (no)
- ¿se avisa al cliente antes de que el mensaje sea irreversible? (si, al proponer)
"""
from __future__ import annotations

import json

import pytest

from app.models.ai_action_proposal import (
    APLICADA,
    FALLIDA,
    PENDIENTE,
    RECHAZADA,
    RIESGO_COMUNICACION,
    RIESGO_FINANCIERO,
    RIESGO_NINGUNO,
    AiActionProposal,
)
from app.models.customer import Customer, Equipment
from app.models.role import CompanyUserRole, Permission, Role, role_permissions
from app.models.user import CompanyUser
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.work_order_quote import WorkOrderExecutionItem
from app.services.ai import proposals
from app.services.ai.providers.base import LlmResponse, LlmToolCall
from app.services.ai.providers.fake import FakeProvider
from app.services.ai.registry import PROVIDERS
from app.services.ai.tools import ToolContext, disponibles, ejecutar
from tests.test_ai import _dar_permiso_ia, _habilitar
from tests.test_work_orders import login, setup

TODOS = frozenset(
    {
        "ai.use", "customers.view", "customers.manage", "equipment.view", "equipment.manage",
        "work_orders.view", "work_orders.manage",
    }
)


def _contexto(db, company_id, permisos=TODOS, user_id=1):
    return ToolContext(db=db, company_id=company_id, user_id=user_id, permissions=permisos)


def _proponer(db, company_id, tool, argumentos, user_id=1, permisos=TODOS):
    return ejecutar(tool, argumentos, _contexto(db, company_id, permisos, user_id))


def _pendientes(db, company_id):
    return db.query(AiActionProposal).filter_by(company_id=company_id, status=PENDIENTE).all()


# --- el nucleo: proponer no es escribir -------------------------------------------------


def test_proponer_un_cliente_no_escribe_nada(db_session):
    """La herramienta deja la propuesta y no toca la tabla de clientes."""
    a, _, _, _ = setup(db_session, "prop-no-escribe")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    antes = db_session.query(Customer).filter_by(company_id=a.id).count()
    resultado = _proponer(db_session, a.id, "crear_cliente", {"nombre": "Cliente Nuevo SA"})

    assert resultado.ok is True
    assert resultado.data["estado"] == PENDIENTE
    assert resultado.data["propuesta_id"]
    # Esto es lo importante: la base quedo igual.
    assert db_session.query(Customer).filter_by(company_id=a.id).count() == antes
    assert db_session.query(Customer).filter_by(company_id=a.id, name="Cliente Nuevo SA").first() is None


def test_proponer_una_ot_no_crea_la_ot_ni_consume_numero(db_session):
    """Ni la orden ni el contador se tocan hasta que alguien confirme."""
    a, _, ca, ea = setup(db_session, "prop-ot")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    antes_ots = db_session.query(WorkOrder).filter_by(company_id=a.id).count()
    _proponer(
        db_session, a.id, "crear_ot",
        {"cliente_id": ca.id, "equipo_id": ea.id, "falla_reportada": "No enciende"},
    )

    assert db_session.query(WorkOrder).filter_by(company_id=a.id).count() == antes_ots
    from app.models.work_order import WorkOrderCounter

    contador = db_session.get(WorkOrderCounter, a.id)
    assert contador is None, "el numero de orden no se puede reservar sin que haya confirmacion"


def test_las_siete_herramientas_de_escritura_solo_proponen(db_session):
    """Ninguna de las siete escribe al ejecutarse, y cada una deja su propuesta."""
    a, _, ca, ea = setup(db_session, "prop-siete")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)
    db_session.add(Customer(company_id=a.id, name="Cliente con WhatsApp", whatsapp="3511112222"))
    db_session.commit()
    orden = _crear_ot(db_session, a.id, ca.id, ea.id, "Falla para el historial")

    casos = {
        "crear_cliente": {"nombre": "Nuevo"},
        "crear_equipo": {"cliente_id": ca.id, "categoria": "Televisor", "marca": "Sony"},
        "crear_ot": {"cliente_id": ca.id, "equipo_id": ea.id, "falla_reportada": "otra"},
        "actualizar_ot": {"orden": orden.id, "estado": "Listo"},
        "agregar_diagnostico": {"orden": orden.id, "diagnostico": "Placa"},
        "agregar_trabajo": {"orden": orden.id, "descripcion": "Cambio de fuente"},
        "agregar_repuesto": {"orden": orden.id, "descripcion": "Fuente 12V", "precio_unitario": 4500},
    }

    for nombre, argumentos in casos.items():
        resultado = _proponer(db_session, a.id, nombre, argumentos)
        assert resultado.ok is True, f"{nombre}: {resultado.error_message}"
        assert resultado.data["estado"] == PENDIENTE, nombre

    assert len(_pendientes(db_session, a.id)) == len(casos)
    # Y nada se escribio: ni ordenes, ni items, ni diagnosticos.
    assert db_session.query(WorkOrder).filter_by(company_id=a.id).count() == 1
    assert db_session.query(WorkOrderExecutionItem).filter_by(company_id=a.id).count() == 0


# --- confirmar: escribe lo confirmado, no lo propuesto ----------------------------------


def test_confirmar_escribe_lo_que_la_persona_corrijo(db_session, client):
    """La diferencia entre lo propuesto y lo confirmado es lo que se escribe.

    Este es el criterio central del sub-issue: si el modelo propone un nombre y el operador lo
    corrige, tiene que quedar el del operador.
    """
    a, _, _, _ = setup(db_session, "corrige")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    _proponer(db_session, a.id, "crear_cliente", {"nombre": "CLIENTE MAL ESCRITO", "telefono": "111"})
    pendiente = _pendientes(db_session, a.id)[0]

    r = client.post(
        f"/api/v1/ai/propuestas/{pendiente.id}/confirmar",
        headers=login(client, "ot.corrige@example.com", a.id),
        json={"argumentos": {"nombre": "Cliente Bien Escrito SA", "telefono": "999"}},
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["status"] == APLICADA
    # La pantalla puede ver que se corrigio algo.
    assert cuerpo["lo_que_cambio"] == {"nombre": "Cliente Bien Escrito SA", "telefono": "999"}
    # Y en la base quedo lo corregido, no lo propuesto.
    fila = db_session.query(Customer).filter_by(company_id=a.id, name="Cliente Bien Escrito SA").first()
    assert fila is not None
    assert fila.phone == "999"
    assert db_session.query(Customer).filter_by(company_id=a.id, name="CLIENTE MAL ESCRITO").first() is None


def test_confirmar_sin_correcciones_escribe_lo_propuesto(db_session, client):
    a, _, _, _ = setup(db_session, "sin-correccion")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    _proponer(db_session, a.id, "crear_cliente", {"nombre": "Tal cual", "documento": "20111222"})
    pendiente = _pendientes(db_session, a.id)[0]

    r = client.post(
        f"/api/v1/ai/propuestas/{pendiente.id}/confirmar",
        headers=login(client, "ot.sin-correccion@example.com", a.id),
        json={},
    )
    assert r.status_code == 200, r.text
    assert r.json()["argumentos_confirmados"] == {"nombre": "Tal cual", "documento": "20111222"}
    fila = db_session.query(Customer).filter_by(company_id=a.id, name="Tal cual").first()
    assert fila is not None and fila.document == "20111222"


# --- reintentar no duplica ---------------------------------------------------------------


def test_confirmar_dos_veces_no_duplica(db_session, client):
    """Un doble clic, o un reintento del navegador, no puede crear dos clientes."""
    a, _, _, _ = setup(db_session, "doble-clic")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    _proponer(db_session, a.id, "crear_cliente", {"nombre": "Un Solo Cliente"})
    pendiente = _pendientes(db_session, a.id)[0]
    h = login(client, "ot.doble-clic@example.com", a.id)

    primero = client.post(f"/api/v1/ai/propuestas/{pendiente.id}/confirmar", headers=h, json={})
    segundo = client.post(f"/api/v1/ai/propuestas/{pendiente.id}/confirmar", headers=h, json={})

    assert primero.status_code == 200, primero.text
    # El segundo no es un error: devuelve lo que ya se hizo, y lo dice.
    assert segundo.status_code == 200, segundo.text
    assert segundo.json()["ya_se_habia_aplicado"] is True
    assert segundo.json()["resultado"] == primero.json()["resultado"]

    assert db_session.query(Customer).filter_by(company_id=a.id, name="Un Solo Cliente").count() == 1


def test_rechazar_impide_confirmar_despues(db_session, client):
    a, _, _, _ = setup(db_session, "rechazada")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    _proponer(db_session, a.id, "crear_cliente", {"nombre": "No Se Crea"})
    pendiente = _pendientes(db_session, a.id)[0]
    h = login(client, "ot.rechazada@example.com", a.id)

    r = client.post(f"/api/v1/ai/propuestas/{pendiente.id}/rechazar", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == RECHAZADA

    confirmar = client.post(f"/api/v1/ai/propuestas/{pendiente.id}/confirmar", headers=h, json={})
    assert confirmar.status_code == 409
    assert db_session.query(Customer).filter_by(company_id=a.id, name="No Se Crea").first() is None


# --- aislamiento y permisos ---------------------------------------------------------------


def test_una_propuesta_de_otra_empresa_no_existe(db_session, client):
    """Confirmar el id de otra empresa da 404, no aplica nada."""
    a, _, _, _ = setup(db_session, "tenant-a")
    b, _, _, _ = setup(db_session, "tenant-b")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)
    _dar_permiso_ia(db_session, b.id)

    _proponer(db_session, a.id, "crear_cliente", {"nombre": "De la empresa A"})
    pendiente = _pendientes(db_session, a.id)[0]

    r = client.post(
        f"/api/v1/ai/propuestas/{pendiente.id}/confirmar",
        headers=login(client, "ot.tenant-b@example.com", b.id),
        json={},
    )
    assert r.status_code == 404
    assert db_session.query(Customer).filter_by(company_id=a.id, name="De la empresa A").first() is None
    assert _pendientes(db_session, a.id), "la propuesta de A sigue pendiente"


def test_confirmar_exige_el_permiso_de_la_herramienta_no_solo_ai_use(client, db_session):
    """Poder usar el asistente no es poder dar de alta clientes."""
    a, _, _, _ = setup(db_session, "sin-permiso-clientes")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)
    _quitar_permisos(db_session, a.id, {"customers.manage"})

    _proponer(db_session, a.id, "crear_cliente", {"nombre": "No Debe Crearse"})
    pendiente = _pendientes(db_session, a.id)[0]

    r = client.post(
        f"/api/v1/ai/propuestas/{pendiente.id}/confirmar",
        headers=login(client, "ot.sin-permiso-clientes@example.com", a.id),
        json={},
    )

    assert r.status_code == 403
    assert "customers.manage" in r.json()["detail"]
    assert db_session.query(Customer).filter_by(company_id=a.id, name="No Debe Crearse").first() is None
    # Y la propuesta sigue pendiente: se puede confirmar mas tarde con alguien que si pueda.
    assert db_session.get(AiActionProposal, pendiente.id).status == PENDIENTE


def test_la_herramienta_de_escritura_no_se_ofrece_sin_su_permiso(db_session):
    """Sin customers.manage, el modelo ni ve que exista crear_cliente."""
    nombres = {t.name for t in disponibles({"work_orders.manage"})}
    assert "crear_ot" in nombres
    assert "crear_cliente" not in nombres
    assert "crear_equipo" not in nombres


def test_ejecutar_una_herramienta_de_escritura_sin_permiso_no_propone(db_session):
    a, _, _, _ = setup(db_session, "escritura-sin-permiso")
    resultado = _proponer(
        db_session, a.id, "crear_cliente", {"nombre": "X"},
        permisos={"customers.view"},
    )
    assert resultado.ok is False
    assert resultado.error_code == "sin_permiso"
    assert _pendientes(db_session, a.id) == []


# --- riesgo: financiero y comunicacion ---------------------------------------------------


def test_un_repuesto_con_precio_queda_marcado_como_financiero(db_session):
    a, _, ca, ea = setup(db_session, "riesgo-dinero")
    orden = _crear_ot(db_session, a.id, ca.id, ea.id, "Falla")

    con_precio = _proponer(
        db_session, a.id, "agregar_repuesto",
        {"orden": orden.id, "descripcion": "Fuente", "precio_unitario": 4500},
    )
    sin_precio = _proponer(
        db_session, a.id, "agregar_repuesto", {"orden": orden.id, "descripcion": "Tornillo"}
    )

    assert con_precio.data["riesgo"] == RIESGO_FINANCIERO
    # Sin precio no mueve plata, asi que no se marca.
    assert sin_precio.data["riesgo"] == RIESGO_NINGUNO


def test_un_estado_con_aviso_avisa_que_va_a_escribirle_al_cliente(db_session):
    """El aviso se sabe al proponer, no despues de aplicar: un WhatsApp no se deshace."""
    a, _, ca, ea = setup(db_session, "riesgo-comunicacion")
    ca.whatsapp = "3511112222"
    db_session.commit()
    orden = _crear_ot(db_session, a.id, ca.id, ea.id, "Falla")
    avisando = _estado(db_session, a.id, "Avisar al cliente", notify_whatsapp=True)
    callado = _estado(db_session, a.id, "En repairs", notify_whatsapp=False)

    con_aviso = _proponer(db_session, a.id, "actualizar_ot", {"orden": orden.id, "estado": "Avisar al cliente"})
    sin_aviso = _proponer(db_session, a.id, "actualizar_ot", {"orden": orden.id, "estado": "Listo"})

    assert con_aviso.data["avisa_al_cliente"] is True
    assert con_aviso.data["riesgo"] == RIESGO_COMUNICACION
    assert sin_aviso.data["avisa_al_cliente"] is False
    assert sin_aviso.data["riesgo"] == RIESGO_NINGUNO
    # Y en ningun caso se encolo nada todavia.
    from app.models.work_order import WorkOrderNotification

    assert db_session.query(WorkOrderNotification).filter_by(company_id=a.id).count() == 0


def test_confirmar_un_estado_con_aviso_encola_la_notificacion(db_session, client):
    a, _, ca, ea = setup(db_session, "confirma-aviso")
    _dar_permiso_ia(db_session, a.id)
    ca.whatsapp = "3511112222"
    db_session.commit()
    orden = _crear_ot(db_session, a.id, ca.id, ea.id, "Falla")
    _estado(db_session, a.id, "Avisar al cliente", notify_whatsapp=True, notification_template="Hola {{cliente}}")

    _proponer(db_session, a.id, "actualizar_ot", {"orden": orden.id, "estado": "Avisar al cliente"})
    pendiente = _pendientes(db_session, a.id)[0]
    r = client.post(
        f"/api/v1/ai/propuestas/{pendiente.id}/confirmar",
        headers=login(client, "ot.confirma-aviso@example.com", a.id),
        json={},
    )

    assert r.status_code == 200, r.text
    assert r.json()["notificado"] is True
    # El estado quedo aplicado y el aviso quedo encolado para que lo tome el drenaje.
    db_session.refresh(db_session.get(WorkOrder, orden.id))
    assert db_session.get(WorkOrder, orden.id).status == "AVISAR_AL_CLIENTE"
    from app.models.work_order import WorkOrderNotification

    assert db_session.query(WorkOrderNotification).filter_by(company_id=a.id).count() >= 1


# --- la propuesta que no se puede aplicar queda registrada --------------------------------


def test_una_propuesta_invalida_queda_fallida_con_su_motivo(db_session, client):
    """El intento fallido tambien es auditabilidad: queda la fila y el por que."""
    a, _, _, _ = setup(db_session, "fallida")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    _proponer(db_session, a.id, "crear_cliente", {"nombre": "Ganador"})
    pendiente = _pendientes(db_session, a.id)[0]

    # La persona corrige el nombre a algo que ya existe con ese documento.
    db_session.add(Customer(company_id=a.id, name="Otro", document="20303030"))
    db_session.commit()
    r = client.post(
        f"/api/v1/ai/propuestas/{pendiente.id}/confirmar",
        headers=login(client, "ot.fallida@example.com", a.id),
        json={"argumentos": {"nombre": "Imposible", "documento": "20303030"}},
    )

    assert r.status_code >= 400
    fila = db_session.get(AiActionProposal, pendiente.id)
    assert fila.status == FALLIDA
    assert "documento" in (fila.result_error or "").lower()
    assert db_session.query(Customer).filter_by(company_id=a.id, name="Imposible").first() is None


def test_el_agente_crear_cliente_rechaza_documento_duplicado_al_confirmar(db_session, client):
    a, _, _, _ = setup(db_session, "doc-duplicado")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)
    db_session.add(Customer(company_id=a.id, name="Existente", document="20202020"))
    db_session.commit()

    _proponer(db_session, a.id, "crear_cliente", {"nombre": "Nuevo", "documento": "20202020"})
    pendiente = _pendientes(db_session, a.id)[0]
    r = client.post(
        f"/api/v1/ai/propuestas/{pendiente.id}/confirmar",
        headers=login(client, "ot.doc-duplicado@example.com", a.id),
        json={},
    )
    assert r.status_code == 409
    assert "20202020" in r.json()["detail"]


# --- de punta a punta: el modelo propone y el operador confirma ----------------------------


def test_de_punta_a_punta_el_modelo_propone_y_hasta_entonces_no_paso_nada(
    client, db_session, monkeypatch
):
    """La conversacion completa: el modelo pide, queda pendiente, y el dominio no se movio."""
    a, _, ca, ea = setup(db_session, "puntapunta")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    provider = FakeProvider(
        tool_calls=[LlmToolCall(id="c1", name="crear_cliente",
                                arguments={"nombre": "Cliente Pedido Por La IA"})]
    )
    monkeypatch.setitem(PROVIDERS, "fake", lambda: provider)
    monkeypatch.setattr("app.services.ai.registry.settings.ai_provider", "fake", raising=False)

    h = login(client, "ot.puntapunta@example.com", a.id)
    antes = db_session.query(Customer).filter_by(company_id=a.id).count()

    r = client.post(
        "/api/v1/ai/chat",
        headers=h,
        json={"messages": [{"role": "user", "content": "da de alta a un cliente nuevo"}],
              "con_herramientas": True},
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["ok"] is True
    # La respuesta trae la propuesta pendiente para que la pantalla la muestre.
    assert len(cuerpo["propuestas"]) == 1
    propuesta = cuerpo["propuestas"][0]
    assert propuesta["tool"] == "crear_cliente"
    assert propuesta["argumentos_propuestos"]["nombre"] == "Cliente Pedido Por La IA"
    assert propuesta["argumentos_confirmados"] is None
    # Y no se escribio nada.
    assert db_session.query(Customer).filter_by(company_id=a.id).count() == antes

    # Ahora el operador confirma, y recien ahi existe el cliente.
    confirmar = client.post(
        f"/api/v1/ai/propuestas/{propuesta['id']}/confirmar", headers=h, json={}
    )
    assert confirmar.status_code == 200, confirmar.text
    fila = db_session.query(Customer).filter_by(company_id=a.id, name="Cliente Pedido Por La IA").first()
    assert fila is not None
    # Y queda el rastro de quien propuso y quien confirmo.
    guardada = db_session.get(AiActionProposal, propuesta["id"])
    assert guardada.proposed_by_user_id == guardada.confirmed_by_user_id
    assert guardada.confirmed_at is not None and guardada.applied_at is not None
    assert json.loads(guardada.result_reference)["tipo"] == "cliente"


# --- helpers -----------------------------------------------------------------------------


def _quitar_permisos(db, company_id, codigos):
    from app.services.ai.tools.base import SIN_PERMISO  # noqa: F401

    for codigo in codigos:
        permiso = db.query(Permission).filter_by(code=codigo).one()
        db.execute(role_permissions.delete().where(
            role_permissions.c.permission_id == permiso.id))
    db.commit()


def _crear_ot(db, company_id, cliente_id, equipo_id, falla):
    from app.services import work_orders as wo

    orden = wo.crear_orden(
        db, company_id=company_id, user_id=1, customer_id=cliente_id,
        equipment_id=equipo_id, reported_fault=falla,
    )
    db.commit()
    return orden


def _estado(db, company_id, nombre, **flags):
    """Un estado propio de la empresa de la prueba.

    ``setup`` ya deja "En diagnóstico" y "Recibido", asi que los nombres tienen que ser
    distintos o choca contra el unique (company_id, name).
    """
    estado = WorkOrderStatus(
        company_id=company_id, name=nombre, color="#3B82F6", sort_order=90, active=True, **flags
    )
    db.add(estado)
    db.commit()
    return estado
