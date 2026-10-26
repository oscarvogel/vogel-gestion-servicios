"""Finalización técnica: lo que hace que una orden entregada entre al cierre a marcas.

El cierre a marcas filtra por ``completed_at``, **no** por ``delivered_at``. Una orden que
el taller entrega con costo cargado pero sin finalización técnica se queda fuera de todos
los cierres: la plata no se liquida y nadie ve el trabajo. Eso era exactamente lo que
pasaba con las órdenes en garantía.

Lo que se prueba acá:

1. Al entregar una orden **con costo cargado**, la finalización técnica se registra sola.
2. Al entregar una orden **sin costo**, no se registra: no hay nada que liquidar.
3. Una orden entregada **sin** finalización técnica no entra al cierre; con ella, entra.
4. La corrección manual funciona **también en estado final**, que es el caso real.
5. La fecha que se registra decide en qué período del cierre entra la orden.
6. No se registra dos veces, ni con fecha futura, ni sin permiso.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core.security import hash_password
from app.models.company import Company
from app.models.customer import Customer, Equipment, EquipmentCategory
from app.models.role import CompanyUserRole, Permission, Role, role_permissions
from app.models.user import CompanyUser, User
from app.models.work_area import WorkArea
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.work_order_quote import WorkOrderExecutionItem
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
    company = Company(name=f"Fin {suffix}", slug=f"fin-{suffix}")
    db.add(company)
    db.flush()
    user = User(
        email=f"fin.{suffix}@example.com",
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
    db.add_all(
        [
            WorkOrderStatus(
                company_id=company.id, name="Recibido", color="#10B981", sort_order=10,
                active=True, is_initial=True, is_final=False,
            ),
            WorkOrderStatus(
                company_id=company.id, name="Listo", color="#22C55E", sort_order=70,
                active=True, is_initial=False, is_final=False, marks_completed=True,
            ),
            WorkOrderStatus(
                company_id=company.id, name="Entregado", color="#64748B", sort_order=80,
                active=True, is_initial=False, is_final=True, marks_delivered=True,
            ),
        ]
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


def _cenario(db, company, suffix, costo=16000.0):
    """Cliente, equipo, area con empresa a liquidar y una orden con ese area.

    Devuelve (h, cliente, area, orden_id). La orden nace sin costo: el costo se carga
    a proposito, para poder probar tambien el caso "sin costo".
    """
    cliente = Customer(company_id=company.id, name=f"CLIENTE {suffix}", customer_type="PERSON")
    db.add(cliente)
    db.flush()
    marca = Customer(company_id=company.id, name="BRIKET S.A.", customer_type="COMPANY")
    db.add(marca)
    db.flush()
    categoria = EquipmentCategory(company_id=company.id, name="Heladera", active=True)
    db.add(categoria)
    db.flush()
    equipo = Equipment(
        company_id=company.id, customer_id=cliente.id, category_id=categoria.id,
        brand="HELADERA BRIKET", model="X", serial_number=f"SN-{suffix}", active=True,
    )
    db.add(equipo)
    db.flush()
    area = WorkArea(
        company_id=company.id,
        area_code="BRIKETGARANTIAS",
        area_name="BRIKET GARANTIAS",
        policy_code="",
        is_principal=True,
        warranty_type=1,
        liquidate_mode=0,
        utility=0,
        billing_customer_id=marca.id,
        active=True,
    )
    db.add(area)
    db.flush()
    orden = WorkOrder(
        company_id=company.id,
        number=1,
        customer_id=cliente.id,
        equipment_id=equipo.id,
        reported_fault="No enfria",
        received_by_user_id=db.query(User).filter_by(email=f"fin.{suffix}@example.com").one().id,
        status="RECEIVED",
        status_id=db.query(WorkOrderStatus).filter_by(company_id=company.id, name="Recibido").one().id,
        work_area_id=area.id,
        warranty_status="warranty",
        cost_total=costo,
    )
    db.add(orden)
    db.commit()
    return cliente, area, orden


def _id_estado(db, company, nombre):
    return db.query(WorkOrderStatus).filter_by(company_id=company.id, name=nombre).one().id


# ----------------------------------------------------------------------
# La regla: al entregar, con costo cargado, se registra la finalización técnica
# ----------------------------------------------------------------------
def test_al_entregar_con_costo_se_registra_la_finalizacion_tecnica(client, db_session):
    company, _ = setup(db_session, "entrega")
    h = login(client, "fin.entrega@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "entrega")

    entregado = _id_estado(db_session, company, "Entregado")
    cambio = client.post(
        f"/api/v1/work-orders/{orden.id}/status", headers=h, json={"status_id":entregado}
    )
    assert cambio.status_code == 200, cambio.text
    cuerpo = cambio.json()
    assert cuerpo["completed_at"] is not None
    assert cuerpo["delivered_at"] is not None

    # Y queda dicho en el historial, no de paso.
    eventos = client.get(f"/api/v1/work-orders/{orden.id}/events", headers=h).json()
    cambio_estado = [e for e in eventos if e["event_type"] == "STATUS_CHANGE"][-1]
    assert "finalización técnica" in cambio_estado["detail"].lower()
    assert "costo cargado" in cambio_estado["detail"].lower()


def test_al_entregar_sin_costo_no_se_registra_la_finalizacion_tecnica(client, db_session):
    """Sin costo no hay nada que liquidar: no se da por finalizado un trabajo sin cargar."""
    company, _ = setup(db_session, "sincosto")
    h = login(client, "fin.sincosto@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "sincosto", costo=0)

    entregado = _id_estado(db_session, company, "Entregado")
    cambio = client.post(
        f"/api/v1/work-orders/{orden.id}/status", headers=h, json={"status_id":entregado}
    )
    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["completed_at"] is None
    assert cambio.json()["delivered_at"] is not None


def test_la_orden_entregada_entra_al_cierre_a_marcas(client, db_session):
    """El cierre filtra por `completed_at`: sin ella, la orden no aparece."""
    company, _ = setup(db_session, "cierre")
    h = login(client, "fin.cierre@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "cierre", costo=16000)
    periodo = datetime.utcnow().strftime("%Y-%m")

    entregado = _id_estado(db_session, company, "Entregado")
    client.post(f"/api/v1/work-orders/{orden.id}/status", headers=h, json={"status_id":entregado})

    reporte = cierre.calcular_cierre(db_session, company.id, periodo)
    empresas = reporte["companies"]
    assert len(empresas) == 1, reporte
    assert empresas[0]["billing_customer_name"] == "BRIKET S.A."
    assert empresas[0]["works_count"] == 1
    assert empresas[0]["total_amount"] == 16000
    # Y entra en el casillero de garantia de terceros.
    assert empresas[0]["warranty_works_count"] == 1


# ----------------------------------------------------------------------
# La corrección manual
# ----------------------------------------------------------------------
def test_registrar_la_finalizacion_tecnica_a_mano_en_una_orden_entregada(client, db_session):
    """El caso real: la orden ya estaba entregada y sin finalizez, y hay que corregirla.

    Se arma el estado a mano, como quedo antes de que existiera la regla: entregada, con
    costo y **sin** finalización técnica.
    """
    company, _ = setup(db_session, "manual")
    h = login(client, "fin.manual@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "manual", costo=16000)

    entregado = _id_estado(db_session, company, "Entregado")
    orden.status_id = entregado
    orden.status = "ENTREGADO"
    orden.delivered_at = datetime(2026, 10, 26, 18, 32)
    db_session.commit()

    # Antes de corregirla, no entra en ningun cierre.
    assert cierre.calcular_cierre(db_session, company.id, "2026-10")["companies"] == []

    # La orden esta en estado final: cambiar el area o la fecha de entrega daria 409, pero
    # la finalizacion tecnica se puede registrar.
    cuerpo = client.post(
        f"/api/v1/work-orders/{orden.id}/technical-completion",
        headers=h,
        json={"completed_at": "2026-10-26T18:30:00"},
    )
    assert cuerpo.status_code == 200, cuerpo.text
    assert cuerpo.json()["completed_at"].startswith("2026-10-26T18:30")

    # Y ahora entra al cierre de octubre con lo que hay que liquidarle.
    reporte = cierre.calcular_cierre(db_session, company.id, "2026-10")
    empresas = reporte["companies"]
    assert len(empresas) == 1, reporte
    assert empresas[0]["billing_customer_name"] == "BRIKET S.A."
    assert empresas[0]["works_count"] == 1
    assert empresas[0]["total_amount"] == 16000

    # La correccion queda escrita en el historial de la orden.
    eventos = client.get(f"/api/v1/work-orders/{orden.id}/events", headers=h).json()
    correcciones = [e for e in eventos if e["event_type"] == "TECHNICAL_COMPLETION"]
    assert len(correcciones) == 1
    assert "Finalización técnica registrada" in correcciones[0]["detail"]


def test_la_fecha_registrada_decide_el_periodo_del_cierre(client, db_session):
    """La fecha es lo que decide en que mes entra la orden."""
    company, _ = setup(db_session, "periodo")
    h = login(client, "fin.periodo@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "periodo", costo=5000)

    entregado = _id_estado(db_session, company, "Entregado")
    orden.status_id = entregado
    orden.status = "ENTREGADO"
    orden.delivered_at = datetime(2026, 10, 26, 18, 32)
    db_session.commit()

    respuesta = client.post(
        f"/api/v1/work-orders/{orden.id}/technical-completion",
        headers=h,
        json={"completed_at": "2026-09-30T10:00:00"},
    )
    assert respuesta.status_code == 200, respuesta.text

    assert cierre.calcular_cierre(db_session, company.id, "2026-09")["companies"][0]["total_amount"] == 5000
    assert cierre.calcular_cierre(db_session, company.id, "2026-10")["companies"] == []


def test_no_se_registra_la_finalizacion_tecnica_dos_veces(client, db_session):
    company, _ = setup(db_session, "doble")
    h = login(client, "fin.doble@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "doble")

    primera = client.post(f"/api/v1/work-orders/{orden.id}/technical-completion", headers=h, json={})
    assert primera.status_code == 200, primera.text
    segunda = client.post(f"/api/v1/work-orders/{orden.id}/technical-completion", headers=h, json={})
    assert segunda.status_code == 409, segunda.text
    assert "ya tiene la finalización técnica" in segunda.text


def test_no_se_acepta_una_finalizacion_con_fecha_futura(client, db_session):
    company, _ = setup(db_session, "futuro")
    h = login(client, "fin.futuro@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "futuro")

    manana = (datetime.utcnow() + timedelta(days=1)).isoformat()
    respuesta = client.post(
        f"/api/v1/work-orders/{orden.id}/technical-completion",
        headers=h,
        json={"completed_at": manana},
    )
    assert respuesta.status_code == 422, respuesta.text
    fila = db_session.query(WorkOrder).filter_by(id=orden.id).one()
    assert fila.completed_at is None


def test_sin_permiso_no_se_registra_la_finalizacion_tecnica(client, db_session):
    company, _ = setup(
        db_session,
        "permiso",
        permisos=("customers.view", "equipment.view", "work_orders.view"),
    )
    h = login(client, "fin.permiso@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "permiso")

    respuesta = client.post(f"/api/v1/work-orders/{orden.id}/technical-completion", headers=h, json={})
    assert respuesta.status_code == 403, respuesta.text


def test_la_orden_de_otra_empresa_no_se_toca(client, db_session):
    a, _ = setup(db_session, "ajena-a")
    b, _ = setup(db_session, "ajena-b")
    hb = login(client, "fin.ajena-b@example.com", b.id)
    _, _, orden = _cenario(db_session, a, "ajena-a")

    respuesta = client.post(f"/api/v1/work-orders/{orden.id}/technical-completion", headers=hb, json={})
    assert respuesta.status_code == 404, respuesta.text


# ----------------------------------------------------------------------
# El costo de las OTs cargadas en la app (que no traen cost_total)
# ----------------------------------------------------------------------
def _trabajo_registrado(db, orden, costo=16000.0, cantidad=1):
    """Una linea de trabajo como las que se cargan en la app (no como las del legacy)."""
    db.add(
        WorkOrderExecutionItem(
            company_id=orden.company_id,
            work_order_id=orden.id,
            item_type="LABOR",
            description="Se arreglo la puerta",
            quantity=cantidad,
            unit_cost=costo,
            unit_price=18000,
            created_by_user_id=1,
        )
    )
    db.commit()


def test_una_orden_cargada_en_la_app_se_liquida_con_el_costo_de_su_trabajo(client, db_session):
    """Las OTs hechas en la app no traen `cost_total`: el costo esta en el trabajo registrado.

    Antes el cierre solo leia las lineas del legacy (``work_order_parts``), que las OTs de
    la app no tienen: entraban al cierre con cero.
    """
    company, _ = setup(db_session, "app")
    h = login(client, "fin.app@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "app", costo=0)
    _trabajo_registrado(db_session, orden, costo=16000)
    periodo = datetime.utcnow().strftime("%Y-%m")

    entregado = _id_estado(db_session, company, "Entregado")
    client.post(f"/api/v1/work-orders/{orden.id}/status", headers=h, json={"status_id":entregado})

    reporte = cierre.calcular_cierre(db_session, company.id, periodo)
    empresas = reporte["companies"]
    assert len(empresas) == 1, reporte
    assert empresas[0]["total_amount"] == 16000


def test_al_entregar_una_orden_cargada_en_la_app_se_registra_la_finalizacion_tecnica(client, db_session):
    """La regla mira el mismo costo que el cierre: el trabajo registrado en la app."""
    company, _ = setup(db_session, "appregla")
    h = login(client, "fin.appregla@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "appregla", costo=0)
    _trabajo_registrado(db_session, orden, costo=16000)

    entregado = _id_estado(db_session, company, "Entregado")
    cambio = client.post(
        f"/api/v1/work-orders/{orden.id}/status", headers=h, json={"status_id":entregado}
    )
    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["completed_at"] is not None


def test_una_orden_sin_trabajo_no_se_liquida(client, db_session):
    """Sin costo y sin trabajo registrado no hay nada que liquidar.

    La regla no anota la finalizacion tecnica de una orden sin costo, y sin finalizacion
    tecnica la orden no entra al cierre. Queda para liquidar a mano, si hiciera falta.
    """
    company, _ = setup(db_session, "vacia")
    h = login(client, "fin.vacia@example.com", company.id)
    _, _, orden = _cenario(db_session, company, "vacia", costo=0)
    periodo = datetime.utcnow().strftime("%Y-%m")

    entregado = _id_estado(db_session, company, "Entregado")
    cambio = client.post(
        f"/api/v1/work-orders/{orden.id}/status", headers=h, json={"status_id":entregado}
    )
    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["completed_at"] is None
    assert cierre.calcular_cierre(db_session, company.id, periodo)["companies"] == []
