"""Herramientas de solo lectura del asistente IA (#44, sub-issue 2).

Lo que estos tests tienen que demostrar no es que las herramientas funcionen, sino **que no
se pueden leer datos de otra empresa**. Son tres reglas, y cada una tiene su test:

1. El `company_id` sale de la sesion y el modelo no lo puede influenciar. Se prueba
   mandando un `company_id` en los argumentos y viendo que no cambia nada.
2. Un recurso de otra empresa devuelve vacio, no un error: un 404 por id permitiria
   enumerar los ids de otras empresas.
3. Sin permiso, la herramienta no se ofrece y, si se pide igual, falla con un motivo
   tipado. Nunca es un 500.
"""
from __future__ import annotations

import json

import pytest

from app.models.customer import Customer, Equipment
from app.models.role import Permission, role_permissions
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.services.ai import chat as ai_chat
from app.services.ai.providers.base import ROLE_TOOL, LlmMessage, LlmToolCall
from app.services.ai.providers.fake import FakeProvider
from app.services.ai.registry import PROVIDERS
from app.services.ai.tools import ToolContext, disponibles, ejecutar
from app.services.ai.tools.base import (
    ARGUMENTOS_INVALIDOS,
    DESCONOCIDA,
    SIN_PERMISO,
)
from app.services.ai.tools.registry import catalogo_para_proveedor
from app.services.ai.usage import OK
from tests.test_ai import _dar_permiso_ia, _habilitar
from tests.test_work_orders import login, setup

TODOS = frozenset(
    {"ai.use", "customers.view", "customers.manage", "equipment.view", "work_orders.view"}
)


def _contexto(db, company_id, permisos=TODOS, user_id=None):
    return ToolContext(db=db, company_id=company_id, user_id=user_id, permissions=permisos)


# --- el catalogo que ve el modelo ----------------------------------------------------


def test_sin_permiso_no_se_ofrece_la_herramienta(db_session):
    """Un operador sin equipment.view ni ve que exista buscar_equipo.

    Es distinto de que la herramienta se niegue: si se le ofrece y después falla, el modelo
    le promete al operador algo que va a salir con un error.
    """
    a, _, _, _ = setup(db_session, "herr-a")
    b, _, _, _ = setup(db_session, "herr-b")
    _dar_permiso_ia(db_session, a.id)
    _dar_permiso_ia(db_session, b.id)

    con_equipment = disponibles({"customers.view", "equipment.view", "work_orders.view"})
    sin_equipment = disponibles({"customers.view"})

    assert "buscar_equipo" in {t.name for t in con_equipment}
    assert "buscar_equipo" not in {t.name for t in sin_equipment}
    # Y el catalogo que se manda al proveedor tampoco lo menciona.
    assert "buscar_equipo" not in json.dumps(catalogo_para_proveedor({"customers.view"}))


def test_ejecutar_sin_permiso_devuelve_motivo_tipado(db_session):
    """Aunque se la pida a mano, la herramienta revisa el permiso y no toca la base."""
    a, _, _, _ = setup(db_session, "perm-a")
    _dar_permiso_ia(db_session, a.id)
    ctx = _contexto(db_session, a.id, permisos={"customers.view"})

    resultado = ejecutar("buscar_equipo", {"texto": "Samsung"}, ctx)

    assert resultado.ok is False
    assert resultado.error_code == SIN_PERMISO
    # El motivo no le dice al modelo que la herramienta existe en otra parte ni que hay
    # equipos: no hay nada que enumerar.
    assert "Samsung" not in (resultado.error_message or "")


def test_herramienta_desconocida_no_revienta(db_session):
    a, _, _, _ = setup(db_session, "desc")
    resultado = ejecutar("borrar_todo", {}, _contexto(db_session, a.id))
    assert resultado.ok is False
    assert resultado.error_code == DESCONOCIDA


# --- aislamiento entre empresas ------------------------------------------------------


def test_buscar_cliente_no_trae_clientes_de_otra_empresa(db_session):
    a, _, ca, _ = setup(db_session, "iso-a")
    b, _, cb, _ = setup(db_session, "iso-b")
    ca.name = "Nombre Repetido"
    ca.phone = "1112223333"
    cb.name = "Nombre Repetido"
    cb.phone = "4445556666"
    db_session.commit()

    resultados = ejecutar("buscar_cliente", {"texto": "Nombre Repetido"}, _contexto(db_session, a.id))

    assert resultados.ok is True
    nombres = {r["id"] for r in resultados.data["resultados"]}
    assert nombres == {ca.id}
    assert cb.id not in resultados.data["resultados"]


def test_el_modelo_no_puede_pedir_otra_empresa(db_session):
    """Un company_id en los argumentos se ignora: la empresa es la de la sesion.

    Este es el test que sostiene la decision de arquitectura. El esquema JSON de la
    herramienta ni siquiera declara company_id, pero un modelo puede inventar un argumento
    extra, asi que lo que importa es que sobrante se ignore.
    """
    a, _, ca, _ = setup(db_session, "arg-a")
    b, _, cb, _ = setup(db_session, "arg-b")
    ca.name = "Compartido"
    cb.name = "Compartido"
    db_session.commit()

    contexto = _contexto(db_session, a.id)
    con_argumento = ejecutar(
        "buscar_cliente", {"texto": "Compartido", "company_id": b.id, "empresa": b.id}, contexto
    )

    assert con_argumento.ok is True
    assert [r["id"] for r in con_argumento.data["resultados"]] == [ca.id]


def test_historial_de_un_equipo_de_otra_empresa_devuelve_vacio(db_session):
    """Un id que existe en otra empresa devuelve `encontrado: false`, no sus ordenes.

    Un error distinto de "no existe" permitiria enumerar ids ajenos probando de a uno.
    """
    a, _, _, ea = setup(db_session, "hist-a")
    b, _, _, eb = setup(db_session, "hist-b")
    _crear_orden(db_session, b, eb, "Falla secreta de la otra empresa")
    _crear_orden(db_session, a, ea, "Falla propia")

    resultado = ejecutar("consultar_historial_equipo", {"equipo_id": eb.id}, _contexto(db_session, a.id))

    assert resultado.ok is True
    assert resultado.data["encontrado"] is False
    assert resultado.data["historial"] == []
    assert "secreta" not in json.dumps(resultado.data, ensure_ascii=False)


def test_el_historial_propio_trae_las_ordenes_con_estado_y_fecha(db_session):
    a, _, _, ea = setup(db_session, "hist-ok")
    _crear_orden(db_session, a, ea, "No enciende")

    resultado = ejecutar("consultar_historial_equipo", {"equipo_id": ea.id}, _contexto(db_session, a.id))

    assert resultado.ok is True
    assert resultado.data["encontrado"] is True
    assert resultado.data["cantidad_de_ordenes"] == 1
    orden = resultado.data["historial"][0]
    assert orden["falla_reportada"] == "No enciende"
    # El estado sale por nombre, no por el codigo interno: el modelo se lo muestra al
    # operador y "RECEIVED" no le sirve de nada.
    assert orden["estado"] == "Recibido"
    assert orden["recibida"] is not None


def test_buscar_equipo_busca_por_nombre_del_cliente(db_session):
    a, _, ca, ea = setup(db_session, "eq-a")
    b, _, cb, eb = setup(db_session, "eq-b")
    ca.name = "Cliente Buscable"
    db_session.commit()

    resultados = ejecutar("buscar_equipo", {"texto": "Cliente Buscable"}, _contexto(db_session, a.id))

    assert [r["id"] for r in resultados.data["resultados"]] == [ea.id]
    assert eb.id not in [r["id"] for r in resultados.data["resultados"]]


def test_un_comodin_en_el_texto_no_trae_todo(db_session):
    """Un '%' tipeado busca un '%', no devuelve la tabla entera."""
    a, _, ca, _ = setup(db_session, "like-a")
    _dar_cliente(db_session, a.id, "Nombre con porcento 100%")
    ca.name = "Traid"
    db_session.commit()

    todos = ejecutar("buscar_cliente", {"texto": "%"}, _contexto(db_session, a.id))
    assert len(todos.data["resultados"]) == 1, "el comodin deberia haber buscado el caracter"
    assert todos.data["resultados"][0]["nombre"] == "Nombre con porcento 100%"

    nada = ejecutar("buscar_cliente", {"texto": "%zzzz%"}, _contexto(db_session, a.id))
    assert nada.data["resultados"] == []


# --- argumentos invalidos: error tipado, no excepcion ----------------------------------


@pytest.mark.parametrize(
    "herramienta,args",
    [
        ("buscar_cliente", {}),
        ("buscar_cliente", {"texto": "   "}),
        ("buscar_cliente", {"texto": 5}),
        ("buscar_equipo", {"texto": None}),
        ("consultar_historial_equipo", {"equipo_id": "no-es-un-id"}),
        ("consultar_historial_equipo", {}),
    ],
)
def test_argumentos_invalidos_dan_motivo_tipado(db_session, herramienta, args):
    a, _, _, _ = setup(db_session, f"args-{herramienta}-{len(args)}")
    resultado = ejecutar(herramienta, args, _contexto(db_session, a.id))
    assert resultado.ok is False
    assert resultado.error_code == ARGUMENTOS_INVALIDOS


def test_el_limite_no_puede_desbordar(db_session):
    a, _, _, _ = setup(db_session, "limite")
    for i in range(30):
        _dar_cliente(db_session, a.id, f"Cliente {i:02d}")
    resultado = ejecutar("buscar_cliente", {"texto": "Cliente", "limite": 9999}, _contexto(db_session, a.id))
    assert len(resultado.data["resultados"]) <= 20


# --- el bucle de herramientas ---------------------------------------------------------


def test_el_modelo_pide_la_herramienta_y_el_resultado_vuelve_al_modelo(client, db_session, monkeypatch):
    """Round trip completo: el modelo pide, se ejecuta, y el resultado se le manda."""
    a, _, ca, ea = setup(db_session, "bucle")
    ca.name = "Cliente Del Bucle"
    ca.phone = "1122334455"
    db_session.commit()
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    provider = FakeProvider(
        tool_calls=[LlmToolCall(id="c1", name="buscar_cliente", arguments={"texto": "Cliente Del Bucle"})]
    )
    monkeypatch.setitem(PROVIDERS, "fake", lambda: provider)
    monkeypatch.setattr("app.services.ai.registry.settings.ai_provider", "fake", raising=False)

    r = client.post(
        "/api/v1/ai/chat",
        headers=login(client, "ot.bucle@example.com", a.id),
        json={"messages": [{"role": "user", "content": "Buscame al Cliente Del Bucle"}], "con_herramientas": True},
    )

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["ok"] is True
    # La respuesta final es texto, y el modelo recibio de verdad el resultado.
    assert cuerpo["text"] == "Respuesta de prueba del proveedor simulado."
    assert cuerpo["tool_calls"] == [{"name": "buscar_cliente", "ok": True, "error": None, "repetida": False}]
    # El segundo complete() llevo el mensaje de la herramienta con el dato adentro.
    ultimo = provider.calls[-1]
    mensaje_tool = [m for m in ultimo if m.role == ROLE_TOOL]
    assert len(mensaje_tool) == 1
    assert "Cliente Del Bucle" in mensaje_tool[0].content
    assert "1122334455" in mensaje_tool[0].content


def test_cada_herramienta_queda_registrada_con_su_operacion(client, db_session, monkeypatch):
    """El gasto se atribuye a la herramienta, no solo a la conversacion."""
    a, _, ca, _ = setup(db_session, "uso")
    ca.name = "Cliente Contable"
    db_session.commit()
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    provider = FakeProvider(
        tool_calls=[LlmToolCall(id="c1", name="buscar_cliente", arguments={"texto": "Cliente Contable"})]
    )
    monkeypatch.setitem(PROVIDERS, "fake", lambda: provider)
    monkeypatch.setattr("app.services.ai.registry.settings.ai_provider", "fake", raising=False)

    client.post(
        "/api/v1/ai/chat",
        headers=login(client, "ot.uso@example.com", a.id),
        json={"messages": [{"role": "user", "content": "buscalo"}], "con_herramientas": True},
    )

    from app.models.ai_usage import AiUsage

    operaciones = sorted(f.operation for f in db_session.query(AiUsage).all())
    assert "herramienta:buscar_cliente" in operaciones
    assert any(o.startswith("chat") for o in operaciones)
    assert all(f.status == OK for f in db_session.query(AiUsage).filter_by(operation="herramienta:buscar_cliente").all())


def test_una_herramienta_que_falla_no_rompe_la_conversacion(client, db_session, monkeypatch):
    """Argumentos malos: el modelo recibe el motivo y sigue, el request no es un 500."""
    a, _, _, _ = setup(db_session, "falla-herr")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    provider = FakeProvider(
        tool_calls=[LlmToolCall(id="c1", name="buscar_cliente", arguments={})]
    )
    monkeypatch.setitem(PROVIDERS, "fake", lambda: provider)
    monkeypatch.setattr("app.services.ai.registry.settings.ai_provider", "fake", raising=False)

    r = client.post(
        "/api/v1/ai/chat",
        headers=login(client, "ot.falla-herr@example.com", a.id),
        json={"messages": [{"role": "user", "content": "buscalo"}], "con_herramientas": True},
    )

    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["tool_calls"][0]["ok"] is False
    assert r.json()["tool_calls"][0]["error"] == ARGUMENTOS_INVALIDOS


def test_sin_con_herramientas_no_se_manda_el_catalogo(client, db_session, monkeypatch):
    """El default es no leer la base: el cliente tiene que pedirlo."""
    a, _, ca, _ = setup(db_session, "sin-herr")
    ca.name = "No Deberia Aparecer"
    db_session.commit()
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    provider = FakeProvider()
    monkeypatch.setitem(PROVIDERS, "fake", lambda: provider)
    monkeypatch.setattr("app.services.ai.registry.settings.ai_provider", "fake", raising=False)

    r = client.post(
        "/api/v1/ai/chat",
        headers=login(client, "ot.sin-herr@example.com", a.id),
        json={"messages": [{"role": "user", "content": "hola"}]},
    )

    assert r.status_code == 200
    assert provider.tools_seen == [None]
    assert r.json()["tool_calls"] == []


def test_el_bucle_termina_aunque_el_modelo_pida_herramientas_siempre(client, db_session, monkeypatch):
    """Un modelo que se pide una herramienta para siempre tiene que cortar."""
    a, _, ca, _ = setup(db_session, "loop")
    ca.name = "Loop"
    db_session.commit()
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    class Infinito(FakeProvider):
        def complete(self, messages, max_tokens=1024, tools=None):
            self.calls.append(list(messages))
            # Siempre pide una herramienta, nunca responde con texto.
            from app.services.ai.providers.base import LlmResponse

            return LlmResponse(
                text="",
                model=self.model_id(),
                provider=self.name,
                finish_reason="tool_calls",
                tool_calls=[LlmToolCall(id=f"c{len(self.calls)}", name="buscar_cliente", arguments={"texto": "Loop"})],
            )

    provider = Infinito()
    monkeypatch.setitem(PROVIDERS, "fake", lambda: provider)
    monkeypatch.setattr("app.services.ai.registry.settings.ai_provider", "fake", raising=False)

    r = client.post(
        "/api/v1/ai/chat",
        headers=login(client, "ot.loop@example.com", a.id),
        json={"messages": [{"role": "user", "content": "loop"}], "con_herramientas": True},
    )

    assert r.status_code == 200, r.text
    # Tantas vueltas como el tope, ni una mas: el costo tiene que estar acotado.
    assert len(provider.calls) == ai_chat.MAX_VUELTAS_HERRAMIENTAS
    assert len(r.json()["tool_calls"]) == ai_chat.MAX_VUELTAS_HERRAMIENTAS


# --- helpers -------------------------------------------------------------------------


def _dar_cliente(db, company_id, nombre, **extra):
    cliente = Customer(company_id=company_id, name=nombre, **extra)
    db.add(cliente)
    db.commit()
    return cliente


def _crear_orden(db, company, equipment, falla):
    estado = db.query(WorkOrderStatus).filter_by(company_id=company.id, is_initial=True).first()
    orden = WorkOrder(
        company_id=company.id,
        number=1,
        customer_id=equipment.customer_id,
        equipment_id=equipment.id,
        reported_fault=falla,
        received_by_user_id=1,
        status="RECEIVED",
        status_id=estado.id if estado else None,
    )
    db.add(orden)
    db.commit()
    return orden
