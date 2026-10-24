"""Tests del modulo de repuestos de Flexxus (#114).

Se prueban las tres cosas que importan:

1. **Aislamiento.** Una empresa sin `flexxus.enabled` no ve el catalogo, y no
   se abre ni un socket contra el ERP. Es lo que impide que otra empresa vea
   el catalogo de Electrotecniref.
2. **Degradacion.** Si el ERP no responde, la busqueda vuelve vacia con aviso:
   la carga de la OT tiene que seguir funcionando.
3. **Cliente defensivo.** Si en la base no esta la tabla o la columna, no
   revienta: devuelve vacio.
"""
import datetime as dt

import pytest

from app.core.security import hash_password
from app.integrations.flexxus.client import FlexxusClient, FlexxusUnavailable, _sin_acentos
from app.models.company import Company, CompanyParameter, ParameterDefinition
from app.models.role import CompanyUserRole, Permission, Role, role_permissions
from app.models.user import CompanyUser, User
from app.services import spare_parts

PARAMETROS = (
    ("flexxus.enabled", "false", "Habilita el catalogo", "bool", "integraciones", False),
    ("flexxus.database", r"C:\FLEXXUS\DB\ETR\DB-ETR.gdb", "Base", "string", "integraciones", False),
    ("flexxus.price_list", "1", "Lista", "integer", "integraciones", False),
)


def _parametros(db):
    for parameter, default, description, data_type, category, editable in PARAMETROS:
        if db.query(ParameterDefinition).filter_by(parameter=parameter).first() is None:
            db.add(
                ParameterDefinition(
                    parameter=parameter,
                    default_value=default,
                    description=description,
                    data_type=data_type,
                    category=category,
                    editable=editable,
                    active=True,
                )
            )
    db.commit()


def _empresa(client, db, suffix, *, habilitado: bool, permiso: bool = True):
    company = Company(name=f"Flexxus {suffix}", slug=f"flexxus-{suffix}")
    db.add(company)
    db.flush()
    user = User(
        email=f"flexxus.{suffix}@example.com",
        full_name="Tecnico Flexxus",
        password_hash=hash_password("Password1234"),
    )
    db.add(user)
    db.flush()
    membership = CompanyUser(
        company_id=company.id, user_id=user.id, is_admin=True, role="ADMIN", active=True
    )
    db.add(membership)
    db.flush()
    if permiso:
        role = Role(company_id=company.id, name="Administrador", is_system=True, active=True)
        db.add(role)
        db.flush()
        for code in ("work_orders.view", "work_orders.manage"):
            p = db.query(Permission).filter_by(code=code).one()
            db.execute(role_permissions.insert().values(role_id=role.id, permission_id=p.id))
        db.add(CompanyUserRole(company_user_id=membership.id, role_id=role.id, active=True))
    if habilitado:
        definition = db.query(ParameterDefinition).filter_by(parameter="flexxus.enabled").one()
        db.add(
            CompanyParameter(
                company_id=company.id, parameter_definition_id=definition.id, value="true"
            )
        )
    db.commit()
    token = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Password1234"}
    ).json()["access_token"]
    r = client.post(
        "/api/v1/auth/select-company",
        headers={"Authorization": f"Bearer {token}"},
        json={"company_id": company.id},
    )
    return company, {"Authorization": f"Bearer {r.json()['access_token']}"}


class ClienteFalso:
    """Sustituye al cliente real: registra las llamadas y devuelve lo que se le pida."""

    def __init__(self, items=None, error=None):
        self.items = items if items is not None else []
        self.error = error
        self.llamadas = []

    def buscar_articulos(self, texto, limite=20, precio_lista=1):
        self.llamadas.append({"texto": texto, "limite": limite, "precio_lista": precio_lista})
        if self.error:
            raise self.error
        return self.items

    def obtener_articulo(self, codigo, precio_lista=1):
        self.llamadas.append({"codigo": codigo, "precio_lista": precio_lista})
        if self.error:
            raise self.error
        return next((i for i in self.items if i["code"] == codigo), None)


def test_empresa_sin_habilitacion_no_ve_nada_y_no_abre_conexion(client, db_session, monkeypatch):
    """El caso de aislamiento: sin `flexxus.enabled` no se toca la red."""
    _parametros(db_session)

    def _no_deberia_existir(*args, **kwargs):
        raise AssertionError("Se armo un cliente de Flexxus para una empresa sin el modulo.")

    monkeypatch.setattr(spare_parts, "_cliente", _no_deberia_existir)

    company, headers = _empresa(client, db_session, "off", habilitado=False)
    r = client.get("/api/v1/spare-parts/search?q=adaptador", headers=headers)

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["disponible"] is False
    assert cuerpo["items"] == []
    # Que el modulo no aplique no es una falla: no hay aviso que mostrar.
    assert cuerpo["aviso"] is None


def test_empresa_habilitada_recibe_items_del_catalogo(client, db_session, monkeypatch):
    _parametros(db_session)
    item = {
        "code": "05589",
        "description": "ADAPTADOR TRIPLE PIRAMIDAL",
        "rubro_code": "00259",
        "rubro": "ADAPTADORES",
        "marca_code": "138",
        "marca": "STARBOX",
        "stock": 10.0,
        "stock_minimo": 2.0,
        "cost": 1440.0,
        "cost_currency": "ARS",
        "cost_source_currency": "PESOS",
        "sale_price": 2160.0,
        "sale_price_currency": "ARS",
        "price_source": "flexxus:PRECIOVENTA1",
        "price_synced_at": dt.datetime.now(dt.timezone.utc),
    }
    cliente = ClienteFalso(items=[item])
    monkeypatch.setattr(spare_parts, "_cliente", lambda db, company_id: cliente)

    company, headers = _empresa(client, db_session, "on", habilitado=True)
    r = client.get("/api/v1/spare-parts/search?q=adaptador&limit=5", headers=headers)

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["disponible"] is True
    assert cuerpo["aviso"] is None
    assert len(cuerpo["items"]) == 1
    assert cuerpo["items"][0]["code"] == "05589"
    assert cuerpo["items"][0]["sale_price"] == 2160.0
    # El limite y la lista de precios llegan al ERP.
    assert cliente.llamadas[0]["limite"] == 5
    assert cliente.llamadas[0]["precio_lista"] == 1


def test_erp_caido_degrada_sin_romper(client, db_session, monkeypatch):
    """Si el ERP no responde: vacio con aviso, nunca una excepcion."""
    _parametros(db_session)
    cliente = ClienteFalso(error=FlexxusUnavailable("El ERP no respondio"))
    monkeypatch.setattr(spare_parts, "_cliente", lambda db, company_id: cliente)

    company, headers = _empresa(client, db_session, "caido", habilitado=True)
    r = client.get("/api/v1/spare-parts/search?q=adaptador", headers=headers)

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["disponible"] is False
    assert cuerpo["items"] == []
    assert "Flexxus" in cuerpo["aviso"]


def test_aislamiento_entre_empresas(client, db_session, monkeypatch):
    """Una empresa con el modulo no habilita el de la otra."""
    _parametros(db_session)
    cliente = ClienteFalso(items=[{"code": "05589", "description": "ADAPTADOR"}])
    monkeypatch.setattr(spare_parts, "_cliente", lambda db, company_id: cliente)

    a, ha = _empresa(client, db_session, "a", habilitado=True)
    b, hb = _empresa(client, db_session, "b", habilitado=False)

    assert client.get("/api/v1/spare-parts/search?q=x", headers=ha).json()["disponible"] is True
    r_b = client.get("/api/v1/spare-parts/search?q=x", headers=hb)
    assert r_b.json()["disponible"] is False
    assert r_b.json()["items"] == []


def test_sin_permiso_no_puede_buscar(client, db_session):
    _parametros(db_session)
    company, headers = _empresa(client, db_session, "sinp", habilitado=True, permiso=False)
    r = client.get("/api/v1/spare-parts/search?q=x", headers=headers)
    assert r.status_code == 403


def test_query_vacia_o_limite_fuera_de_rango(client, db_session):
    _parametros(db_session)
    company, headers = _empresa(client, db_session, "valid", habilitado=True)
    assert client.get("/api/v1/spare-parts/search?q=", headers=headers).status_code == 422
    assert client.get("/api/v1/spare-parts/search?q=x&limit=0", headers=headers).status_code == 422
    assert client.get("/api/v1/spare-parts/search?q=x&limit=999", headers=headers).status_code == 422


def test_el_estado_no_abre_conexion_al_erp(client, db_session, monkeypatch):
    """El estado solo mira la habilitacion de la empresa: no toca la red."""
    _parametros(db_session)

    def _no_deberia_existir(*args, **kwargs):
        raise AssertionError("Se armo un cliente de Flexxus para consultar el estado.")

    monkeypatch.setattr(spare_parts, "_cliente", _no_deberia_existir)

    company, headers = _empresa(client, db_session, "estado", habilitado=False)
    r = client.get("/api/v1/spare-parts/status", headers=headers)
    assert r.status_code == 200
    assert r.json()["disponible"] is False
    # No es una falla: el modulo no aplica a esta empresa.
    assert r.json()["falla"] is False
    assert r.json()["motivo"]


def test_el_estado_avisa_cuando_falta_la_credencial(client, db_session, monkeypatch):
    """Si el modulo corresponde pero no hay credencial, eso si es una falla."""
    _parametros(db_session)
    monkeypatch.setattr(spare_parts.settings, "flexxus_password", None)

    company, headers = _empresa(client, db_session, "sincred", habilitado=True)
    r = client.get("/api/v1/spare-parts/status", headers=headers)
    assert r.status_code == 200
    assert r.json()["disponible"] is False
    assert r.json()["falla"] is True
    assert r.json()["motivo"]


def _crear_ot(client, db, headers, suffix, company_id):
    """Crea cliente, equipo y una OT lista para presupuestar."""
    from app.models.customer import Customer, Equipment, EquipmentCategory
    from app.models.work_order import WorkOrderStatus

    category = EquipmentCategory(company_id=company_id, name="Televisor")
    db.add(category)
    db.flush()
    customer = Customer(company_id=company_id, name=f"Cliente {suffix}")
    db.add(customer)
    db.flush()
    equipment = Equipment(
        company_id=company_id, customer_id=customer.id, category_id=category.id, brand="Samsung"
    )
    db.add(equipment)
    db.flush()
    for name, order in (("Recibido", 10), ("En diagnóstico", 20)):
        db.add(
            WorkOrderStatus(
                company_id=company_id,
                name=name,
                color="#10B981",
                sort_order=order,
                active=True,
                is_initial=name == "Recibido",
                is_final=False,
            )
        )
    db.commit()
    r = client.post(
        "/api/v1/work-orders",
        headers=headers,
        json={
            "customer_id": customer.id,
            "equipment_id": equipment.id,
            "reported_fault": "No enciende",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_el_presupuesto_guarda_el_codigo_y_el_origen_del_precio(client, db_session):
    """La linea guardada tiene que decir de donde salio el precio (#114)."""
    from app.models.work_order_quote import WorkOrderQuoteItem

    _parametros(db_session)
    company, headers = _empresa(client, db_session, "traza", habilitado=True)
    ot_id = _crear_ot(client, db_session, headers, "traza", company.id)
    client.put(
        f"/api/v1/work-orders/{ot_id}/diagnosis",
        headers=headers,
        json={"diagnosis": "Fuente dañada"},
    )

    r = client.post(
        f"/api/v1/work-orders/{ot_id}/quotes",
        headers=headers,
        json={
            "items": [
                {
                    "item_type": "PART",
                    "description": "ADAPTADOR TRIPLE PIRAMIDAL",
                    "quantity": 2,
                    "unit_cost": 1440,
                    "unit_price": 2160,
                    "item_code": "05589",
                    "price_source": "flexxus:PRECIOVENTA1",
                    "price_synced_at": "2026-10-24T12:00:00",
                }
            ]
        },
    )
    assert r.status_code == 201, r.text

    item = r.json()["items"][0]
    assert item["item_code"] == "05589"
    assert item["price_source"] == "flexxus:PRECIOVENTA1"
    assert item["price_synced_at"] is not None

    # Y quedo guardado, no solo devuelto.
    fila = (
        db_session.query(WorkOrderQuoteItem)
        .filter_by(company_id=company.id)
        .first()
    )
    assert fila.item_code == "05589"
    assert fila.price_source == "flexxus:PRECIOVENTA1"


def test_la_ejecucion_guarda_el_codigo_y_el_origen_del_precio(client, db_session):
    from app.models.work_order_quote import WorkOrderExecutionItem

    _parametros(db_session)
    company, headers = _empresa(client, db_session, "traza2", habilitado=True)
    ot_id = _crear_ot(client, db_session, headers, "traza2", company.id)

    r = client.post(
        f"/api/v1/work-orders/{ot_id}/execution",
        headers=headers,
        json={
            "item_type": "PART",
            "description": "ADAPTADOR TRIPLE PIRAMIDAL",
            "quantity": 1,
            "unit_cost": 1440,
            "unit_price": 2160,
            "item_code": "05589",
            "price_source": "flexxus:PRECIOVENTA1",
            "price_synced_at": "2026-10-24T12:00:00",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["item_code"] == "05589"

    fila = (
        db_session.query(WorkOrderExecutionItem)
        .filter_by(company_id=company.id)
        .first()
    )
    assert fila.item_code == "05589"
    assert fila.price_source == "flexxus:PRECIOVENTA1"


def test_una_linea_a_mano_no_inventa_origen_de_precio(client, db_session):
    """Una linea cargada a mano no tiene de donde salio el precio: queda vacio."""
    from app.models.work_order_quote import WorkOrderQuoteItem

    _parametros(db_session)
    company, headers = _empresa(client, db_session, "manual", habilitado=True)
    ot_id = _crear_ot(client, db_session, headers, "manual", company.id)
    client.put(
        f"/api/v1/work-orders/{ot_id}/diagnosis",
        headers=headers,
        json={"diagnosis": "Reparacion"},
    )

    r = client.post(
        f"/api/v1/work-orders/{ot_id}/quotes",
        headers=headers,
        json={
            "items": [
                {
                    "item_type": "LABOR",
                    "description": "Reparacion",
                    "quantity": 1,
                    "unit_cost": 8000,
                    "unit_price": 8000,
                }
            ]
        },
    )
    assert r.status_code == 201, r.text
    fila = db_session.query(WorkOrderQuoteItem).filter_by(company_id=company.id).first()
    assert fila.item_code is None
    assert fila.price_source is None


# --- Cliente: que no reviente con una base que no es la esperada ---------


class CursorFalso:
    """Cursor de Firebird simulado: responde por tipo de consulta."""

    def __init__(self, tablas: dict[str, set[str]], filas: list[dict] | None = None):
        self.tablas = tablas
        self.filas = filas or []
        self.description = None
        self._resultado: list = []

    def execute(self, sql, params=None):
        bajo = sql.lower()
        if "from rdb$relations" in bajo:
            tabla = (params or ("",))[0]
            self._resultado = [[1 if tabla in self.tablas else 0]]
            self.description = (("COUNT",),)
        elif "from rdb$relation_fields" in bajo:
            tabla = (params or ("",))[0]
            self._resultado = [[c] for c in sorted(self.tablas.get(tabla, set()))]
            self.description = (("CAMPO",),)
        elif "from \"monedas\"" in bajo:
            self._resultado = [["PESOS", 1.0], ["DOLARES", 1600.0]]
            self.description = (("CODIGOMONEDA", "CAMBIO"),)
        else:
            self._resultado = [tuple(fila.get(c) for c in self._nombres()) for fila in self.filas]
            self.description = tuple((c,) for c in self._nombres())

    @staticmethod
    def _nombres():
        return [
            "CODIGOARTICULO", "DESCRIPCION", "CODIGORUBRO", "CODIGOMARCA", "CODIGOMONEDA",
            "PRECIOCOMPRA", "PRECIOVENTA1", "PRECIOVENTA2", "PRECIOVENTA3",
            "PRECIOVENTA4", "PRECIOVENTA5", "ACTIVO", "BLOQUEADO", "STOCKACTUAL",
            "STOCKMINIMO", "RUBRO_DESCRIPCION", "MARCA_DESCRIPCION",
        ]

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self):
        return self._resultado


class ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def _cliente_con(tablas, filas=None):
    cliente = FlexxusClient(
        host="suevos.ddns.net",
        port=3050,
        user="ELECTROTR",
        password="secreto",
        charset="ISO8859_1",
        database=r"C:\FLEXXUS\DB\ETR\DB-ETR.gdb",
    )
    cursor = CursorFalso(tablas, filas)
    cliente._conectar = lambda: ConexionFalsa(cursor)
    return cliente


def test_base_sin_tabla_articulos_no_revienta():
    """Si la base no tiene ARTICULOS, se levanta FlexxusUnavailable, no un error raro."""
    cliente = _cliente_con({"MONEDAS": {"CODIGOMONEDA", "CAMBIO"}})
    with pytest.raises(FlexxusUnavailable):
        cliente.buscar_articulos("adaptador")


def test_base_sin_columnas_de_precio_devuelve_item_sin_precio():
    """Una base sin PRECIOVENTA1 no inventa el precio: lo deja en None."""
    tablas = {"ARTICULOS": {"CODIGOARTICULO", "DESCRIPCION"}}
    filas = [{"CODIGOARTICULO": "05589", "DESCRIPCION": "ADAPTADOR"}]
    cliente = _cliente_con(tablas, filas)
    resultado = cliente.buscar_articulos("adaptador")
    assert len(resultado) == 1
    assert resultado[0]["code"] == "05589"
    assert resultado[0]["sale_price"] is None
    assert resultado[0]["price_source"] is None


def test_precio_se_convierte_a_pesos_con_el_cambio_del_erp():
    """Un articulo en DOLARES se convierte con MONEDAS.CAMBIO."""
    tablas = {
        "ARTICULOS": {
            "CODIGOARTICULO", "DESCRIPCION", "CODIGOMONEDA", "PRECIOCOMPRA",
            "PRECIOVENTA1", "ACTIVO", "BLOQUEADO",
        },
        "MONEDAS": {"CODIGOMONEDA", "CAMBIO"},
    }
    filas = [
        {
            "CODIGOARTICULO": "000001",
            "DESCRIPCION": "ARANDELA",
            "CODIGOMONEDA": "DOLARES",
            "PRECIOCOMPRA": 10.0,
            "PRECIOVENTA1": 15.0,
            "ACTIVO": 1,
            "BLOQUEADO": 0,
        }
    ]
    cliente = _cliente_con(tablas, filas)
    item = cliente.buscar_articulos("arandela")[0]
    assert item["cost"] == pytest.approx(16000.0)
    assert item["sale_price"] == pytest.approx(24000.0)
    assert item["cost_source_currency"] == "DOLARES"
    assert item["price_source"] == "flexxus:PRECIOVENTA1"


def test_busqueda_ignora_acentos():
    assert _sin_acentos("CAÑERAS") == "CANERAS"
    assert _sin_acentos("ñ") == "n"


def test_variantes_generan_la_version_con_y_sin_tilde():
    """Firebird no convierte 'ñ' a 'Ñ': hay que probar las dos escrituras."""
    from app.integrations.flexxus.client import _variantes

    assert "CAÑO" in _variantes("cano")
    assert "CANO" in _variantes("cano")
    assert "CAÑO" in _variantes("caño")


def test_consulta_larga_se_trocea_en_terminos():
    """La consulta se parte por palabras: todas tienen que aparecer."""
    from app.integrations.flexxus.client import _terminos

    assert _terminos("adaptador") == ["ADAPTADOR"]
    assert _terminos("arandela plana zinc") == ["ARANDELA", "PLANA", "ZINC"]
    assert _terminos("caño") == ["CANO"]
    # Una palabra larga de mas: se corta al limite del termino.
    partes = _terminos("a" * 60)
    assert partes == ["A" * 30]
    # Muchas palabras: se toman las primeras cuatro.
    assert len(_terminos("uno dos tres cuatro cinco seis")) == 4


def test_descripcion_con_saltos_de_linea_se_limpia():
    """El ERP tiene descripciones con saltos de linea: se compactan."""
    from app.integrations.flexxus.client import FlexxusClient as C

    assert C._texto("ARANDELA AISLANTE\n\n70010") == "ARANDELA AISLANTE 70010"
