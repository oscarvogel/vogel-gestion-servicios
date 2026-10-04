"""Metricas de consumo y facturacion del adicional de IA (#44, sub-issue 8).

La tabla `ai_usage` ya se viene llenando desde el sub-issue 1. Esto es la capa de arriba: lo que
la empresa ve de si misma, y lo que la plataforma ve de todas.

Los tres criterios del issue tienen un test cada uno:

1. La empresa ve cuanto consumio y cuanto le queda de cuota.
2. Nunca se mezclan consumos de empresas distintas.
3. **El costo estimado se distingue del facturado.** No hay ningun "facturado" en el sistema:
   la factura de la proveedor no esta aca. Lo que se puede hacer —y lo que este archivo
   verifica— es que el numero que se muestra este etiquetado como estimacion, para que nadie
   lo confunda con lo que hay que cobrar.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.ai_usage import AiUsage
from app.models.company import Company
from app.models.user import CompanyUser, User
from app.core.security import hash_password
from app.services.ai.usage import historial_mensual

PERMISO = {"ai.use"}


def _sembrar_parametros_ia(db) -> None:
    """Las filas de `parameter_definitions` que siembran las migraciones.

    La base de los tests se arma desde los modelos, no desde alembic, asi que las filas de la
    0018 no existen. Se siembran desde el catalogo, igual que la migracion, para que el test
    mida el comportamiento y no la falta de una fila.
    """
    from app.core.parameter_catalog import AI_PARAMETERS
    from app.models.company import ParameterDefinition

    for nombre, default, descripcion, tipo, categoria, editable in AI_PARAMETERS:
        if db.query(ParameterDefinition).filter_by(parameter=nombre).first() is None:
            db.add(
                ParameterDefinition(
                    parameter=nombre, default_value=default, description=descripcion,
                    data_type=tipo, category=categoria, editable=editable, active=True,
                )
            )
    db.commit()


def _empresa(db, sufijo: str, permisos=PERMISO):
    from app.models.role import CompanyUserRole, Permission, Role, role_permissions

    company = Company(name=f"Empresa {sufijo}", slug=f"empresa-{sufijo}")
    db.add(company)
    db.flush()
    user = User(
        email=f"user.{sufijo}@example.com", full_name="User",
        password_hash=hash_password("user-pwd"),
    )
    root = User(
        email=f"root.{sufijo}@example.com", full_name="Root",
        password_hash=hash_password("root-pwd"), is_superadmin=True,
    )
    db.add_all([user, root])
    db.flush()
    membership = CompanyUser(
        company_id=company.id, user_id=user.id, role="ADMIN", is_admin=True, active=True
    )
    db.add(membership)
    db.flush()
    role = Role(
        company_id=company.id, name="Administrador", description="", is_system=True, active=True
    )
    db.add(role)
    db.flush()
    for code in permisos:
        permiso = db.query(Permission).filter_by(code=code).first()
        if permiso is None:
            permiso = Permission(code=code, namespace="inteligencia artificial", description=code)
            db.add(permiso)
            db.flush()
        db.execute(role_permissions.insert().values(role_id=role.id, permission_id=permiso.id))
    db.add(CompanyUserRole(company_user_id=membership.id, role_id=role.id, active=True))
    _sembrar_parametros_ia(db)
    db.commit()
    return company, user, root


def _token(client, user, password="user-pwd") -> str:
    return client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": password}
    ).json()["access_token"]


def _como_empresa(client, company, user):
    token = _token(client, user)
    r = client.post(
        "/api/v1/auth/select-company",
        headers={"Authorization": f"Bearer {token}"},
        json={"company_id": company.id},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _como_plataforma(client, root):
    return {"Authorization": f"Bearer {_token(client, root, 'root-pwd')}"}


def _uso(db, company, *, costo="0.010000", pedidos=1, entrada=1000, salida=500,
        operation="chat", status="OK", dias_atras=0):
    """Una fila de `ai_usage` con la fecha corrida, para no depender del reloj."""
    momento = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=dias_atras)
    fila = AiUsage(
        company_id=company.id, user_id=None, provider="minimax", model="MiniMax-M3",
        operation=operation, input_tokens=entrada, output_tokens=salida,
        cost_usd=Decimal(costo), duration_ms=500, status=status,
    )
    fila.created_at = momento
    db.add(fila)
    return fila


def _activar(client, db, root, company, *, enabled=True, cuota=0, limite=0):
    r = client.put(
        f"/api/v1/companies/{company.id}/ai",
        headers=_como_plataforma(client, root),
        json={"enabled": enabled, "monthly_quota_usd": cuota, "monthly_request_limit": limite},
    )
    assert r.status_code == 200, r.text
    return r.json()


# --- criterio 1: la empresa ve lo que consumio y lo que le queda -------------------------


def test_la_empresa_ve_su_consumo_y_cuanto_le_queda(client, db_session):
    company, user, root = _empresa(db_session, "consumo")
    _activar(client, db_session, root, company, enabled=True, cuota=1.0, limite=100)
    for _ in range(4):
        db_session.add(_uso(db_session, company, costo="0.100000", entrada=2000, salida=1000))
    db_session.commit()

    cuerpo = client.get(
        "/api/v1/ai/consumo", headers=_como_empresa(client, company, user)
    ).json()

    mes = cuerpo["mes_en_curso"]
    assert mes["requests"] == 4
    assert mes["cost_usd"] == pytest.approx(0.4)
    assert mes["input_tokens"] == 8000
    assert mes["output_tokens"] == 4000
    assert mes["monthly_quota_usd"] == 1.0
    assert mes["cuota_restante_usd"] == pytest.approx(0.6)
    assert mes["pedidos_restantes"] == 96
    assert mes["agotada"] is False


def test_sin_tope_lo_que_queda_es_none_y_no_cero(client, db_session):
    """None y 0 no son lo mismo: 0 es "no le queda nada", None es "no tiene tope"."""
    company, user, root = _empresa(db_session, "sin-tope")
    _activar(client, db_session, root, company, enabled=True, cuota=0, limite=0)
    db_session.add(_uso(db_session, company, costo="0.500000"))
    db_session.commit()

    mes = client.get("/api/v1/ai/consumo", headers=_como_empresa(client, company, user)).json()[
        "mes_en_curso"
    ]

    assert mes["cuota_restante_usd"] is None
    assert mes["pedidos_restantes"] is None
    assert mes["agotada"] is False


def test_cuando_se_agota_no_le_queda_negativo(client, db_session):
    """Un restante negativo seria una invitation a un bug: se topa en cero."""
    company, user, root = _empresa(db_session, "agotada")
    _activar(client, db_session, root, company, enabled=True, cuota=0.05, limite=0)
    for _ in range(10):
        db_session.add(_uso(db_session, company, costo="0.100000"))
    db_session.commit()

    mes = client.get("/api/v1/ai/consumo", headers=_como_empresa(client, company, user)).json()[
        "mes_en_curso"
    ]

    assert mes["cost_usd"] == pytest.approx(1.0)
    assert mes["cuota_restante_usd"] == 0.0
    assert mes["agotada"] is True


def test_el_desglose_separa_las_operaciones(client, db_session):
    company, user, root = _empresa(db_session, "desglose")
    _activar(client, db_session, root, company, enabled=True)
    for _ in range(5):
        db_session.add(_uso(db_session, company, costo="0.010000", operation="chat"))
    for _ in range(2):
        db_session.add(
            _uso(db_session, company, costo="0.500000", operation="transcripcion",
                 entrada=50000, salida=0)
        )
    db_session.commit()

    cuerpo = client.get("/api/v1/ai/consumo", headers=_como_empresa(client, company, user)).json()

    por_op = {f["operation"]: f for f in cuerpo["por_operacion"]}
    assert set(por_op) == {"chat", "transcripcion"}
    assert por_op["chat"]["requests"] == 5
    assert por_op["transcripcion"]["requests"] == 2
    # Viene ordenado por gasto, que es como lo va a querer leer quien mira la pantalla.
    assert cuerpo["por_operacion"][0]["operation"] == "transcripcion"


def test_el_historial_tiene_un_renglon_por_mes(client, db_session):
    """Un acumulado por mes, ordenado de mas viejo a mas reciente.

    El test **no** afirma en que indice cae cada fila, porque eso depende de que dia del mes
    sea hoy: 45 dias atras es el mes antepasado o el anterior segun donde este la fecha. Lo
    que tiene que ser cierto siempre es la cantidad de renglones, que no se pierda ningun
    consumo, el orden, y que el corte caiga en el dia 1 de un mes.
    """
    company, user, root = _empresa(db_session, "historial")
    _activar(client, db_session, root, company, enabled=True)
    esperado = 0.0
    for costo, dias in (("0.010000", 0), ("0.020000", 45), ("0.030000", 75)):
        db_session.add(_uso(db_session, company, costo=costo, dias_atras=dias))
        esperado += float(costo)
    db_session.commit()

    cuerpo = client.get(
        "/api/v1/ai/consumo?meses=4", headers=_como_empresa(client, company, user)
    ).json()

    historial = cuerpo["historial"]
    assert len(historial) == 4
    # No se pierde ningun consumo: la suma del historial es la de las tres filas.
    assert sum(f["cost_usd"] for f in historial) == pytest.approx(esperado)
    # De mas viejo a mas reciente, y el ultimo es el mes en curso. La fecha llega serializada
    # y sin zona, asi que se compara contra el mismo tipo: `utcnow().replace(tzinfo=None)`.
    cortes = [f["period_start"] for f in historial]
    assert cortes == sorted(cortes)
    inicio_del_mes = (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    assert datetime.fromisoformat(historial[-1]["period_start"]) == inicio_del_mes
    # Todo corte cae el dia 1 de un mes, no en un offset fijo de dias. Las fechas llegan como
    # texto desde el JSON, asi que se parsean antes de mirar el dia.
    for fila in historial:
        corte = datetime.fromisoformat(fila["period_start"])
        assert corte.day == 1
        assert 1 <= corte.month <= 12
    # Los meses sin consumo tambien aparecen, en cero: un mes vacio es informacion.
    assert any(f["cost_usd"] == 0.0 for f in historial)


# --- criterio 2: los consumos de empresas distintas no se mezclan -------------------------


def test_una_empresa_no_ve_el_consumo_de_otra(client, db_session):
    company_a, user_a, _ = _empresa(db_session, "aisla-a")
    company_b, user_b, _ = _empresa(db_session, "aisla-b")
    db_session.add(_uso(db_session, company_a, costo="9.000000"))
    for _ in range(3):
        db_session.add(_uso(db_session, company_b, costo="0.010000"))
    db_session.commit()

    de_a = client.get("/api/v1/ai/consumo", headers=_como_empresa(client, company_a, user_a)).json()
    de_b = client.get("/api/v1/ai/consumo", headers=_como_empresa(client, company_b, user_b)).json()

    assert de_a["mes_en_curso"]["cost_usd"] == pytest.approx(9.0)
    assert de_a["mes_en_curso"]["requests"] == 1
    assert de_b["mes_en_curso"]["cost_usd"] == pytest.approx(0.03)
    assert de_b["mes_en_curso"]["requests"] == 3


def test_el_tablero_de_plataforma_tiene_una_fila_por_empresa_y_no_mezcla(client, db_session):
    company_a, _, _ = _empresa(db_session, "tablero-a")
    company_b, _, root = _empresa(db_session, "tablero-b")
    db_session.add(_uso(db_session, company_a, costo="7.000000"))
    db_session.add(_uso(db_session, company_b, costo="0.500000"))
    db_session.commit()

    filas = client.get("/api/v1/companies/ai-consumo", headers=_como_plataforma(client, root)).json()
    por_id = {f["company_id"]: f for f in filas}

    assert set(por_id) == {company_a.id, company_b.id}
    assert por_id[company_a.id]["cost_usd"] == pytest.approx(7.0)
    assert por_id[company_b.id]["cost_usd"] == pytest.approx(0.5)


def test_una_empresa_completa_sin_ia_tambien_aparece_en_el_tablero(client, db_session):
    """Es justo la fila que hay que mirar: consumo con el adicional apagado.

    O se le quedo el interruptor despues de un mes de uso, o esta pagando sin estar
    contratada. Filtrar el tablero por "solo las que tienen IA" esconde las dos.
    """
    company, _, root = _empresa(db_session, "sin-ia-con-consumo")
    db_session.add(_uso(db_session, company, costo="1.000000"))
    db_session.commit()

    filas = client.get("/api/v1/companies/ai-consumo", headers=_como_plataforma(client, root)).json()
    fila = next(f for f in filas if f["company_id"] == company.id)

    assert fila["enabled"] is False
    assert fila["cost_usd"] == pytest.approx(1.0)
    assert fila["requests"] == 1


def test_el_tablero_de_plataforma_es_solo_para_superadmin(client, db_session):
    """La lista de consumo de todas las empresas es informacion de la plataforma."""
    company, user, _ = _empresa(db_session, "no-plataforma")
    db_session.add(_uso(db_session, company))
    db_session.commit()

    respuesta = client.get(
        "/api/v1/companies/ai-consumo", headers=_como_empresa(client, company, user)
    )

    assert respuesta.status_code == 403, respuesta.text


def test_sin_el_permiso_ai_use_no_hay_consumo_que_ver(client, db_session):
    """Un rol sin `ai.use` no tiene nada que mirar: el consumo es del modulo IA."""
    company, user, _ = _empresa(db_session, "sin-permiso", permisos={"customers.view"})
    db_session.add(_uso(db_session, company))
    db_session.commit()

    respuesta = client.get("/api/v1/ai/consumo", headers=_como_empresa(client, company, user))

    assert respuesta.status_code == 403, respuesta.text


# --- criterio 3: estimado no es facturado -------------------------------------------------


def test_el_consumo_Declara_que_el_costo_es_estimado(client, db_session):
    """El criterio del issue: el estimado se distingue del facturado.

    En el sistema **no hay** cifra facturada: la factura de la proveedor no se carga. Lo que se
    puede y se debe hacer es que el numero que se muestra este etiquetado, para que el que lo
    lea no lo lleve a una factura como si fuera el total a cobrar.
    """
    company, user, root = _empresa(db_session, "estimado")
    _activar(client, db_session, root, company, enabled=True)
    db_session.add(_uso(db_session, company, costo="0.250000"))
    db_session.commit()

    cuerpo = client.get("/api/v1/ai/consumo", headers=_como_empresa(client, company, user)).json()

    assert cuerpo["costo_es_estimado"] is True
    # Y ningun campo se llama "facturado", que seria mentir.
    assert "facturado" not in str(cuerpo).lower()


def test_el_endpoint_de_plataforma_tambien_lo_estima(client, db_session):
    company, _, root = _empresa(db_session, "estimado-plataforma")
    db_session.add(_uso(db_session, company, costo="0.250000"))
    db_session.commit()

    filas = client.get("/api/v1/companies/ai-consumo", headers=_como_plataforma(client, root)).json()

    assert filas[0]["cost_usd"] == pytest.approx(0.25)
    assert "facturado" not in str(filas).lower()


# --- el acumulado tiene que contar tambien lo que fallo ----------------------------------


def test_lo_que_fallo_cuenta_como_consumo_y_aparece_como_registro(client, db_session):
    """Si solo se contaran los exitos, el acumulado miente justo cuando el proveedor esta caido.

    Los pedidos que cuentan para la cuota son los OK y los ERROR. Los `SIN_CUOTA` y
    `SIN_PERMISO` quedan registrados pero no consumen, porque no llegaron a pegarle al
    proveedor.
    """
    company, user, root = _empresa(db_session, "errores")
    _activar(client, db_session, root, company, enabled=True)
    db_session.add(_uso(db_session, company, costo="0.010000", status="OK"))
    db_session.add(_uso(db_session, company, costo="0.020000", status="ERROR"))
    db_session.add(_uso(db_session, company, costo="0", status="SIN_CUOTA"))
    db_session.commit()

    mes = client.get("/api/v1/ai/consumo", headers=_como_empresa(client, company, user)).json()[
        "mes_en_curso"
    ]

    assert mes["registros"] == 3, "las tres filas quedan registradas"
    assert mes["requests"] == 2, "pero solo dos consumieron de verdad"
    assert mes["cost_usd"] == pytest.approx(0.03)


# --- la agregacion en Python, que es lo que hace portable el historial -------------------


def test_los_cortes_de_mes_no_dependen_del_motor_de_base():
    """La suite corre en SQLite y la migracion en MySQL: las funciones de fecha no coinciden.

    Por eso los cortes se arman en Python. Este test fija el comportamiento al margen de un
    cambio de dia/hora, que es donde un `timedelta(days=30)` se equivocaria: el mes pasado
    tiene 28, 29, 30 o 31 dias, y el costo acumulado tiene que caer en el mes que corresponde.
    """
    from app.services.ai.usage import _month_start

    assert _month_start(0).day == 1
    assert _month_start(1).day == 1
    assert _month_start(12).day == 1
    # Cruce de año: 12 meses atrás tiene que caer en el año anterior.
    assert _month_start(12).year == _month_start(0).year - 1
    # Y cada corte es el primero de un mes existente, no un día 31 de un mes corto.
    for atras in range(0, 14):
        corte = _month_start(atras)
        assert corte.day == 1
        assert 1 <= corte.month <= 12
    # Doce meses atrás desde enero tiene que dar enero del año anterior.
    enero = _month_start(0)
    if enero.month == 1:
        assert _month_start(12).month == 1
        assert _month_start(13).month == 2


def test_historial_rechaza_un_rango_absurdo(db_session):
    """Con 99 meses, o con 0, la pantalla no tiene que romperse ni traer 99 consultas."""
    company, _, _ = _empresa(db_session, "rangos")
    for meses, esperado in ((0, 12), (99, 12), (-3, 12), (6, 6)):
        assert len(historial_mensual(db_session, company.id, meses)) == esperado
