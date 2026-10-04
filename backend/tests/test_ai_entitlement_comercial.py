"""El adicional de IA no se lo enciende ni se lo agranda el cliente (#44, decision de producto).

La IA se vende por empresa. Mientras `ai.enabled` y su techo de uso (`ai.monthly_quota_usd`,
`ai.monthly_request_limit`) vivieron en la pantalla de Parametros con los permisos de
configuracion del cliente, un administrador de empresa podia prenderse solo el adicional y
ponerse la cuota en 0, que significa sin cuota.

Los tests de este archivo tienen que demostrar dos cosas distintas, porque son dos defensas:

1. **El cliente no puede**: el PATCH de Parametros le devuelve 403 aunque arme la peticion a
   mano, no solo le aparece el switch apagado.
2. **La plataforma si puede**: el superadmin lo cambia por su endpoint. Sin ese endpoint, el
   punto 1 dejaria la IA apagada para siempre.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.parameter_catalog import AI_PARAMETERS
from app.core.security import hash_password
from app.models.ai_usage import AiUsage
from app.models.company import Company, CompanyParameter, ParameterDefinition
from app.models.user import CompanyUser, User
from app.services.ai import entitlement

PARAMETROS = [p[0] for p in AI_PARAMETERS]


def _sembrar_parametros(db) -> None:
    """Las filas que siembra la migracion 0018, tal cual las pone el catalogo.

    Se siembran con el `editable` **del catalogo**, no con un `true` fijo, para que este test
    mida la decision y no un dibujo.
    """
    for nombre, default, descripcion, tipo, categoria, editable in AI_PARAMETERS:
        if db.query(ParameterDefinition).filter_by(parameter=nombre).first() is None:
            db.add(
                ParameterDefinition(
                    parameter=nombre, default_value=default, description=descripcion,
                    data_type=tipo, category=categoria, editable=editable, active=True,
                )
            )
    db.commit()


def _empresa(db, sufijo: str):
    """Empresa, su administrador de empresa y el superadmin de la plataforma."""
    company = Company(name=f"Empresa {sufijo}", slug=f"empresa-{sufijo}")
    db.add(company)
    db.flush()
    admin = User(
        email=f"admin.{sufijo}@example.com", full_name="Admin",
        password_hash=hash_password("admin-pwd"),
    )
    root = User(
        email=f"root.{sufijo}@example.com", full_name="Root",
        password_hash=hash_password("root-pwd"), is_superadmin=True,
    )
    db.add_all([admin, root])
    db.flush()
    db.add(
        CompanyUser(company_id=company.id, user_id=admin.id, role="ADMIN", is_admin=True, active=True)
    )
    _sembrar_parametros(db)
    db.commit()
    return company, admin, root


def _como_empresa(client, db, company, admin):
    token = client.post(
        "/api/v1/auth/login", json={"email": admin.email, "password": "admin-pwd"}
    ).json()["access_token"]
    r = client.post(
        "/api/v1/auth/select-company",
        headers={"Authorization": f"Bearer {token}"},
        json={"company_id": company.id},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _como_plataforma(client, root):
    token = client.post(
        "/api/v1/auth/login", json={"email": root.email, "password": "root-pwd"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- la defensa 1: el cliente no puede tocar la configuracion comercial ------------------


def test_el_administrador_de_empresa_no_puede_encender_la_ia(client, db_session):
    """El agujero principal: prenderse solo el adicional."""
    company, admin, _ = _empresa(db_session, "encender")
    cabeceras = _como_empresa(client, db_session, company, admin)

    respuesta = client.patch(
        "/api/v1/company-parameters/ai.enabled",
        headers=cabeceras, json={"value": True},
    )

    assert respuesta.status_code == 403, respuesta.text
    assert "no es editable" in respuesta.text
    assert entitlement.is_enabled(db_session, company.id) is False


def test_el_administrador_tampoco_puede_ponerse_cuota_infinita(client, db_session):
    """El segundo agujero, y mas silencioso: agrandarse el propio techo.

    Con la cuota en 0 —que el sistema lee como "sin cuota"— un cliente se garantizaba IA
    ilimitada sin contrato, con el interruptor ya apagado.
    """
    company, admin, root = _empresa(db_session, "cuota")
    cabeceras = _como_empresa(client, db_session, company, admin)
    # Se la deja encendida primero, desde la plataforma, para aislar el segundo cambio.
    _activar_desde_plataforma(client, db_session, root, company, enabled=True, cuota=25)

    for valor in (0, 9999):
        respuesta = client.patch(
            "/api/v1/company-parameters/ai.monthly_quota_usd",
            headers=cabeceras, json={"value": valor},
        )
        assert respuesta.status_code == 403, respuesta.text

    assert entitlement.monthly_quota_usd(db_session, company.id) == 25.0


def test_los_tres_parametros_de_ia_no_son_editables(client, db_session):
    """La regla general, para que mañana un cuarto parametro comercial no se cuelgue."""
    company, admin, _ = _empresa(db_session, "los-tres")
    cabeceras = _como_empresa(client, db_session, company, admin)

    for nombre in PARAMETROS:
        respuesta = client.patch(
            f"/api/v1/company-parameters/{nombre}",
            headers=cabeceras, json={"value": "999" if "enabled" not in nombre else True},
        )
        assert respuesta.status_code == 403, f"{nombre} dejo ser editable: {respuesta.text}"


def test_los_parametros_de_ia_siguen_siendo_visibles_para_la_empresa(client, db_session):
    """Deberian verse apagados, no desaparecer.

    Que un cliente vea "IA: no incluida en tu plan" es informacion honesta y abre la
    conversacion comercial. Esconderlo seria dejar un modulo que no aparece sin explicacion.
    """
    company, admin, _ = _empresa(db_session, "visibles")
    cabeceras = _como_empresa(client, db_session, company, admin)

    respuesta = client.get("/api/v1/company-parameters", headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    por_nombre = {p["parameter"]: p for p in respuesta.json()}
    for nombre in PARAMETROS:
        assert nombre in por_nombre, f"{nombre} no aparece en la pantalla de la empresa"
        assert por_nombre[nombre]["editable"] is False


# --- la defensa 2: la plataforma si puede -----------------------------------------------


def _activar_desde_plataforma(client, db, root, company, *, enabled, cuota=0, limite=0):
    r = client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=_como_plataforma(client, root),
        json={
            "enabled": enabled,
            "monthly_quota_usd": cuota,
            "monthly_request_limit": limite,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_el_superadmin_habilita_la_ia_para_una_empresa(client, db_session):
    """Sin esto, cerrar los parametros al cliente deja la IA apagada para siempre."""
    company, _, root = _empresa(db_session, "plataforma")

    cuerpo = client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=_como_plataforma(client, root),
        json={"enabled": True, "monthly_quota_usd": 20, "monthly_request_limit": 500},
    )

    assert cuerpo.status_code == 200, cuerpo.text
    datos = cuerpo.json()
    assert datos["enabled"] is True
    assert datos["monthly_quota_usd"] == 20
    assert datos["monthly_request_limit"] == 500
    # Y el modulo lo ve de verdad, no solo la respuesta del endpoint.
    assert entitlement.is_enabled(db_session, company.id) is True
    assert entitlement.monthly_quota_usd(db_session, company.id) == 20.0
    assert entitlement.monthly_request_limit(db_session, company.id) == 500


def test_poner_la_cuota_en_cero_borra_el_override(client, db_session):
    """Sin cuota es el default del catalogo, no un override que dice 0.

    Si se guardara, la pantalla lo mostraria como "personalizado" para un valor que en
    realidad es el general, y el superadmin no podria distinguir "le leave sin cuota a
    proposito" de "nunca le dijimos nada".
    """
    company, _, root = _empresa(db_session, "borrar")
    cabeceras = _como_plataforma(client, root)
    client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=cabeceras,
        json={"enabled": True, "monthly_quota_usd": 20, "monthly_request_limit": 100},
    )
    assert db_session.query(CompanyParameter).filter_by(
        company_id=company.id,
        parameter_definition_id=db_session.query(ParameterDefinition)
        .filter_by(parameter="ai.monthly_quota_usd").one().id,
    ).count() == 1

    client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=cabeceras,
        json={"enabled": True, "monthly_quota_usd": 0, "monthly_request_limit": 0},
    )

    restantes = db_session.query(CompanyParameter).join(ParameterDefinition).filter(
        CompanyParameter.company_id == company.id,
        ParameterDefinition.parameter.in_(["ai.monthly_quota_usd", "ai.monthly_request_limit"]),
    ).count()
    assert restantes == 0, "los valores que vuelven al default no deberian quedar guardados"
    assert entitlement.monthly_quota_usd(db_session, company.id) == 0.0


def test_desactivar_deja_la_ia_apagada_pero_no_toca_las_OT(client, db_session):
    """Apagar el adicional no puede romper el sistema sin IA: es el estado por defecto de todo."""
    company, _, root = _empresa(db_session, "apagar")
    cabeceras = _como_plataforma(client, root)
    client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=cabeceras,
        json={"enabled": True, "monthly_quota_usd": 20, "monthly_request_limit": 0},
    )

    client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=cabeceras,
        json={"enabled": False, "monthly_quota_usd": 20, "monthly_request_limit": 0},
    )

    assert entitlement.is_enabled(db_session, company.id) is False
    assert entitlement.monthly_quota_usd(db_session, company.id) == 20.0, "la cuota se conserva"


def test_una_cuota_negativa_se_rechaza(client, db_session):
    company, _, root = _empresa(db_session, "negativa")
    cabeceras = _como_plataforma(client, root)

    for cuerpo in (
        {"enabled": True, "monthly_quota_usd": -5, "monthly_request_limit": 0},
        {"enabled": True, "monthly_quota_usd": 0, "monthly_request_limit": -1},
    ):
        respuesta = client.put(
            f"/api/v1/companies/{company.id}/ai", headers=cabeceras, json=cuerpo
        )
        assert respuesta.status_code == 422, respuesta.text


def test_una_empresa_inactiva_tambien_se_puede_configurar(client, db_session):
    """Es una decision comercial, no una operacion sobre el sistema: da igual que este off."""
    company, _, root = _empresa(db_session, "inactiva")
    company.active = False
    db_session.commit()

    respuesta = client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=_como_plataforma(client, root),
        json={"enabled": True, "monthly_quota_usd": 5, "monthly_request_limit": 0},
    )
    assert respuesta.status_code == 200, respuesta.text


def test_un_admin_de_empresa_no_puede_tocar_el_endpoint_de_plataforma(client, db_session):
    """El endpoint nuevo es la puerta de atrás del 403: también tiene que estar cerrada."""
    company, admin, _ = _empresa(db_session, "sin-acceso")
    cabeceras = _como_empresa(client, db_session, company, admin)

    lectura = client.get(f"/api/v1/companies/{company.id}/ai", headers=cabeceras)
    escritura = client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=cabeceras,
        json={"enabled": True, "monthly_quota_usd": 0, "monthly_request_limit": 0},
    )

    assert lectura.status_code == 403, lectura.text
    assert escritura.status_code == 403, escritura.text
    assert entitlement.is_enabled(db_session, company.id) is False


def test_un_admin_no_puede_configurar_la_ia_de_otra_empresa(client, db_session):
    company_a, _, _ = _empresa(db_session, "ajena-a")
    company_b, admin_b, _ = _empresa(db_session, "ajena-b")
    cabeceras = _como_empresa(client, db_session, company_b, admin_b)

    respuesta = client.get(f"/api/v1/companies/{company_a.id}/ai", headers=cabeceras)
    # No es 403 de superadmin: el admin no es superadmin, asi que el endpoint no lo alcanza.
    assert respuesta.status_code == 403, respuesta.text


# --- lo que la plataforma necesita ver para decidir a quien le vende el adicional ----------


def test_el_endpoint_devuelve_el_consumo_del_mes(client, db_session):
    """La pregunta de plataforma: cuanto llevo gastado esta empresa y cuando se frena.

    Es la mitad de la respuesta a "como me entero si le quiero cobrar": el otro lado es que
    los datos existen en `ai_usage` y hay que poder leerlos por empresa.
    """
    company, _, root = _empresa(db_session, "consumo")
    cabeceras = _como_plataforma(client, root)
    for _ in range(3):
        db_session.add(
            AiUsage(
                company_id=company.id, user_id=None, provider="minimax", model="MiniMax-M3",
                operation="chat", input_tokens=1000, output_tokens=500,
                cost_usd=Decimal("0.015000"), duration_ms=900, status="OK",
            )
        )
    db_session.commit()

    cuerpo = client.get(f"/api/v1/companies/{company.id}/ai", headers=cabeceras).json()

    assert cuerpo["usage_requests"] == 3
    assert cuerpo["usage_cost_usd"] == pytest.approx(0.045)
    assert cuerpo["usage_input_tokens"] == 3000
    assert cuerpo["usage_output_tokens"] == 1500
    assert cuerpo["over_quota"] is False


def test_avisa_cuando_la_cuota_se_ya_fracaso(client, db_session):
    """Que la pantalla lo diga, en vez de que el usuario lo descubra cuando la IA deja de
    responder y no sabe por que."""
    company, _, root = _empresa(db_session, "agotada")
    cabeceras = _como_plataforma(client, root)
    client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=cabeceras,
        json={"enabled": True, "monthly_quota_usd": 0.01, "monthly_request_limit": 0},
    )
    db_session.add(
        AiUsage(
            company_id=company.id, user_id=None, provider="minimax", model="MiniMax-M3",
            operation="chat", input_tokens=1000, output_tokens=500,
            cost_usd=Decimal("0.050000"), duration_ms=900, status="OK",
        )
    )
    db_session.commit()

    cuerpo = client.get(f"/api/v1/companies/{company.id}/ai", headers=cabeceras).json()

    assert cuerpo["quota_exhausted"] is True
    assert cuerpo["over_quota"] is True


def test_el_consumo_de_una_empresa_no_se_le_muestra_a_otra(client, db_session):
    company_a, _, _ = _empresa(db_session, "consumo-a")
    company_b, _, root_b = _empresa(db_session, "consumo-b")
    db_session.add(
        AiUsage(
            company_id=company_a.id, user_id=None, provider="minimax", model="MiniMax-M3",
            operation="chat", input_tokens=10, output_tokens=10,
            cost_usd=Decimal("0.500000"), duration_ms=10, status="OK",
        )
    )
    db_session.commit()

    cuerpo = client.get(
        f"/api/v1/companies/{company_b.id}/ai", headers=_como_plataforma(client, root_b)
    ).json()

    assert cuerpo["usage_cost_usd"] == 0.0
    assert cuerpo["usage_requests"] == 0


# --- el catalogo y la migracion no pueden divergir ----------------------------------------


def test_las_definiciones_de_ia_no_son_editables_en_el_catalogo():
    """El arreglo empieza aca. Si esto vuelve a True, el cliente puede encenderse solo."""
    for nombre, _default, _desc, _tipo, _categoria, editable in AI_PARAMETERS:
        assert editable is False, f"{nombre} quedo editable otra vez"


def test_la_migracion_0023_deja_no_editables_las_filas_existentes(monkeypatch, tmp_path):
    """La 0018 ya corrio en las bases reales: sin una migracion nueva, el arreglo no llega.

    Se levanta una base con la 0018 aplicada, se corre la 0023 y se verifica el flag.
    """
    import importlib.util
    import pathlib

    from alembic import command
    from sqlalchemy import create_engine, text

    from tests.test_migrations import _alembic_config

    database_path = tmp_path / "ia-editable.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    config = _alembic_config(database_path)

    command.upgrade(config, "20261002_0018")
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        antes = dict(
            connection.execute(
                text(
                    "select parameter, editable from parameter_definitions"
                    " where parameter in ('ai.enabled','ai.monthly_quota_usd','ai.monthly_request_limit')"
                )
            ).fetchall()
        )
    engine.dispose()
    # Con la 0018 de este repo, que siembra desde el catalogo, ya nacen no editables.
    assert set(antes) == set(PARAMETROS)

    command.upgrade(config, "20261004_0023")
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        despues = dict(
            connection.execute(
                text(
                    "select parameter, editable from parameter_definitions"
                    " where parameter in ('ai.enabled','ai.monthly_quota_usd','ai.monthly_request_limit')"
                )
            ).fetchall()
        )
        revision = connection.execute(text("select version_num from alembic_version")).scalar_one()
    engine.dispose()

    assert all(v in (0, False) for v in despues.values()), despues
    assert revision == "20261004_0023"
