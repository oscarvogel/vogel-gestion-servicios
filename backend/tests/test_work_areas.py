"""Maestro de áreas de trabajo: la garantía y la empresa a liquidar de cada orden.

Este archivo fija la regla que decide si una orden entra al cierre a marcas:

    el **área de trabajo** (marca + política) es la que trae la garantía y la empresa a
    liquidar. La orden no tiene esos campos: los hereda del área.

Y deja asentado el hueco que existía antes de esto: **una orden creada en la
aplicación no entraba nunca al cierre**, porque nacía sin área y el cierre hace JOIN
por ese campo. Las que entraban eran solo las importadas del legacy.

Lo que se prueba acá:

1. El maestro se puede dar de alta, y el código se deriva del nombre si no se escribe.
2. La orden guarda el área y hereda la garantía del área (no se escribe suelta).
3. **Sin área la orden no entra al cierre; con área entra**, con el importe y el
   desglose de garantía que correspondan.
4. Cambiar el área de una orden abierta recalcula la garantía y queda en el historial.
5. Cambiar la garantía del área sincroniza las órdenes que la usan.
"""
from __future__ import annotations

from datetime import datetime

from app.core.security import hash_password
from app.models.company import Company
from app.models.customer import Customer, Equipment, EquipmentCategory
from app.models.role import CompanyUserRole, Permission, Role, role_permissions
from app.models.user import CompanyUser, User
from app.models.work_area import WorkArea
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.services import warranty_settlements as cierre

PERMISOS = (
    "customers.view",
    "customers.manage",
    "equipment.view",
    "equipment.manage",
    "work_orders.view",
    "work_orders.manage",
    "work_areas.view",
    "work_areas.manage",
    "warranty_settlements.view",
)


def setup(db, suffix, permisos=PERMISOS):
    """Empresa con un usuario, un rol Administrador y los permisos dados."""
    company = Company(name=f"Area {suffix}", slug=f"area-{suffix}")
    db.add(company)
    db.flush()
    user = User(
        email=f"area.{suffix}@example.com",
        full_name="Recepción",
        password_hash=hash_password("Password1234"),
    )
    db.add(user)
    db.flush()
    membership = CompanyUser(
        company_id=company.id, user_id=user.id, role="ADMIN", is_admin=True, active=True
    )
    db.add(membership)
    db.flush()
    role = Role(company_id=company.id, name="Administrador", is_system=True, active=True)
    db.add(role)
    db.flush()
    for code in permisos:
        permiso = db.query(Permission).filter_by(code=code).one()
        db.execute(
            role_permissions.insert().values(role_id=role.id, permission_id=permiso.id)
        )
    db.add(CompanyUserRole(company_user_id=membership.id, role_id=role.id, active=True))
    db.add(
        WorkOrderStatus(
            company_id=company.id,
            name="Recibido",
            color="#10B981",
            sort_order=10,
            active=True,
            is_initial=True,
            is_final=False,
        )
    )
    db.commit()
    return company, user


def login(client, email, cid):
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Password1234"}
    ).json()["access_token"]
    r = client.post(
        "/api/v1/auth/select-company",
        headers={"Authorization": f"Bearer {token}"},
        json={"company_id": cid},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _cliente_equipo(db, company, nombre="PEREZ JUAN"):
    cliente = Customer(company_id=company.id, name=nombre, customer_type="PERSON")
    db.add(cliente)
    db.flush()
    categoria = EquipmentCategory(company_id=company.id, name="Lavarropas", active=True)
    db.add(categoria)
    db.flush()
    equipo = Equipment(
        company_id=company.id,
        customer_id=cliente.id,
        category_id=categoria.id,
        brand="LAVARROPAS",
        model="X",
        serial_number="SN-1",
        active=True,
    )
    db.add(equipo)
    db.commit()
    return cliente, equipo


def _crear_area(client, h, empresa_id, nombre="WHIRLPOOL GARANTIAS", politica="AGU", garantia=1):
    return client.post(
        "/api/v1/work-areas",
        headers=h,
        json={
            "area_name": nombre,
            "policy_code": politica,
            "billing_customer_id": empresa_id,
            "warranty_type": garantia,
        },
    )


def _crear_orden(client, h, cliente, equipo, work_area_id=None):
    payload = {
        "customer_id": cliente.id,
        "equipment_id": equipo.id,
        "reported_fault": "no enciende",
    }
    if work_area_id is not None:
        payload["work_area_id"] = work_area_id
    return client.post("/api/v1/work-orders", headers=h, json=payload)


# ----------------------------------------------------------------------
# El maestro
# ----------------------------------------------------------------------
def test_alta_de_area_deriva_el_codigo_y_trae_la_garantia(client, db_session):
    company, _ = setup(db_session, "alta")
    h = login(client, "area.alta@example.com", company.id)
    marca = Customer(company_id=company.id, name="DREAN S.A.", customer_type="COMPANY")
    db_session.add(marca)
    db_session.commit()

    alta = _crear_area(client, h, marca.id)
    assert alta.status_code == 201, alta.text
    cuerpo = alta.json()
    # El codigo se deriva del nombre: no hay que inventarlo.
    assert cuerpo["area_code"] == "WHIRLPOOLGARANTIAS"
    assert cuerpo["policy_code"] == "AGU"
    assert cuerpo["is_principal"] is False
    assert cuerpo["billing_customer_name"] == "DREAN S.A."
    assert cuerpo["warranty_type"] == 1
    assert cuerpo["warranty_label"] == "Garantía de terceros"

    # La politica vacia es la principal del area.
    principal = client.post(
        "/api/v1/work-areas",
        headers=h,
        json={"area_name": "WHIRLPOOL", "warranty_type": 0},
    )
    assert principal.status_code == 201, principal.text
    assert principal.json()["policy_code"] == ""
    assert principal.json()["is_principal"] is True


def test_no_se_repiten_codigo_y_politica(client, db_session):
    company, _ = setup(db_session, "dup")
    h = login(client, "area.dup@example.com", company.id)

    primera = _crear_area(client, h, None, nombre="DREAN GARANTIAS", politica="AGU")
    assert primera.status_code == 201, primera.text

    repetida = _crear_area(client, h, None, nombre="DREAN GARANTIAS", politica="AGU")
    assert repetida.status_code == 409, repetida.text

    # Otra politica de la misma marca si: son areas distintas.
    otra = _crear_area(client, h, None, nombre="DREAN GARANTIAS", politica="FUERA")
    assert otra.status_code == 201, otra.text


def test_el_area_de_otra_empresa_no_sirve(client, db_session):
    company, _ = setup(db_session, "ajena")
    h = login(client, "area.ajena@example.com", company.id)
    otra, _ = setup(db_session, "ajena2")

    area = WorkArea(
        company_id=otra.id,
        area_code="1",
        area_name="AJENA",
        policy_code="",
        is_principal=True,
        warranty_type=1,
        liquidate_mode=0,
        utility=0,
        active=True,
    )
    db_session.add(area)
    db_session.commit()

    cliente, equipo = _cliente_equipo(db_session, company)
    orden = _crear_orden(client, h, cliente, equipo, work_area_id=area.id)
    assert orden.status_code == 422, orden.text


# ----------------------------------------------------------------------
# La orden y el area
# ----------------------------------------------------------------------
def test_la_orden_hereda_la_garantia_del_area(client, db_session):
    company, _ = setup(db_session, "herencia")
    h = login(client, "area.herencia@example.com", company.id)
    marca = Customer(company_id=company.id, name="DREAN S.A.", customer_type="COMPANY")
    db_session.add(marca)
    db_session.commit()
    cliente, equipo = _cliente_equipo(db_session, company)

    area = _crear_area(client, h, marca.id).json()
    orden = _crear_orden(client, h, cliente, equipo, work_area_id=area["id"])
    assert orden.status_code == 201, orden.text
    cuerpo = orden.json()

    assert cuerpo["work_area_id"] == area["id"]
    assert cuerpo["work_area_name"] == "WHIRLPOOL GARANTIAS · AGU"
    assert cuerpo["warranty_type"] == 1
    assert cuerpo["warranty_label"] == "Garantía de terceros"
    assert cuerpo["billing_customer_name"] == "DREAN S.A."

    # La garantia de la orden es una copia de la del area.
    fila = db_session.query(WorkOrder).filter_by(id=cuerpo["id"]).one()
    assert fila.warranty_status == "warranty"


def test_sin_area_la_orden_no_entra_al_cierre_y_con_area_si(client, db_session):
    """La regla que hace que el cierre exista: el area trae la empresa a liquidar."""
    company, _ = setup(db_session, "cierre")
    h = login(client, "area.cierre@example.com", company.id)
    marca = Customer(company_id=company.id, name="DREAN S.A.", customer_type="COMPANY")
    db_session.add(marca)
    db_session.commit()
    cliente, equipo = _cliente_equipo(db_session, company)

    area = _crear_area(client, h, marca.id).json()

    sin_area = _crear_orden(client, h, cliente, equipo).json()
    con_area = _crear_orden(client, h, cliente, equipo, work_area_id=area["id"]).json()

    # Las dos se crean igual: lo que cambia es si entran al cierre.
    assert sin_area["work_area_id"] is None
    assert con_area["work_area_id"] == area["id"]

    # Las dos terminan en junio 2025, que es el periodo que se liquida.
    for ot_id, costo in ((sin_area["id"], 100), (con_area["id"], 250)):
        fila = db_session.query(WorkOrder).filter_by(id=ot_id).one()
        fila.completed_at = datetime(2025, 6, 18, 10, 0)
        fila.cost_total = costo
    db_session.commit()

    reporte = cierre.calcular_cierre(db_session, company.id, "2025-06")
    empresas = reporte["companies"]
    assert len(empresas) == 1, reporte
    assert empresas[0]["billing_customer_name"] == "DREAN S.A."
    # Solo entra la orden CON area: la otra no tiene a quien liquidarle.
    assert empresas[0]["works_count"] == 1
    assert empresas[0]["total_amount"] == 250
    # Y entra en el casillero de garantia de terceros.
    assert empresas[0]["warranty_works_count"] == 1
    assert empresas[0]["warranty_amount"] == 250
    assert empresas[0]["out_of_warranty_works_count"] == 0


def test_cambiar_el_area_recalcula_la_garantia_y_deja_historial(client, db_session):
    company, _ = setup(db_session, "cambio")
    h = login(client, "area.cambio@example.com", company.id)
    marca = Customer(company_id=company.id, name="DREAN S.A.", customer_type="COMPANY")
    db_session.add(marca)
    db_session.commit()
    cliente, equipo = _cliente_equipo(db_session, company)

    garantia = _crear_area(client, h, marca.id, nombre="WHIRLPOOL GARANTIAS", politica="AGU", garantia=1).json()
    fuera = _crear_area(client, h, marca.id, nombre="WHIRLPOOL FUERA", politica="FUERA", garantia=0).json()

    orden = _crear_orden(client, h, cliente, equipo, work_area_id=garantia["id"]).json()
    assert orden["warranty_type"] == 1

    cambio = client.patch(
        f"/api/v1/work-orders/{orden['id']}/work-area",
        headers=h,
        json={"work_area_id": fuera["id"]},
    )
    assert cambio.status_code == 200, cambio.text
    cuerpo = cambio.json()
    assert cuerpo["warranty_type"] == 0
    assert cuerpo["warranty_label"] == "Fuera de garantía"
    assert cuerpo["work_area_name"] == "WHIRLPOOL FUERA · FUERA"

    fila = db_session.query(WorkOrder).filter_by(id=orden["id"]).one()
    assert fila.warranty_status == "out_of_warranty"

    # El cambio queda escrito: corregir la garantia de una orden cargada es un
    # cambio de criterio y tiene que verse.
    eventos = client.get(f"/api/v1/work-orders/{orden['id']}/events", headers=h).json()
    areas = [e for e in eventos if e["event_type"] == "WORK_AREA_CHANGE"]
    assert len(areas) == 1
    assert "WHIRLPOOL GARANTIAS" in areas[0]["detail"]
    assert "WHIRLPOOL FUERA" in areas[0]["detail"]
    assert "DREAN S.A." in areas[0]["detail"]

    # Quitarle el area saca la orden del cierre, y queda dicho.
    quitar = client.patch(
        f"/api/v1/work-orders/{orden['id']}/work-area",
        headers=h,
        json={"work_area_id": None},
    )
    assert quitar.status_code == 200, quitar.text
    assert quitar.json()["work_area_id"] is None
    assert quitar.json()["warranty_type"] is None


def test_cambiar_la_garantia_del_area_sincroniza_las_ordenes(client, db_session):
    company, _ = setup(db_session, "sync")
    h = login(client, "area.sync@example.com", company.id)
    marca = Customer(company_id=company.id, name="DREAN S.A.", customer_type="COMPANY")
    db_session.add(marca)
    db_session.commit()
    cliente, equipo = _cliente_equipo(db_session, company)

    area = _crear_area(client, h, marca.id, garantia=1).json()
    orden = _crear_orden(client, h, cliente, equipo, work_area_id=area["id"]).json()
    assert orden["warranty_type"] == 1

    cambio = client.patch(
        f"/api/v1/work-areas/{area['id']}",
        headers=h,
        json={"warranty_type": 2},
    )
    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["warranty_label"] == "Garantía propia / de service"

    # La orden que usa ese area no puede quedar mostrando la garantia vieja.
    fila = db_session.query(WorkOrder).filter_by(id=orden["id"]).one()
    assert fila.warranty_status == "own_warranty"
    releida = client.get(f"/api/v1/work-orders/{orden['id']}", headers=h).json()
    assert releida["warranty_type"] == 2


# ----------------------------------------------------------------------
# Permisos
# ----------------------------------------------------------------------
def test_quien_arma_ordenes_puede_ver_el_maestro_pero_no_editarlo(client, db_session):
    company, _ = setup(
        db_session,
        "permiso",
        permisos=("customers.view", "equipment.view", "work_orders.view", "work_orders.manage"),
    )
    h = login(client, "area.permiso@example.com", company.id)

    listado = client.get("/api/v1/work-areas", headers=h)
    assert listado.status_code == 200, listado.text

    alta = client.post(
        "/api/v1/work-areas", headers=h, json={"area_name": "NO DEBERIA"}
    )
    assert alta.status_code == 403, alta.text


def test_el_maestro_de_otra_empresa_no_se_ve(client, db_session):
    company, _ = setup(db_session, "aisla")
    h = login(client, "area.aisla@example.com", company.id)
    otra, _ = setup(db_session, "aisla2")

    area = WorkArea(
        company_id=otra.id,
        area_code="1",
        area_name="DE OTRA",
        policy_code="",
        is_principal=True,
        warranty_type=1,
        liquidate_mode=0,
        utility=0,
        active=True,
    )
    db_session.add(area)
    db_session.commit()

    listado = client.get("/api/v1/work-areas", headers=h).json()
    assert [a["area_name"] for a in listado] == []
