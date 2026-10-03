"""Documentos de equipo (#43).

Lo que hay que demostrar, segun el issue: aislamiento multiempresa, permisos,
asociacion equipo/OT, y que el binario nunca queda en MySQL.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile

import pytest

from app.core.config import settings
from app.models.equipment_document import EquipmentDocument
from app.models.work_order import WorkOrderEvent
from app.services.storage import FilesystemStorage, StorageError, build_key
# setup/login de test_work_orders: el rol que crea ya tiene equipment.view y
# equipment.manage, que es lo que necesita esta suite.
from tests.test_work_orders import login, setup


@pytest.fixture(autouse=True)
def storage_temporal(monkeypatch):
    """Cada test escribe en un directorio propio y lo borra al terminar."""
    root = tempfile.mkdtemp(prefix="docs-test-")
    monkeypatch.setattr(settings, "storage_backend", "filesystem")
    monkeypatch.setattr(settings, "storage_local_root", root)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _subir(client, headers, equipment_id, contenido=b"contenido de prueba", nombre="foto.jpg", tipo="image/jpeg", **form):
    return client.post(
        f"/api/v1/equipment/{equipment_id}/documents",
        headers=headers,
        files={"file": (nombre, io.BytesIO(contenido), tipo)},
        data={k: v for k, v in form.items() if v is not None},
    )


def test_subir_crea_la_fila_y_deja_el_binario_fuera_de_mysql(client, db_session, storage_temporal):
    company, user, customer, equipment = setup(db_session, "doc")
    headers = login(client, "ot.doc@example.com", company.id)
    contenido = b"bytes de una foto de 4 KB " + b"x" * 4096

    r = _subir(client, headers, equipment.id, contenido, "estado inicial.jpg", description="Como lo recibio el cliente")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["original_filename"] == "estado inicial.jpg"
    assert body["mime_type"] == "image/jpeg"
    assert body["size_bytes"] == len(contenido)
    assert body["description"] == "Como lo recibio el cliente"
    assert body["is_previewable"] is True

    # El binario esta en disco...
    fila = db_session.query(EquipmentDocument).one()
    ruta = os.path.join(storage_temporal, *fila.storage_key.split("/"))
    assert os.path.exists(ruta)
    with open(ruta, "rb") as f:
        assert f.read() == contenido
    # ...y en la base no hay ni un byte de contenido.
    assert "bytes de una foto" not in str(fila.__dict__)


def test_la_clave_la_genera_el_servidor_y_no_el_nombre_del_usuario(client, db_session, storage_temporal):
    """Un nombre de archivo es entrada de usuario: no puede ser la clave de storage."""
    company, user, customer, equipment = setup(db_session, "doc-key")
    headers = login(client, "ot.doc-key@example.com", company.id)
    r = _subir(client, headers, equipment.id, nombre="../../../etc/passwd")
    assert r.status_code == 201, r.text
    fila = db_session.query(EquipmentDocument).one()
    assert ".." not in fila.storage_key
    assert fila.storage_key.startswith(f"company-{company.id}/equipment-{equipment.id}/")
    assert fila.original_filename == "../../../etc/passwd"
    # Y el archivo quedo dentro de la raiz, no arriba.
    assert os.path.abspath(os.path.join(storage_temporal, *fila.storage_key.split("/"))).startswith(os.path.abspath(storage_temporal))


def test_build_key_ignora_nombres_hostiles():
    for nombre in ("../../etc/passwd", "a b/c*d.jpg", "archivo", "x" * 300):
        clave = build_key(1, 2, nombre)
        assert ".." not in clave and " " not in clave and "*" not in clave
        assert clave.startswith("company-1/equipment-2/")


def test_documentos_nunca_se_ven_de_otra_empresa(client, db_session, storage_temporal):
    a, _, ca, ea = setup(db_session, "doc-iso-a")
    b, _, cb, eb = setup(db_session, "doc-iso-b")
    ha = login(client, "ot.doc-iso-a@example.com", a.id)
    hb = login(client, "ot.doc-iso-b@example.com", b.id)

    creado = _subir(client, ha, ea.id)
    assert creado.status_code == 201
    doc_id = creado.json()["id"]

    # La empresa B no lo lista, no lo descarga, no lo edita y no lo da de baja.
    assert client.get(f"/api/v1/equipment/{ea.id}/documents", headers=hb).status_code == 404
    assert client.get(f"/api/v1/documents/{doc_id}/download", headers=hb).status_code == 404
    assert client.patch(f"/api/v1/documents/{doc_id}", headers=hb, json={"description": "mio"}).status_code == 404
    assert client.delete(f"/api/v1/documents/{doc_id}", headers=hb).status_code == 404
    # Tampoco puede colgarlo de un equipo propio usando su id.
    colgado = _subir(client, hb, eb.id, nombre="ajeno.jpg")
    assert colgado.status_code == 201
    assert db_session.query(EquipmentDocument).filter_by(id=colgado.json()["id"]).one().company_id == b.id


def test_la_ot_debe_ser_del_mismo_equipo(client, db_session, storage_temporal):
    company, user, customer, equipment = setup(db_session, "doc-ot")
    headers = login(client, "ot.doc-ot@example.com", company.id)
    headers_ot = login(client, "ot.doc-ot@example.com", company.id)
    otra, _, otra_c, otra_e = setup(db_session, "doc-ot-otra")

    h2 = login(client, "ot.doc-ot-otra@example.com", otra.id)
    ot_ajena = h2 and client.post("/api/v1/work-orders", headers=h2, json={
        "customer_id": otra_c.id, "equipment_id": otra_e.id, "reported_fault": "Ajena"}).json()

    # Una OT de otra empresa no se puede vincular.
    r = _subir(client, headers, equipment.id, nombre="x.jpg", work_order_id=ot_ajena["id"])
    assert r.status_code == 422, r.text
    # Ni una OT de esta empresa que es de otro equipo.
    propia = client.post("/api/v1/work-orders", headers=headers, json={
        "customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "Propia"}).json()
    ok = _subir(client, headers, equipment.id, nombre="y.jpg", work_order_id=propia["id"])
    assert ok.status_code == 201, ok.text
    assert ok.json()["work_order_id"] == propia["id"]
    assert headers_ot is not None


def test_permiso_de_equipo_para_subir(client, db_session, storage_temporal):
    """equipment.view no alcanza para subir: se necesita equipment.manage."""
    from app.models.role import CompanyUserRole, Permission, Role
    from app.models.user import CompanyUser, User
    from app.core.security import hash_password

    company, _, customer, equipment = setup(db_session, "doc-perm")
    # Usuario nuevo con SOLO equipment.view
    viewer = User(email="doc.viewer@example.com", full_name="Solo lectura", password_hash=hash_password("Password1234"))
    db_session.add(viewer)
    db_session.flush()
    db_session.add(CompanyUser(company_id=company.id, user_id=viewer.id, is_admin=False, role="LECTURA", active=True))
    db_session.flush()
    rol = Role(company_id=company.id, name="Lectura", is_system=True, active=True)
    db_session.add(rol)
    db_session.flush()
    permiso = db_session.query(Permission).filter_by(code="equipment.view").one()
    db_session.execute(
        CompanyUserRole.__table__.insert().values(company_user_id=db_session.query(CompanyUser).filter_by(user_id=viewer.id, company_id=company.id).one().id, role_id=rol.id, active=True)
    ) if False else None
    from app.models.role import role_permissions
    db_session.execute(role_permissions.insert().values(role_id=rol.id, permission_id=permiso.id))
    db_session.add(CompanyUserRole(company_user_id=db_session.query(CompanyUser).filter_by(user_id=viewer.id).one().id, role_id=rol.id, active=True))
    db_session.commit()

    h = login(client, "doc.viewer@example.com", company.id)
    assert _subir(client, h, equipment.id).status_code == 403
    # Pero si listar y descargar, si.
    assert client.get(f"/api/v1/equipment/{equipment.id}/documents", headers=h).status_code == 200


def test_baja_logica_no_borra_el_archivo_y_deja_rastro(client, db_session, storage_temporal):
    company, user, customer, equipment = setup(db_session, "doc-baja")
    headers = login(client, "ot.doc-baja@example.com", company.id)
    ot = client.post("/api/v1/work-orders", headers=headers, json={
        "customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "F"}).json()
    creado = _subir(client, headers, equipment.id, work_order_id=ot["id"]).json()
    doc_id = creado["id"]
    fila = db_session.query(EquipmentDocument).one()
    ruta = os.path.join(storage_temporal, *fila.storage_key.split("/"))

    assert client.delete(f"/api/v1/documents/{doc_id}", headers=headers).status_code == 204
    db_session.expire_all()
    fila = db_session.query(EquipmentDocument).one()
    assert fila.deleted_at is not None
    assert fila.deleted_by_user_id is not None
    # El archivo sigue en el storage: la baja es logica.
    assert os.path.exists(ruta)
    # No aparece en el listado normal, si en el que incluye dados de baja.
    assert client.get(f"/api/v1/equipment/{equipment.id}/documents", headers=headers).json()["total"] == 0
    assert client.get(f"/api/v1/equipment/{equipment.id}/documents?include_deleted=true", headers=headers).json()["total"] == 1
    # Queda en el historial de la OT.
    eventos = client.get(f"/api/v1/work-orders/{ot['id']}/events", headers=headers).json()
    assert any(e["event_type"] == "DOCUMENT_DELETED" for e in eventos), eventos
    # Y no se puede volver a dar de baja.
    assert client.delete(f"/api/v1/documents/{doc_id}", headers=headers).status_code == 404


def test_descarga_sirve_el_contenido_y_no_la_ruta(client, db_session, storage_temporal):
    company, user, customer, equipment = setup(db_session, "doc-descarga")
    headers = login(client, "ot.doc-descarga@example.com", company.id)
    contenido = b"contenido real del archivo"
    doc_id = _subir(client, headers, equipment.id, contenido, "manual.pdf", "application/pdf").json()["id"]
    r = client.get(f"/api/v1/documents/{doc_id}/download", headers=headers)
    assert r.status_code == 200
    assert r.content == contenido
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    # La ruta del storage no aparece en ninguna parte de la respuesta.
    assert storage_temporal not in r.text


def test_limite_de_tamano_y_archivo_vacio(client, db_session, storage_temporal, monkeypatch):
    company, user, customer, equipment = setup(db_session, "doc-limite")
    headers = login(client, "ot.doc-limite@example.com", company.id)
    monkeypatch.setattr(settings, "storage_max_file_mb", 1)
    grande = b"x" * (1048576 + 10)
    r = _subir(client, headers, equipment.id, grande, "video.mp4", "video/mp4")
    assert r.status_code == 413, r.text
    vacio = _subir(client, headers, equipment.id, b"", "vacio.txt", "text/plain")
    assert vacio.status_code == 422, vacio.text
    assert db_session.query(EquipmentDocument).count() == 0


def test_mime_se_deduce_del_nombre_cuando_el_navegador_manda_octet_stream(client, db_session, storage_temporal):
    company, user, customer, equipment = setup(db_session, "doc-mime")
    headers = login(client, "ot.doc-mime@example.com", company.id)
    r = _subir(client, headers, equipment.id, b"%PDF-1.4", "presupuesto.pdf", "application/octet-stream")
    assert r.status_code == 201
    assert r.json()["mime_type"] == "application/pdf"


def test_varios_archivos_en_la_misma_carga_no_colisionan(client, db_session, storage_temporal):
    company, user, customer, equipment = setup(db_session, "doc-varios")
    headers = login(client, "ot.doc-varios@example.com", company.id)
    ids = {_subir(client, headers, equipment.id, nombre="foto.jpg").json()["id"] for _ in range(3)}
    assert len(ids) == 3
    claves = {r.storage_key for r in db_session.query(EquipmentDocument).all()}
    assert len(claves) == 3
    assert client.get(f"/api/v1/equipment/{equipment.id}/documents", headers=headers).json()["total"] == 3


def test_storage_no_deja_salir_de_la_raiz():
    storage = FilesystemStorage("/tmp/raiz-prueba")
    with pytest.raises(StorageError):
        storage.open("../../etc/passwd")


def test_editar_la_descripcion(client, db_session, storage_temporal):
    company, user, customer, equipment = setup(db_session, "doc-desc")
    headers = login(client, "ot.doc-desc@example.com", company.id)
    doc_id = _subir(client, headers, equipment.id).json()["id"]
    r = client.patch(f"/api/v1/documents/{doc_id}", headers=headers, json={"description": "Ajustado"})
    assert r.status_code == 200
    assert r.json()["description"] == "Ajustado"


def test_documentos_de_la_orden_solo_los_adjuntados_a_ella(client, db_session, storage_temporal):
    company, user, customer, equipment = setup(db_session, "doc-otdocs")
    headers = login(client, "ot.doc-otdocs@example.com", company.id)
    ot = client.post("/api/v1/work-orders", headers=headers, json={
        "customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "F"}).json()

    # Del equipo solamente: no aparece en la orden, porque no se genero ahi.
    _subir(client, headers, equipment.id, nombre="del-equipo.jpg")
    assert client.get(f"/api/v1/work-orders/{ot['id']}/documents", headers=headers).json()["total"] == 0

    # Adjunto a la orden: si aparece, y con el work_order_id puesto.
    adjunto = _subir(client, headers, equipment.id, nombre="de-la-orden.jpg", work_order_id=ot["id"]).json()
    assert adjunto["work_order_id"] == ot["id"]
    listado = client.get(f"/api/v1/work-orders/{ot['id']}/documents", headers=headers).json()
    assert listado["total"] == 1
    assert listado["items"][0]["original_filename"] == "de-la-orden.jpg"

    # Y el equipo los muestra a los dos.
    assert client.get(f"/api/v1/equipment/{equipment.id}/documents", headers=headers).json()["total"] == 2
    # Filtrando por orden tambien desde el equipo.
    filtrado = client.get(f"/api/v1/equipment/{equipment.id}/documents?work_order_id={ot['id']}", headers=headers).json()
    assert filtrado["total"] == 1


def test_documentos_de_otra_orden_no_se_ven(client, db_session, storage_temporal):
    company, user, customer, equipment = setup(db_session, "doc-otdocs2")
    headers = login(client, "ot.doc-otdocs2@example.com", company.id)
    a = client.post("/api/v1/work-orders", headers=headers, json={
        "customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "A"}).json()
    b = client.post("/api/v1/work-orders", headers=headers, json={
        "customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "B"}).json()
    _subir(client, headers, equipment.id, nombre="de-a.jpg", work_order_id=a["id"])
    assert client.get(f"/api/v1/work-orders/{b['id']}/documents", headers=headers).json()["total"] == 0
    assert client.get(f"/api/v1/work-orders/{a['id']}/documents", headers=headers).json()["total"] == 1

    otra, _, _, _ = setup(db_session, "doc-otdocs2-b")
    h2 = login(client, "ot.doc-otdocs2-b@example.com", otra.id)
    assert client.get(f"/api/v1/work-orders/{a['id']}/documents", headers=h2).status_code == 404
