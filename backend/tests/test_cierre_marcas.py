"""Cierre mensual a marcas: que ordenes estan en garantia y a que empresa hay que liquidarla.

Este archivo fija **la regla de inclusion**, que es lo mas caro que se puede equivocar en este
modulo. El legacy (CiberBrain) no tiene nada de esto: el cierre a marcas se hacia a mano y no
quedaba registrado, asi que no hay un contra que validar. Por eso la regla queda escrita en
tests, no solo en la documentacion.

**La regla:** entra al cierre toda OT cuya politica pertenezca a un area con empresa a liquidar
(``work_areas.billing_customer_id`` no nulo), y se le imputa a ese cliente.

Los tres errores que estos tests cerran:

1. **Confundir "Liquidar" con "a quien se liquida".** ``Areas.Liquidar`` es el ciclo de vida de
   la OT (0/3 = liquidacion manual, 1 = automatica, 2 = nunca), no la deuda. En las areas de
   marca vale 0, o sea "liquidacion manual": si el cierre filtrara por ahi, se excluiria justo
   la garantia, que es lo que hay que liquidar.

2. **Excluir el trabajo fuera de garantia.** La rama ``FUERA`` de cada marca tambien se le
   factura a la marca. En el corte 2020+ son 3.565 OTs y 47,8 M: mas de la mitad de la plata.
   Filtrar por "es garantia" deja fuera eso.

3. **Liquidar el precio de venta en vez del costo.** En garantia de terceros el legacy infla el
   precio (``@Unitario = @Costo * (1 + @PorcUtil/100)``), asi que la venta sale aproximadamente
   el doble. La decision es liquidar el COSTO.

Ademas: el cliente final de la OT no es a quien se liquida. La OT es de "PEREZ JUAN" y se liquida
a "DREAN S.A.", que es el ``CodCli`` del area.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models.company import Company
from app.models.customer import Customer, Equipment, EquipmentCategory
from app.models.user import CompanyUser, User
from app.models.work_area import WorkArea
from app.models.work_order import WorkOrder
from app.models.work_order_part import WorkOrderPart
from app.services import warranty_settlements as service

PERMISOS = {"warranty_settlements.view", "warranty_settlements.manage"}


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
def _empresa(db, sufijo: str, permisos=PERMISOS):
    """Empresa con un usuario y un rol Administrador con los permisos dados."""
    from app.models.role import CompanyUserRole, Permission, Role, role_permissions

    company = Company(name=f"Empresa {sufijo}", slug=f"empresa-{sufijo}")
    db.add(company)
    db.flush()
    user = User(
        email=f"user.{sufijo}@example.com",
        full_name="User",
        password_hash=hash_password("user-pwd"),
    )
    db.add(user)
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
            permiso = Permission(code=code, namespace="warranty_settlements", description=code)
            db.add(permiso)
            db.flush()
        db.execute(role_permissions.insert().values(role_id=role.id, permission_id=permiso.id))
    db.add(CompanyUserRole(company_user_id=membership.id, role_id=role.id, active=True))
    db.commit()
    return company, user


def _cliente(db, company, nombre: str, tipo="COMPANY") -> Customer:
    cliente = Customer(company_id=company.id, name=nombre, customer_type=tipo)
    db.add(cliente)
    db.commit()
    return cliente


def _equipo(db, company, cliente, serie="SN-1", marca="LAVARROPAS") -> Equipment:
    categoria = db.query(EquipmentCategory).filter_by(
        company_id=company.id, name="Lavarropas"
    ).first()
    if categoria is None:
        categoria = EquipmentCategory(company_id=company.id, name="Lavarropas", active=True)
        db.add(categoria)
        db.flush()
    equipo = Equipment(
        company_id=company.id,
        customer_id=cliente.id,
        category_id=categoria.id,
        brand=marca,
        model="X",
        serial_number=serie,
        active=True,
    )
    db.add(equipo)
    db.commit()
    return equipo


def _area(
    db,
    company,
    billing_customer=None,
    warranty_type=1,
    liquidate_mode=0,
    area_code="1",
    area_name="DREAN GARANTIAS",
    policy_code="",
):
    """Un area (marca) con su politica.

    ``billing_customer=None`` es el area generica: la que no se le liquida a nadie.
    """
    area = WorkArea(
        company_id=company.id,
        area_code=area_code,
        area_name=area_name,
        policy_code=policy_code,
        is_principal=policy_code == "",
        billing_customer_id=billing_customer.id if billing_customer else None,
        brand_name=area_name,
        warranty_type=warranty_type,
        liquidate_mode=liquidate_mode,
        utility=0,
        active=True,
    )
    db.add(area)
    db.commit()
    return area


def _ot(
    db,
    company,
    cliente,
    equipo,
    area,
    user,
    costo=100,
    venta=250,
    completada=datetime(2025, 6, 18, 10, 0),
    numero=1,
):
    ot = WorkOrder(
        company_id=company.id,
        number=numero,
        customer_id=cliente.id,
        equipment_id=equipo.id,
        reported_fault="no enciende",
        received_by_user_id=user.id,
        status="RECEIVED",
        work_area_id=area.id,
        cost_total=Decimal(str(costo)),
        sale_total=Decimal(str(venta)),
        completed_at=completada,
    )
    db.add(ot)
    db.commit()
    return ot


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


@pytest.fixture
def escenario(db_session):
    """Empresa con una marca (DREAN), un cliente final (PEREZ JUAN) y su equipo."""
    company, user = _empresa(db_session, "cierre")
    marca = _cliente(db_session, company, "DREAN S.A.")
    cliente = _cliente(db_session, company, "PEREZ JUAN", tipo="PERSON")
    equipo = _equipo(db_session, company, cliente)
    return {
        "db": db_session,
        "company": company,
        "user": user,
        "marca": marca,
        "cliente": cliente,
        "equipo": equipo,
    }


# ----------------------------------------------------------------------
# La regla de inclusion
# ----------------------------------------------------------------------
def test_el_trabajo_fuera_de_garantia_de_la_marca_tambien_se_liquida(escenario):
    """La rama FUERA de cada marca se le factura a la marca igual.

    Es el error mas caro del modulo: si el cierre filtrara por "es garantia", se perdia mas de
    la mitad del trabajo de marca (3.565 OTs y 47,8 M en el corte 2020+).
    """
    db = escenario["db"]
    area = _area(db, escenario["company"], billing_customer=escenario["marca"], warranty_type=0)
    _ot(db, escenario["company"], escenario["cliente"], escenario["equipo"], area, escenario["user"])

    reporte = service.calcular_cierre(db, escenario["company"].id, "2025-06")

    assert reporte["totals"]["works_count"] == 1, "el trabajo fuera de garantia de la marca se perdio"
    empresa = reporte["companies"][0]
    assert empresa["billing_customer_name"] == "DREAN S.A."
    # El flag no decide la inclusion: categoriza.
    assert empresa["warranty_works_count"] == 0
    assert empresa["out_of_warranty_works_count"] == 1
    assert empresa["out_of_warranty_amount"] == Decimal("100")


def test_la_garantia_propia_del_service_va_en_su_propio_casillero(escenario):
    """La garantia propia (Gt = 2) es garantia, pero no de terceros: no va con "fuera de garantia".

    Es el caso de Alladio (``CodCli = 7634``), que no es una marca de fabrica sino un service
    oficial / representante: sus politicas de "Garantia de Service" tienen ``Gt = 2``, o sea
    que la garantia la da el service. Si eso cayera en "fuera de garantia", el cierre
    mostraria como trabajo no cubierto lo que si cubre, y el service oficial quedaria con un
    numero que no es el real.
    """
    db = escenario["db"]
    alladio = _cliente(db, escenario["company"], "ALLADIO")
    area = _area(
        db, escenario["company"], billing_customer=alladio, warranty_type=2,
        area_code="60", area_name="ALLADIO SERVICE",
    )
    _ot(db, escenario["company"], escenario["cliente"], escenario["equipo"], area, escenario["user"])

    reporte = service.calcular_cierre(db, escenario["company"].id, "2025-06")
    empresa = reporte["companies"][0]

    assert reporte["totals"]["works_count"] == 1, "la garantia propia del service no entra al cierre"
    assert empresa["billing_customer_name"] == "ALLADIO"
    assert empresa["own_warranty_works_count"] == 1
    assert empresa["own_warranty_amount"] == Decimal("100")
    assert empresa["warranty_works_count"] == 0
    assert empresa["out_of_warranty_works_count"] == 0, "la garantia propia no es trabajo fuera de garantia"
    assert reporte["totals"]["own_warranty_works_count"] == 1


def test_los_tres_casilleros_no_se_pisan(escenario):
    """Garantia de terceros, garantia propia y fuera de garantia son tres cosas distintas.

    Es el error de desglose mas probable: si los tres caen en dos casilleros, el total
    sigue cuadrando (por eso el cuadre del importe no lo detecta) pero el reparto por
    naturaleza del trabajo queda mal, y es justo el numero que se usa para negociar.
    """
    db = escenario["db"]
    company = escenario["company"]
    marca = escenario["marca"]

    area_terceros = _area(db, company, billing_customer=marca, warranty_type=1, area_code="1")
    area_propia = _area(db, company, billing_customer=marca, warranty_type=2, area_code="60")
    area_fuera = _area(db, company, billing_customer=marca, warranty_type=0, area_code="2")
    _ot(db, company, escenario["cliente"], escenario["equipo"], area_terceros, escenario["user"], numero=1)
    _ot(db, company, escenario["cliente"], escenario["equipo"], area_propia, escenario["user"], numero=2)
    _ot(db, company, escenario["cliente"], escenario["equipo"], area_fuera, escenario["user"], numero=3)

    reporte = service.calcular_cierre(db, company.id, "2025-06")
    empresa = reporte["companies"][0]

    assert empresa["works_count"] == 3
    assert empresa["warranty_works_count"] == 1
    assert empresa["own_warranty_works_count"] == 1
    assert empresa["out_of_warranty_works_count"] == 1
    # El total no se pisa: los tres casilleros suman el total liquidado.
    assert (
        empresa["warranty_amount"]
        + empresa["own_warranty_amount"]
        + empresa["out_of_warranty_amount"]
        == empresa["total_amount"]
        == Decimal("300")
    )


def test_la_garantia_sin_empresa_a_liquidar_no_entra(escenario):
    """Garantia si, pero sin empresa a liquidar no: no hay a quien liquidarle."""
    db = escenario["db"]
    area = _area(db, escenario["company"], billing_customer=None, warranty_type=1)
    _ot(db, escenario["company"], escenario["cliente"], escenario["equipo"], area, escenario["user"])

    reporte = service.calcular_cierre(db, escenario["company"].id, "2025-06")

    assert reporte["totals"]["works_count"] == 0
    assert reporte["companies"] == []


def test_el_flag_liquidar_no_decide_la_inclusion(escenario):
    """`Liquidar` es el ciclo de vida de la OT, no "a quien se liquida".

    Las areas de marca del legacy tienen ``Liquidar = 0`` (liquidacion manual). Si el cierre
    usara ese flag como filtro, se excluiria justo la garantia. Y al reves: un area con
    ``Liquidar = 1`` (automatica) pero sin empresa a liquidar tampoco entra.
    """
    db = escenario["db"]
    company = escenario["company"]

    # Area de marca: Liquidar = 0 (manual), como todas en el legacy. ENTRA.
    area_marca = _area(
        db, company, billing_customer=escenario["marca"], warranty_type=1, liquidate_mode=0,
        area_code="1", area_name="DREAN GARANTIAS",
    )
    # Area generica: Liquidar = 1 (automatica), pero sin empresa. NO entra.
    area_generica = _area(
        db, company, billing_customer=None, warranty_type=1, liquidate_mode=1,
        area_code="99", area_name="GENERICA",
    )
    _ot(db, company, escenario["cliente"], escenario["equipo"], area_marca, escenario["user"], numero=1)
    _ot(db, company, escenario["cliente"], escenario["equipo"], area_generica, escenario["user"], numero=2)

    reporte = service.calcular_cierre(db, company.id, "2025-06")

    assert reporte["totals"]["works_count"] == 1, "el filtro Liquidar excluyo la garantia"
    assert reporte["companies"][0]["billing_customer_name"] == "DREAN S.A."


def test_el_cierre_se_imputa_a_la_empresa_del_area_y_no_al_cliente_final(escenario):
    """La OT es de PEREZ JUAN; la plata es de DREAN S.A."""
    db = escenario["db"]
    area = _area(db, escenario["company"], billing_customer=escenario["marca"], warranty_type=1)
    _ot(db, escenario["company"], escenario["cliente"], escenario["equipo"], area, escenario["user"])

    reporte = service.calcular_cierre(db, escenario["company"].id, "2025-06")
    empresa = reporte["companies"][0]

    assert empresa["billing_customer_name"] == "DREAN S.A."
    assert empresa["billing_customer_id"] == escenario["marca"].id
    # El cliente final sigue apareciendo en el detalle: es a quien se le hizo el trabajo.
    assert empresa["works"][0]["client_name"] == "PEREZ JUAN"


def test_el_importe_liquidado_es_el_costo_y_no_la_venta(escenario):
    """En garantia de terceros el legacy infla el precio: la venta sale el doble del costo."""
    db = escenario["db"]
    area = _area(db, escenario["company"], billing_customer=escenario["marca"], warranty_type=1)
    _ot(
        db, escenario["company"], escenario["cliente"], escenario["equipo"], area,
        escenario["user"], costo=100, venta=250,
    )

    reporte = service.calcular_cierre(db, escenario["company"].id, "2025-06")

    assert reporte["totals"]["total_amount"] == Decimal("100")
    assert reporte["companies"][0]["total_amount"] == Decimal("100")


def test_solo_entra_el_periodo_cerrado(escenario):
    db = escenario["db"]
    area = _area(db, escenario["company"], billing_customer=escenario["marca"], warranty_type=1)
    _ot(
        db, escenario["company"], escenario["cliente"], escenario["equipo"], area,
        escenario["user"], completada=datetime(2025, 6, 30, 23, 59), numero=1,
    )
    _ot(
        db, escenario["company"], escenario["cliente"], escenario["equipo"], area,
        escenario["user"], completada=datetime(2025, 7, 1, 0, 0), numero=2,
    )

    junio = service.calcular_cierre(db, escenario["company"].id, "2025-06")
    julio = service.calcular_cierre(db, escenario["company"].id, "2025-07")

    assert junio["totals"]["works_count"] == 1
    assert julio["totals"]["works_count"] == 1
    assert junio["totals"]["total_amount"] == Decimal("100")
    assert julio["totals"]["total_amount"] == Decimal("100")


def test_una_ot_sin_costo_toma_el_importe_de_sus_lineas(escenario):
    """Las OTs nacidas en el sistema nuevo no traen `cost_total`: sale de las lineas."""
    db = escenario["db"]
    area = _area(db, escenario["company"], billing_customer=escenario["marca"], warranty_type=1)
    ot = _ot(
        db, escenario["company"], escenario["cliente"], escenario["equipo"], area,
        escenario["user"], costo=0, numero=1,
    )
    db.add(
        WorkOrderPart(
            company_id=escenario["company"].id,
            work_order_id=ot.id,
            line_no=1,
            part_type=1,
            description="repuesto",
            quantity=Decimal("2"),
            unit_cost=Decimal("150"),
            unit_price=Decimal("300"),
        )
    )
    db.commit()

    reporte = service.calcular_cierre(db, escenario["company"].id, "2025-06")

    assert reporte["totals"]["total_amount"] == Decimal("300")


def test_una_ot_de_otra_empresa_no_aparece(escenario, db_session):
    db = escenario["db"]
    otra, otro_usuario = _empresa(db, "otra")
    otra_marca = _cliente(db, otra, "BGH S.A.")
    otro_cliente = _cliente(db, otra, "OTRO CLIENTE")
    otro_equipo = _equipo(db, otra, otro_cliente)
    area = _area(db, otra, billing_customer=otra_marca, warranty_type=1)
    _ot(db, otra, otro_cliente, otro_equipo, area, otro_usuario, numero=1)

    reporte = service.calcular_cierre(db, escenario["company"].id, "2025-06")

    assert reporte["totals"]["works_count"] == 0
    assert reporte["companies"] == []


# ----------------------------------------------------------------------
# Registrar el periodo
# ----------------------------------------------------------------------
def test_generar_registra_el_periodo_y_regenerar_no_duplica(escenario):
    db = escenario["db"]
    company = escenario["company"]
    area = _area(db, company, billing_customer=escenario["marca"], warranty_type=1)
    _ot(db, company, escenario["cliente"], escenario["equipo"], area, escenario["user"])

    service.generar_cierre(db, company.id, "2025-06")
    service.generar_cierre(db, company.id, "2025-06")

    from app.models.warranty_settlement import WarrantySettlement, WarrantySettlementOrder

    cierres = db.query(WarrantySettlement).filter_by(company_id=company.id).all()
    assert len(cierres) == 1, "regenerar duplico el cierre"
    detalle = db.query(WarrantySettlementOrder).filter_by(
        warranty_settlement_id=cierres[0].id
    ).all()
    assert len(detalle) == 1, "regenerar duplico el detalle del cierre"
    assert cierres[0].status == "draft"
    assert cierres[0].works_count == 1
    assert cierres[0].total_amount == Decimal("100")


def test_el_cierre_registrado_conserva_el_casillero_de_garantia_propia(escenario):
    """El cierre guardado tiene que traer los tres casilleros, no solo dos.

    El detalle por OT ya guardaba ``warranty_type = 2``; lo que faltaba era el resumen. Si
    el resumen no lo tiene, el cierre emitido muestra un reparto que no se corresponde con
    las OTs que lo componen, y el resumen es lo que se manda a la marca.
    """
    db = escenario["db"]
    company = escenario["company"]
    alladio = _cliente(db, company, "ALLADIO")
    area = _area(db, company, billing_customer=alladio, warranty_type=2, area_code="60")
    _ot(db, company, escenario["cliente"], escenario["equipo"], area, escenario["user"])

    service.generar_cierre(db, company.id, "2025-06")

    from app.models.warranty_settlement import WarrantySettlement, WarrantySettlementOrder

    cierre = db.query(WarrantySettlement).filter_by(company_id=company.id).one()
    assert cierre.own_warranty_works_count == 1
    assert cierre.own_warranty_amount == Decimal("100")
    assert cierre.out_of_warranty_works_count == 0

    detalle = db.query(WarrantySettlementOrder).filter_by(
        warranty_settlement_id=cierre.id
    ).one()
    assert detalle.warranty_type == 2


def test_el_cierre_emitido_no_se_regenera(escenario):
    """Emitir congela el periodo: si se pudiera regenerar, los numeros del mes cambiarian
    sin que nadie lo note."""
    db = escenario["db"]
    company = escenario["company"]
    area = _area(db, company, billing_customer=escenario["marca"], warranty_type=1)
    _ot(db, company, escenario["cliente"], escenario["equipo"], area, escenario["user"])

    service.generar_cierre(db, company.id, "2025-06")
    from app.models.warranty_settlement import WarrantySettlement

    cierre = db.query(WarrantySettlement).filter_by(company_id=company.id).one()
    service.cambiar_estado(db, company.id, cierre.id, "issued")

    with pytest.raises(service.CierreInvalido):
        service.generar_cierre(db, company.id, "2025-06")


def test_no_se_puede_saltar_de_borrador_a_liquidado(escenario):
    db = escenario["db"]
    company = escenario["company"]
    area = _area(db, company, billing_customer=escenario["marca"], warranty_type=1)
    _ot(db, company, escenario["cliente"], escenario["equipo"], area, escenario["user"])
    service.generar_cierre(db, company.id, "2025-06")

    from app.models.warranty_settlement import WarrantySettlement

    cierre = db.query(WarrantySettlement).filter_by(company_id=company.id).one()
    with pytest.raises(service.CierreInvalido):
        service.cambiar_estado(db, company.id, cierre.id, "settled")


def test_liquidar_guarda_el_numero_de_factura(escenario):
    db = escenario["db"]
    company = escenario["company"]
    area = _area(db, company, billing_customer=escenario["marca"], warranty_type=1)
    _ot(db, company, escenario["cliente"], escenario["equipo"], area, escenario["user"])
    service.generar_cierre(db, company.id, "2025-06")

    from app.models.warranty_settlement import WarrantySettlement

    cierre = db.query(WarrantySettlement).filter_by(company_id=company.id).one()
    service.cambiar_estado(db, company.id, cierre.id, "issued")
    liquidado = service.cambiar_estado(db, company.id, cierre.id, "settled", "0001-00001234")

    assert liquidado.status == "settled"
    assert liquidado.invoice_number == "0001-00001234"
    assert liquidado.settled_at is not None


# ----------------------------------------------------------------------
# El endpoint
# ----------------------------------------------------------------------
def test_el_endpoint_devuelve_el_reporte(escenario, client):
    db = escenario["db"]
    area = _area(db, escenario["company"], billing_customer=escenario["marca"], warranty_type=1)
    _ot(db, escenario["company"], escenario["cliente"], escenario["equipo"], area, escenario["user"])
    headers = _como_empresa(client, escenario["company"], escenario["user"])

    r = client.get("/api/v1/warranty-settlements?period=2025-06", headers=headers)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["period"] == "2025-06"
    assert cuerpo["totals"]["works_count"] == 1
    assert cuerpo["companies"][0]["billing_customer_name"] == "DREAN S.A."


def test_el_endpoint_rechaza_un_periodo_invalido(escenario, client):
    headers = _como_empresa(client, escenario["company"], escenario["user"])

    r = client.get("/api/v1/warranty-settlements?period=junio-2025", headers=headers)

    assert r.status_code == 422, r.text


def test_sin_el_permiso_no_se_ve_el_cierre(db_session, client):
    """Ver un cierre y emitirlo no es lo mismo: son permisos distintos."""
    company, user = _empresa(db_session, "sin-permiso", permisos=set())
    headers = _como_empresa(client, company, user)

    r = client.get("/api/v1/warranty-settlements?period=2025-06", headers=headers)

    assert r.status_code == 403, r.text


def test_generar_por_endpoint_deja_el_registro(escenario, client):
    db = escenario["db"]
    area = _area(db, escenario["company"], billing_customer=escenario["marca"], warranty_type=1)
    _ot(db, escenario["company"], escenario["cliente"], escenario["equipo"], area, escenario["user"])
    headers = _como_empresa(client, escenario["company"], escenario["user"])

    r = client.post("/api/v1/warranty-settlements/generate", headers=headers, json={"period": "2025-06"})
    assert r.status_code == 200, r.text

    listado = client.get("/api/v1/warranty-settlements/registros", headers=headers)
    assert listado.status_code == 200, listado.text
    cuerpo = listado.json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["status"] == "draft"
    assert cuerpo["items"][0]["billing_customer_name"] == "DREAN S.A."
    assert len(cuerpo["items"][0]["works"]) == 1


def test_emitir_y_liquidar_por_endpoint(escenario, client):
    db = escenario["db"]
    area = _area(db, escenario["company"], billing_customer=escenario["marca"], warranty_type=1)
    _ot(db, escenario["company"], escenario["cliente"], escenario["equipo"], area, escenario["user"])
    headers = _como_empresa(client, escenario["company"], escenario["user"])

    client.post("/api/v1/warranty-settlements/generate", headers=headers, json={"period": "2025-06"})
    listado = client.get("/api/v1/warranty-settlements/registros", headers=headers).json()
    id_cierre = listado["items"][0]["id"]

    emitido = client.post(f"/api/v1/warranty-settlements/{id_cierre}/issue", headers=headers)
    assert emitido.status_code == 200, emitido.text
    assert emitido.json()["status"] == "issued"

    liquidado = client.post(
        f"/api/v1/warranty-settlements/{id_cierre}/settle",
        headers=headers,
        json={"invoice_number": "0001-00009999"},
    )
    assert liquidado.status_code == 200, liquidado.text
    cuerpo = liquidado.json()
    assert cuerpo["status"] == "settled"
    assert cuerpo["invoice_number"] == "0001-00009999"


def test_emitir_un_cierre_inexistente_da_404(escenario, client):
    headers = _como_empresa(client, escenario["company"], escenario["user"])

    r = client.post("/api/v1/warranty-settlements/999999/issue", headers=headers)

    assert r.status_code == 404, r.text
