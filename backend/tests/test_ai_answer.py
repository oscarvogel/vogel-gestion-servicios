"""La respuesta con datos la arma el servidor, no el modelo (#44).

Esto existe por una medicion, no por una teoria. En los turnos de seguimiento, con la propia
respuesta anterior del modelo en el historial, MiniMax M3 contesta de memoria con fechas,
estados y cantidades inventadas, y cada corrida inventa otras distintas. Ni
``tool_choice: "required"`` ni un prompt estricto lo cortan.

La defensa no es pedirle que no invente: es que **no pueda escribir los datos**.

- La ficha la arma el servidor con los valores de la base.
- El texto del modelo no puede contener numeros ni estados. Si los contiene, se descarta
  entero y queda una frase neutra.

Los tests de aca comprueban las dos mitades: que la ficha diga la verdad, y que ningun dato
del modelo llegue al operador.
"""
from __future__ import annotations

import pytest

from app.models.work_order import WorkOrderStatus
from app.services.ai.answer import (
    TEXTO_NEUTRO,
    construir_ficha,
    estados_de_la_empresa,
    sanear,
)
from app.services.ai.providers.base import LlmResponse, LlmToolCall
from app.services.ai.providers.fake import FakeProvider
from app.services.ai.registry import PROVIDERS
from tests.test_ai import _dar_permiso_ia, _habilitar
from tests.test_ai_tools import _crear_orden
from tests.test_work_orders import login, setup


# --- el saneo del texto: la garantia --------------------------------------------------


def test_texto_con_un_numero_se_descarta():
    """Un numero es un dato, y los datos son de la ficha."""
    texto, saneado = sanear("Tiene 3 ordenes de trabajo.", estados=set())
    assert saneado is True
    assert texto == TEXTO_NEUTRO
    assert "3" not in texto


def test_texto_con_una_fecha_se_descarta():
    _, saneado = sanear("La orden es del 15/03/2024.", estados=set())
    assert saneado is True


def test_texto_con_un_estado_de_la_empresa_se_descarta():
    """El estado lo compara normalizado, asi que las tildes no lo salvan."""
    estados = {e for e in ("listo", "entregado", "endiagnostico")}

    for texto in (
        "El equipo esta Listo.",
        "El equipo esta listo",
        "Fue ENTREGADO ayer",
        "Esta en diagnostico",
        "Esta En Diagnóstico",
    ):
        _, saneado = sanear(texto, estados)
        assert saneado is True, texto


def test_texto_sin_datos_pasa_intacto():
    """Un comentario sin cifras ni estados es justo lo que se quiere del modelo."""
    for texto in (
        "Busqué y encontré el cliente.",
        "No encontré ese equipo en esta empresa.",
        "El historial te lo dejo en la ficha.",
    ):
        limpio, saneado = sanear(texto, estados={"listo", "entregado"})
        assert saneado is False
        assert limpio == texto


def test_un_estado_de_otra_empresa_no_invalida_el_texto():
    """Los estados son los de ESTA empresa: "Listo" de otra empresa no aplica."""
    limpio, saneado = sanear("El equipo esta en_revision.", estados={"entregado"})
    assert saneado is False
    assert limpio == "El equipo esta en_revision."


def test_texto_vacio_no_inventa_una_frase():
    limpio, saneado = sanear("   ", estados=set())
    assert limpio == ""
    assert saneado is False


# --- la ficha: los valores son los de la base -----------------------------------------


def test_la_ficha_trae_los_valores_de_la_base(db_session):
    a, _, ca, ea = setup(db_session, "ficha")
    ca.name = "Cliente De La Ficha"
    db_session.commit()
    _crear_orden(db_session, a, ea, "Falla que la reporta el cliente")

    resultados = ejecutar_historial(db_session, a.id, ea.id)
    ficha = construir_ficha([("consultar_historial_equipo", resultados)])

    assert len(ficha.bloques) == 1
    bloque = ficha.bloques[0]
    assert bloque["titulo"] == "Historial del equipo"
    assert bloque["vacio"] is False
    assert bloque["equipo"]["id"] == ea.id
    assert bloque["cantidad_de_ordenes"] == 1
    assert bloque["historial"][0]["falla_reportada"] == "Falla que la reporta el cliente"
    # El estado sale por nombre, y el nombre sale de la base, no de un enum del codigo.
    assert bloque["historial"][0]["estado"] == "Recibido"


def test_la_ficha_de_un_equipo_inexistente_marca_vacio(db_session):
    a, _, _, _ = setup(db_session, "ficha-vacia")
    resultados = ejecutar_historial(db_session, a.id, 999999)
    ficha = construir_ficha([("consultar_historial_equipo", resultados)])
    bloque = ficha.bloques[0]
    assert bloque["vacio"] is True
    assert bloque["historial"] == []


def test_una_busqueda_sin_coincidencias_marca_vacio(db_session):
    a, _, _, _ = setup(db_session, "ficha-sin-coincidencia")
    resultados = ejecutar_busqueda(db_session, a.id, "nombre-que-no-existe-xyz")
    ficha = construir_ficha([("buscar_cliente", resultados)])
    assert ficha.bloques[0]["vacio"] is True
    assert ficha.bloques[0]["resultados"] == []


def test_estados_de_la_empresa_solo_trae_los_suyos(db_session):
    a, _, _, _ = setup(db_session, "estados")
    db_session.add(WorkOrderStatus(company_id=a.id, name="En espera de repuesto", color="#000000",
                                   sort_order=90, active=True))
    b, _, _, _ = setup(db_session, "estados-b")
    db_session.add(WorkOrderStatus(company_id=b.id, name="Solo de la otra", color="#000000",
                                   sort_order=90, active=True))
    db_session.commit()

    estados = estados_de_la_empresa(db_session, a.id)

    assert "enesperaderepuesto" in estados
    assert "solodelaotra" not in estados


# --- de punta a punta: el operador no ve datos inventados ------------------------------


def test_el_operador_no_ve_datos_inventados_por_el_modelo(client, db_session, monkeypatch):
    """El proveedor simulado devuelve un texto lleno de datos inventados.

    Es exactamente lo que hace M3 en un turno de seguimiento. La respuesta tiene que llegar
    sin ninguno de esos valores, y con la ficha que si viene de la base.
    """
    a, _, ca, ea = setup(db_session, "inventa")
    ca.name = "Cliente Inventado"
    db_session.commit()
    _crear_orden(db_session, a, ea, "Falla real")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    class Alucina(FakeProvider):
        """Pide el historial y despues responde con un historial inventado."""

        def complete(self, messages, max_tokens=1024, tools=None):
            self.calls.append(list(messages))
            ya_hay_historial = any(
                m.role == "tool" and "Falla real" in m.content for m in messages
            )
            if not ya_hay_historial:
                return LlmResponse(
                    text="Voy a buscar.",
                    model=self.model_id(),
                    provider=self.name,
                    finish_reason="tool_calls",
                    tool_calls=[LlmToolCall(id="c1", name="consultar_historial_equipo",
                                            arguments={"equipo_id": ea.id})],
                )
            return LlmResponse(
                text=(
                    "El equipo tiene 5 ordenes de trabajo. La ultima es la P001, del "
                    "15/03/2024, en estado ENTREGADO, con falla de pantalla sin imagen."
                ),
                model=self.model_id(),
                provider=self.name,
                finish_reason="stop",
            )

    monkeypatch.setitem(PROVIDERS, "fake", lambda: Alucina())
    monkeypatch.setattr("app.services.ai.registry.settings.ai_provider", "fake", raising=False)

    r = client.post(
        "/api/v1/ai/chat",
        headers=login(client, "ot.inventa@example.com", a.id),
        json={"messages": [{"role": "user", "content": "historial del equipo"}], "con_herramientas": True},
    )

    assert r.status_code == 200, r.text
    cuerpo = r.json()

    # El texto que ve el operador no tiene ni un numero.
    assert cuerpo["texto_saneado"] is True
    assert cuerpo["text"] == TEXTO_NEUTRO
    formentation = ["5", "P001", "15/03/2024", "2024", "ENTREGADO"]
    for valor in ("5", "P001", "15/03/2024", "2024", "ENTREGADO"):
        assert valor not in cuerpo["text"], f"se le escapo {valor}"

    # Y los datos de verdad estan en la ficha, que la armo el servidor.
    assert cuerpo["consulto"] is True
    bloque = cuerpo["ficha"]["bloques"][0]
    assert bloque["historial"][0]["falla_reportada"] == "Falla real"
    assert bloque["historial"][0]["estado"] == "Recibido"


def test_una_respuesta_sin_consulta_queda_marcada(client, db_session, monkeypatch):
    """Si se pidieron herramientas y el modelo no consulto, el operador tiene que enterarse."""
    a, _, _, _ = setup(db_session, "sin-consulta")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    provider = FakeProvider(text="No encontre ese equipo en esta empresa.")
    monkeypatch.setitem(PROVIDERS, "fake", lambda: provider)
    monkeypatch.setattr("app.services.ai.registry.settings.ai_provider", "fake", raising=False)

    r = client.post(
        "/api/v1/ai/chat",
        headers=login(client, "ot.sin-consulta@example.com", a.id),
        json={"messages": [{"role": "user", "content": "hola"}], "con_herramientas": True},
    )

    cuerpo = r.json()
    assert cuerpo["ok"] is True
    assert cuerpo["consulto"] is False
    assert cuerpo["ficha"]["bloques"] == []
    # Sin datos inventados y sin ficha, el texto sigue siendo aceptable.
    assert cuerpo["text"] == "No encontre ese equipo en esta empresa."
    assert cuerpo["texto_saneado"] is False


def test_sin_herramientas_no_hay_ficha_ni_saneo(client, db_session, monkeypatch):
    """El camino sin herramientas no cambia: no hay nada que sanear ni ficha que armar."""
    a, _, _, _ = setup(db_session, "plano")
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)

    provider = FakeProvider(text="Hola, en que te puedo ayudar?")
    monkeypatch.setitem(PROVIDERS, "fake", lambda: provider)
    monkeypatch.setattr("app.services.ai.registry.settings.ai_provider", "fake", raising=False)

    cuerpo = client.post(
        "/api/v1/ai/chat",
        headers=login(client, "ot.plano@example.com", a.id),
        json={"messages": [{"role": "user", "content": "hola"}]},
    ).json()

    assert cuerpo["text"] == "Hola, en que te puedo ayudar?"
    assert cuerpo["ficha"] == {"bloques": [], "consultas": []}
    assert cuerpo["consulto"] is False
    assert cuerpo["texto_saneado"] is False


# --- helpers ---------------------------------------------------------------------------


def ejecutar_historial(db, company_id, equipo_id):
    from app.services.ai.tools import ToolContext, ejecutar

    ctx = ToolContext(
        db=db,
        company_id=company_id,
        user_id=1,
        permissions=frozenset({"work_orders.view", "equipment.view"}),
    )
    return ejecutar("consultar_historial_equipo", {"equipo_id": equipo_id}, ctx).data


def ejecutar_busqueda(db, company_id, texto):
    from app.services.ai.tools import ToolContext, ejecutar

    ctx = ToolContext(
        db=db,
        company_id=company_id,
        user_id=1,
        permissions=frozenset({"customers.view"}),
    )
    return ejecutar("buscar_cliente", {"texto": texto}, ctx).data
