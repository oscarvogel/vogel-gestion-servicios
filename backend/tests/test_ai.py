"""Cimientos del modulo IA (#44, sub-issue 1).

El criterio que mas importa: **el sistema tiene que seguir siendo utilizable si el
proveedor de IA esta caido**. Eso se prueba, no se supone.
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.permissions import PERMISSIONS
from app.models.ai_usage import AiUsage
from app.models.company import CompanyParameter, ParameterDefinition
from app.services.ai import chat as ai_chat
from app.services.ai.entitlement import monthly_quota_usd, read_parameter
from app.services.ai.providers.base import LlmMessage, ProviderError
from app.services.ai.providers.fake import FakeProvider
from app.services.ai.registry import build_provider, get_provider
from app.services.ai.usage import ERROR, OK, SIN_CUOTA, estimate_cost_usd, month_totals, record
from tests.test_work_orders import login, setup

MENSAJE = LlmMessage(role="user", content="Hola")


def _habilitar(db, company_id: int, **params):
    """Pone los parametros de la empresa, igual que lo haria la pantalla de Parametros."""
    valores = {"ai.enabled": "true", "ai.monthly_quota_usd": "0", "ai.monthly_request_limit": "0"}
    valores.update({k: str(v) for k, v in params.items()})
    from app.core.parameter_catalog import AI_PARAMETERS

    for definicion in AI_PARAMETERS:
        nombre = definicion[0]
        if db.query(ParameterDefinition).filter_by(parameter=nombre).first() is None:
            # La migracion siembra estas filas; en los tests la base se arma desde los
            # modelos, asi que se crean aca desde el mismo catalogo.
            db.add(ParameterDefinition(
                parameter=definicion[0], default_value=definicion[1], description=definicion[2],
                data_type=definicion[3], category=definicion[4], editable=definicion[5], active=True,
            ))
    db.commit()
    for nombre, valor in valores.items():
        d = db.query(ParameterDefinition).filter_by(parameter=nombre).one()
        fila = db.query(CompanyParameter).filter_by(parameter_definition_id=d.id, company_id=company_id).first()
        if fila is None:
            db.add(CompanyParameter(parameter_definition_id=d.id, company_id=company_id, value=valor))
        else:
            fila.value = valor
    db.commit()


def _dar_permiso_ia(db, company_id: int):
    """Le da ai.use al admin de la empresa.

    En produccion no hace falta: create_company usa _grant_all_company_permissions y le
    da todos los permisos del catalogo. El fixture compartido de tests usa un subconjunto
    a proposito, asi que aca se completa solo para este modulo.
    """
    from app.core.permissions import PERMISSIONS
    from app.models.role import Permission, Role, role_permissions
    from app.models.user import CompanyUser

    admin = db.query(CompanyUser).filter_by(company_id=company_id, is_admin=True).one()
    rol = db.query(Role).filter_by(company_id=company_id, is_system=True).first()
    permiso = db.query(Permission).filter_by(code="ai.use").one()
    ya_esta = db.execute(role_permissions.select().where(
        role_permissions.c.role_id == rol.id, role_permissions.c.permission_id == permiso.id)).first()
    if ya_esta is None:
        db.execute(role_permissions.insert().values(role_id=rol.id, permission_id=permiso.id))
    db.commit()
    assert any(p.code == "ai.use" for p in PERMISSIONS)
    return admin


def _sin_permisos_ia(db, company_id: int):
    """Un admin de empresa normal no tiene el permiso si no se lo damos."""
    from app.models.role import CompanyUserRole, Role, role_permissions
    from app.models.user import CompanyUser

    admin = db.query(CompanyUser).filter_by(company_id=company_id, is_admin=True).one()
    for rc in db.query(CompanyUserRole).filter_by(company_user_id=admin.id, active=True).all():
        db.query(role_permissions).filter_by(role_id=rc.role_id).delete()
        db.delete(rc)
    db.commit()
    return admin


# --- entitlement -------------------------------------------------------------------

def test_ia_arranca_apagada_para_toda_empresa(client, db_session, monkeypatch):
    """Default apagado: que haya key en la plataforma no habilita el modulo solo."""
    company, _, _, _ = setup(db_session, "ai-off")
    h = login(client, "ot.ai-off@example.com", company.id)
    _dar_permiso_ia(db_session, company.id)
    r = client.get("/api/v1/ai/status", headers=h)
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["available"] is False
    assert r.json()["reason"] == ai_chat.NO_HABILITADO


def test_habilitar_por_empresa_no_toca_a_las_demas(client, db_session, monkeypatch):
    a, _, _, _ = setup(db_session, "ai-iso-a")
    b, _, _, _ = setup(db_session, "ai-iso-b")
    ha = login(client, "ot.ai-iso-a@example.com", a.id)
    hb = login(client, "ot.ai-iso-b@example.com", b.id)
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)
    _dar_permiso_ia(db_session, b.id)
    assert client.get("/api/v1/ai/status", headers=ha).json()["enabled"] is True
    assert client.get("/api/v1/ai/status", headers=hb).json()["enabled"] is False


def test_read_parameter_cae_al_default_del_catalogo(client, db_session):
    company, _, _, _ = setup(db_session, "ai-param")
    db_session.query(CompanyParameter).filter_by(company_id=company.id).delete()
    db_session.commit()
    assert read_parameter(db_session, company.id, "ai.enabled", "false") == "false"
    assert read_parameter(db_session, company.id, "no.existe.este.parametro", "x") == "x"


# --- el criterio central ------------------------------------------------------------

def test_el_sistema_sigue_andando_si_el_proveedor_esta_caido(client, db_session, monkeypatch):
    """Proveedor caido: la IA responde 'no disponible' y el resto de la app no se rompe."""
    company, _, customer, equipment = setup(db_session, "ai-caido")
    h = login(client, "ot.ai-caido@example.com", company.id)
    _habilitar(db_session, company.id)
    _dar_permiso_ia(db_session, company.id)
    caido = FakeProvider(fails=True)
    monkeypatch.setattr(ai_chat, "get_provider", lambda: caido)

    r = client.post("/api/v1/ai/chat", headers=h, json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["ok"] is False
    assert cuerpo["reason"] == ai_chat.PROVEEDOR_CAIDO
    assert "MiniMax no" not in str(cuerpo)  # el detalle no filtra credenciales

    # Lo importante: una OT se sigue haciendo normal.
    ot = client.post("/api/v1/work-orders", headers=h, json={
        "customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Falla"})
    assert ot.status_code == 201, ot.text
    assert client.get("/api/v1/work-orders", headers=h).json()["total"] == 1
    # Y el intento fallido quedo registrado: si solo se anotaran los exitos, el consumo
    # miente justo cuando el proveedor esta caido.
    usos = db_session.query(AiUsage).all()
    assert len(usos) == 1 and usos[0].status == ERROR


def test_sin_api_key_en_la_plataforma_no_se_rompe_nada(client, db_session, monkeypatch):
    company, _, customer, equipment = setup(db_session, "ai-sin-key")
    h = login(client, "ot.ai-sin-key@example.com", company.id)
    _habilitar(db_session, company.id)
    _dar_permiso_ia(db_session, company.id)
    monkeypatch.setattr(settings, "minimax_api_key", None)

    r = client.post("/api/v1/ai/chat", headers=h, json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 200
    assert r.json()["reason"] == ai_chat.PROVEEDOR_SIN_CONFIGURAR
    # Sin key no se hizo pedido a nadie, asi que no se registra uso.
    assert db_session.query(AiUsage).count() == 0
    ot = client.post("/api/v1/work-orders", headers=h, json={
        "customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "F"})
    assert ot.status_code == 201


def test_un_adapter_que_explota_tampoco_rompe(client, db_session, monkeypatch):
    class Loco:
        name = "loco"

        def is_configured(self): return True
        def model_id(self): return "loco-1"
        def complete(self, messages, max_tokens=1024): raise RuntimeError("boom")

    company, _, _, _ = setup(db_session, "ai-boom")
    h = login(client, "ot.ai-boom@example.com", company.id)
    _habilitar(db_session, company.id)
    _dar_permiso_ia(db_session, company.id)
    monkeypatch.setattr(ai_chat, "get_provider", lambda: Loco())

    r = client.post("/api/v1/ai/chat", headers=h, json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert db_session.query(AiUsage).one().status == ERROR


# --- camino feliz -------------------------------------------------------------------

def test_con_proveedor_responde_y_registra_el_uso(client, db_session, monkeypatch):
    company, _, _, _ = setup(db_session, "ai-ok")
    h = login(client, "ot.ai-ok@example.com", company.id)
    _habilitar(db_session, company.id)
    _dar_permiso_ia(db_session, company.id)
    bueno = FakeProvider(text="respuesta del asistente")
    monkeypatch.setattr(ai_chat, "get_provider", lambda: bueno)

    r = client.post("/api/v1/ai/chat", headers=h, json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["ok"] is True
    assert cuerpo["text"] == "respuesta del asistente"
    # El system prompt se antepone solo y se filtra cualquier rol no valido.
    enviados = bueno.calls[0]
    assert enviados[0].role == "system"
    assert enviados[1].content == "hola"

    fila = db_session.query(AiUsage).one()
    assert fila.status == OK
    assert fila.company_id == company.id
    assert fila.operation == "chat"
    assert fila.input_tokens > 0 and fila.output_tokens > 0
    assert float(fila.cost_usd) > 0


def test_cuota_excedida_corta_antes_de_gastar(client, db_session, monkeypatch):
    company, _, _, _ = setup(db_session, "ai-cuota")
    h = login(client, "ot.ai-cuota@example.com", company.id)
    _habilitar(db_session, company.id, **{"ai.monthly_quota_usd": "0.000001"})
    _dar_permiso_ia(db_session, company.id)
    bueno = FakeProvider()
    monkeypatch.setattr(ai_chat, "get_provider", lambda: bueno)
    client.post("/api/v1/ai/chat", headers=h, json={"messages": [{"role": "user", "content": "hola"}]})
    assert db_session.query(AiUsage).one().cost_usd > 0

    r = client.post("/api/v1/ai/chat", headers=h, json={"messages": [{"role": "user", "content": "otra"}]})
    assert r.status_code == 200
    assert r.json()["reason"] == ai_chat.CUOTA_EXCEDIDA
    # No se llamo al proveedor y el intento queda registrado.
    assert len(bueno.calls) == 1
    assert db_session.query(AiUsage).count() == 2
    assert db_session.query(AiUsage).order_by(AiUsage.id.desc()).first().status == SIN_CUOTA


def test_limite_de_pedidos_por_mes(client, db_session, monkeypatch):
    company, _, _, _ = setup(db_session, "ai-limite")
    h = login(client, "ot.ai-limite@example.com", company.id)
    _habilitar(db_session, company.id, **{"ai.monthly_request_limit": "1"})
    _dar_permiso_ia(db_session, company.id)
    bueno = FakeProvider()
    monkeypatch.setattr(ai_chat, "get_provider", lambda: bueno)
    assert client.post("/api/v1/ai/chat", headers=h, json={"messages": [{"role": "user", "content": "1"}]}).status_code == 200
    segundo = client.post("/api/v1/ai/chat", headers=h, json={"messages": [{"role": "user", "content": "2"}]})
    assert segundo.json()["reason"] == ai_chat.CUOTA_EXCEDIDA
    assert len(bueno.calls) == 1


def test_el_uso_es_por_empresa_y_no_se_mezcla(client, db_session, monkeypatch):
    a, _, _, _ = setup(db_session, "ai-uso-a")
    b, _, _, _ = setup(db_session, "ai-uso-b")
    ha = login(client, "ot.ai-uso-a@example.com", a.id)
    hb = login(client, "ot.ai-uso-b@example.com", b.id)
    _habilitar(db_session, a.id)
    _dar_permiso_ia(db_session, a.id)
    _habilitar(db_session, b.id)
    _dar_permiso_ia(db_session, b.id)
    monkeypatch.setattr(ai_chat, "get_provider", lambda: FakeProvider())
    client.post("/api/v1/ai/chat", headers=ha, json={"messages": [{"role": "user", "content": "a"}]})
    client.post("/api/v1/ai/chat", headers=hb, json={"messages": [{"role": "user", "content": "b"}]})
    assert db_session.query(AiUsage).filter_by(company_id=a.id).count() == 1
    assert db_session.query(AiUsage).filter_by(company_id=b.id).count() == 1
    assert month_totals(db_session, a.id)["requests"] == 1
    assert month_totals(db_session, b.id)["requests"] == 1
    status_a = client.get("/api/v1/ai/status", headers=ha).json()
    assert status_a["usage"]["requests"] == 1


# --- permisos y adaptadores ---------------------------------------------------------

def test_hacen_falta_permisos_para_usar_la_ia(client, db_session):
    company, _, _, _ = setup(db_session, "ai-perm")
    h = login(client, "ot.ai-perm@example.com", company.id)
    _habilitar(db_session, company.id)
    _dar_permiso_ia(db_session, company.id)
    _sin_permisos_ia(db_session, company.id)
    r = client.post("/api/v1/ai/chat", headers=h, json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 403, r.text
    assert client.get("/api/v1/ai/status", headers=h).status_code == 403


def test_las_definiciones_de_ia_no_divergan_del_catalogo():
    import re, pathlib

    from app.core.parameter_catalog import AI_PARAMETERS

    archivo = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261002_0018_ai_entitlement_y_uso.py"
    texto = archivo.read_text(encoding="utf-8")
    # La migracion tiene que leer el catalogo, no llevar su propia copia de los valores.
    assert "AI_PARAMETERS" in texto
    nombres = [p[0] for p in AI_PARAMETERS]
    assert nombres == ["ai.enabled", "ai.monthly_quota_usd", "ai.monthly_request_limit"]
    # Y lo que se siembra por default tiene que ser IA apagada.
    assert dict((p[0], p[1]) for p in AI_PARAMETERS)["ai.enabled"] == "false"


def test_la_ia_entra_al_catalogo_de_permisos():
    assert any(p.code == "ai.use" for p in PERMISSIONS)


def test_proveedor_desconocido_no_cae_en_silencio():
    from app.services.ai.providers.base import ProviderError

    with pytest.raises(ProviderError):
        build_provider("no-existe")


def test_registro_elige_minimax_por_defecto(monkeypatch):
    monkeypatch.setattr(settings, "minimax_api_key", "sk-test")
    p = get_provider()
    assert p.name == "minimax"
    assert p.is_configured() is True
    assert p.model_id() == settings.minimax_model


def test_el_costo_se_estima_por_millon_de_tokens():
    # 1.000.000 de entrada a 0.30 + 1.000.000 de salida a 1.20
    assert float(estimate_cost_usd(1_000_000, 1_000_000)) == 1.5
    assert float(estimate_cost_usd(0, 0)) == 0
