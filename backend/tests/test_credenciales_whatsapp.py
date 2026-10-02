"""Credenciales de WhatsApp por empresa.

Cada empresa habla con la gateway con SU API key y SU instancia, asi que sus clientes
reciben los avisos desde el numero de la empresa. La key se guarda cifrada con Fernet y
es de solo escritura: la API nunca la devuelve.
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.company import Company
from app.services import credentials
from app.services.credentials import CredentialError
from app.services.notifications.channels import WHATSAPP, _instance_for, _whatsapp_key_for
from app.services.notifications.enqueue import FAILED, QUEUED
from tests.test_notificaciones import _configure, _set_contact, senders
from tests.test_work_orders import login, setup

from cryptography.fernet import Fernet

MAESTRA = Fernet.generate_key().decode()
OTRA_MAESTRA = Fernet.generate_key().decode()


@pytest.fixture
def con_clave_maestra(monkeypatch):
    monkeypatch.setattr(settings, "credentials_encryption_key", MAESTRA)
    return MAESTRA


def test_cifrado_ida_y_vuelta(con_clave_maestra):
    cifrado = credentials.encrypt("clave-de-la-gateway")
    assert cifrado and "clave-de-la-gateway" not in cifrado
    assert credentials.decrypt(cifrado) == "clave-de-la-gateway"
    # Cifrar dos veces el mismo valor da cosas distintas: no es un hash desnudo.
    assert credentials.encrypt("misma") != credentials.encrypt("misma")
    # Una credencial vacia no se guarda.
    assert credentials.encrypt("") is None and credentials.encrypt("   ") is None


def test_sin_clave_maestra_no_se_guarda_nada(monkeypatch):
    """Preferimos fallar antes que guardar credenciales en claro."""
    monkeypatch.setattr(settings, "credentials_encryption_key", None)
    assert credentials.is_available() is False
    with pytest.raises(CredentialError) as exc:
        credentials.encrypt("clave-de-la-gateway")
    assert "CREDENTIALS_ENCRYPTION_KEY" in str(exc.value)
    # El mensaje no filtra la credencial que se quiso guardar.
    assert "clave-de-la-gateway" not in str(exc.value)


def test_clave_maestra_invalida_distingue_de_sin_clave(monkeypatch):
    monkeypatch.setattr(settings, "credentials_encryption_key", "no-es-una-clave-fernet")
    with pytest.raises(CredentialError) as exc:
        credentials.encrypt("x")
    assert "Fernet valida" in str(exc.value)


def test_la_api_nunca_devuelve_la_key(client, db_session, con_clave_maestra):
    company, _, _, _ = setup(db_session, "key-writeonly")
    headers = login(client, "ot.key-writeonly@example.com", company.id)
    guardado = client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={
        "whatsapp_instance_id": "ceramica",
        "whatsapp_api_key": "super-secreta-123",
    })
    assert guardado.status_code == 200, guardado.text
    cuerpo = guardado.text
    assert "super-secreta-123" not in cuerpo, "la respuesta del PATCH filtra la key"
    leido = client.get("/api/v1/work-orders/notification-settings", headers=headers)
    assert "super-secreta-123" not in leido.text, "el GET filtra la key"
    assert leido.json()["whatsapp_api_key_configured"] is True
    # Y tampoco esta en el listado de empresas.
    assert "super-secreta-123" not in client.get("/api/v1/companies/current", headers=headers).text
    # En la base esta cifrada.
    fila = db_session.query(Company).filter_by(id=company.id).one()
    assert "super-secreta-123" not in (fila.whatsapp_api_key_encrypted or "")
    assert credentials.decrypt(fila.whatsapp_api_key_encrypted) == "super-secreta-123"


def test_clearing_y_rotate(client, db_session, con_clave_maestra):
    company, _, _, _ = setup(db_session, "key-rotate")
    headers = login(client, "ot.key-rotate@example.com", company.id)
    client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={"whatsapp_api_key": "primera"})
    assert client.get("/api/v1/work-orders/notification-settings", headers=headers).json()["whatsapp_api_key_configured"] is True
    # Rotar: manda otra key y reemplaza la anterior.
    client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={"whatsapp_api_key": "segunda"})
    fila = db_session.query(Company).filter_by(id=company.id).one()
    assert credentials.decrypt(fila.whatsapp_api_key_encrypted) == "segunda"
    # Limpiar.
    client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={"whatsapp_api_key_clear": True})
    assert client.get("/api/v1/work-orders/notification-settings", headers=headers).json()["whatsapp_api_key_configured"] is False


def test_el_envio_usa_la_key_de_la_empresa(client, db_session, con_clave_maestra, monkeypatch):
    """Dos empresas con keys distintas: cada una manda con la suya."""
    captured = []

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.append((url, headers.get("x-api-key")))
        class R:
            status_code = 202
            text = ""
            def json(self): return {"success": True, "data": {"messageId": "m-1", "status": "queued"}}
        return R()

    monkeypatch.setattr(httpx_module(), "post", fake_post)
    a, _, ca, ea = setup(db_session, "key-envia-a")
    b, _, cb, eb = setup(db_session, "key-envia-b")
    ha = login(client, "ot.key-envia-a@example.com", a.id)
    hb = login(client, "ot.key-envia-b@example.com", b.id)
    for company, headers, sufijo in ((a, ha, "a"), (b, hb, "b")):
        _set_contact(db_session, company, whatsapp="5493764000000")
        client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={
            "whatsapp_instance_id": f"instancia-{sufijo}", "whatsapp_api_key": f"key-de-la-empresa-{sufijo}",
        })
    status_a = _configure(client, ha, "Avisar A", notify_whatsapp=True)
    status_b = _configure(client, hb, "Avisar B", notify_whatsapp=True)
    for headers, customer, equipment, status_id in ((ha, ca, ea, status_a), (hb, cb, eb, status_b)):
        ot = client.post("/api/v1/work-orders", headers=headers, json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "F"}).json()
        client.post(f"/api/v1/work-orders/{ot['id']}/status", headers=headers, json={"status_id": status_id})
    assert sorted(captured) == sorted([
        ("https://whatsapp.vogelconsultoria.com.ar/api/v1/instances/instancia-a/messages", "key-de-la-empresa-a"),
        ("https://whatsapp.vogelconsultoria.com.ar/api/v1/instances/instancia-b/messages", "key-de-la-empresa-b"),
    ]), captured


def test_sin_key_propia_falla_en_vez_de_mandar_desde_el_numero_de_otro(client, db_session, con_clave_maestra, monkeypatch):
    """El comportamiento clave: sin opt-in, no se usa la key de plataforma."""
    monkeypatch.setattr(settings, "whatsapp_api_key", "key-de-plataforma")
    monkeypatch.setattr(settings, "whatsapp_default_instance", "vogel")
    company, _, customer, equipment = setup(db_session, "key-sinpropia")
    headers = login(client, "ot.key-sinpropia@example.com", company.id)
    _set_contact(db_session, company, whatsapp="5493764000000")
    status_id = _configure(client, headers, "Avisar", notify_whatsapp=True)
    ot = client.post("/api/v1/work-orders", headers=headers, json={"customer_id": customer.id, "equipment_id": equipment.id, "reported_fault": "F"}).json()
    client.post(f"/api/v1/work-orders/{ot['id']}/status", headers=headers, json={"status_id": status_id})
    fila = db_session.query(Company).filter_by(id=company.id).one()
    key, motivo = _whatsapp_key_for(fila)
    assert key is None
    assert "no tiene API key" in motivo
    assert _instance_for(fila) is None, "no debe cae[r] en la instancia de plataforma sin opt-in"


def test_opt_in_explicito_usa_la_key_de_plataforma(client, db_session, con_clave_maestra, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_api_key", "key-de-plataforma")
    monkeypatch.setattr(settings, "whatsapp_default_instance", "vogel")
    company, _, _, _ = setup(db_session, "key-optin")
    headers = login(client, "ot.key-optin@example.com", company.id)
    client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={"whatsapp_use_platform_key": True})
    fila = db_session.query(Company).filter_by(id=company.id).one()
    key, motivo = _whatsapp_key_for(fila)
    assert key == "key-de-plataforma" and motivo is None
    assert _instance_for(fila) == "vogel"


def test_la_key_de_la_empresa_manda_sobre_el_opt_in(client, db_session, con_clave_maestra, monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_api_key", "key-de-plataforma")
    company, _, _, _ = setup(db_session, "key-precedence")
    headers = login(client, "ot.key-precedence@example.com", company.id)
    client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={
        "whatsapp_api_key": "key-propia", "whatsapp_use_platform_key": True,
    })
    fila = db_session.query(Company).filter_by(id=company.id).one()
    key, motivo = _whatsapp_key_for(fila)
    assert key == "key-propia" and motivo is None


def test_clave_maestra_rotada_distingue_el_error(client, db_session, monkeypatch):
    """Si la maestra no descifra, el motivo lo dice: hay que recargar la credencial."""
    monkeypatch.setattr(settings, "credentials_encryption_key", MAESTRA)
    company, _, _, _ = setup(db_session, "key-rotada")
    headers = login(client, "ot.key-rotada@example.com", company.id)
    client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={"whatsapp_api_key": "guardada-con-otra"})
    monkeypatch.setattr(settings, "credentials_encryption_key", OTRA_MAESTRA)
    fila = db_session.query(Company).filter_by(id=company.id).one()
    key, motivo = _whatsapp_key_for(fila)
    assert key is None
    assert "volver a cargar" in motivo


def test_sin_clave_maestra_el_endpoint_responde_claro(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "credentials_encryption_key", None)
    company, _, _, _ = setup(db_session, "key-sinmaestra")
    headers = login(client, "ot.key-sinmaestra@example.com", company.id)
    r = client.patch("/api/v1/work-orders/notification-settings", headers=headers, json={"whatsapp_api_key": "x"})
    assert r.status_code == 503
    assert "CREDENTIALS_ENCRYPTION_KEY" in r.text


def test_una_empresa_no_toca_la_credencial_de_otra(client, db_session, con_clave_maestra):
    a, _, _, _ = setup(db_session, "key-iso-a")
    b, _, _, _ = setup(db_session, "key-iso-b")
    ha = login(client, "ot.key-iso-a@example.com", a.id)
    hb = login(client, "ot.key-iso-b@example.com", b.id)
    client.patch("/api/v1/work-orders/notification-settings", headers=ha, json={"whatsapp_api_key": "key-a", "whatsapp_instance_id": "inst-a"})
    assert client.get("/api/v1/work-orders/notification-settings", headers=hb).json()["whatsapp_api_key_configured"] is False
    assert client.get("/api/v1/work-orders/notification-settings", headers=hb).json()["whatsapp_instance_id"] is None
    fila_b = db_session.query(Company).filter_by(id=b.id).one()
    assert fila_b.whatsapp_api_key_encrypted is None


def httpx_module():
    import httpx
    return httpx
