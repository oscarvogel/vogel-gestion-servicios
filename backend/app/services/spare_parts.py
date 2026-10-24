"""Servicio del catalogo de repuestos de Flexxus (#114).

El servicio es el que decide **a quien** se le muestra el catalogo. El
adaptador de Firebird no sabe nada de empresas: solo sabe leer.

La habilitacion es por parametro de empresa (`flexxus.enabled`), no por slug
clavado en el codigo: asi se puede prender y apagar sin tocar el codigo, y
queda a la vista en la pantalla de Parametros.

Orden de las cosas, y es lo que evita que se filtre el catalogo de otro:

1. La empresa activa tiene que tener `flexxus.enabled` en true. Si no, se
   responde "no disponible" **sin abrir ninguna conexion** al ERP.
2. Recien ahi se arma el cliente y se consulta.

El credencial (host, puerto, usuario, clave) es de plataforma: no se guarda
por empresa. Lo que se guarda por empresa es la habilitacion y que base usa.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.flexxus.client import FlexxusClient, FlexxusUnavailable
from app.models.company import CompanyParameter, ParameterDefinition

LOGGER = logging.getLogger(__name__)

PARAM_ENABLED = "flexxus.enabled"
PARAM_DATABASE = "flexxus.database"
PARAM_PRICE_LIST = "flexxus.price_list"

AVISO_NO_DISPONIBLE = (
    "El catalogo de repuestos no esta disponible para esta empresa."
)
AVISO_ERP_CAIDO = (
    "No se pudo consultar el catalogo de repuestos en Flexxus. "
    "Segui operando: el repuesto se carga a mano."
)
AVISO_SIN_CREDENCIAL = (
    "No hay credencial de Flexxus configurada en el servidor."
)
# El ERP es el ERP de otro cliente: bombardearlo con una consulta por tecla
# es una falta de respeto. Se cachea la consulta un rato corto: el operador
# escribiendo "adaptador" no golpea el ERP en cada tecla.
_CACHE_TTL_SEGUNDOS = 30
_CACHE_MAX_ENTRADAS = 200
_cache: dict[tuple, tuple[float, list]] = {}


def _cache_leer(clave: tuple) -> list | None:
    entrada = _cache.get(clave)
    if entrada is None:
        return None
    momento, items = entrada
    if time.monotonic() - momento > _CACHE_TTL_SEGUNDOS:
        _cache.pop(clave, None)
        return None
    return items


def _cache_guardar(clave: tuple, items: list) -> None:
    if len(_cache) >= _CACHE_MAX_ENTRADAS:
        mas_vieja = min(_cache.items(), key=lambda kv: kv[1][0])[0]
        _cache.pop(mas_vieja, None)
    _cache[clave] = (time.monotonic(), items)


def read_parameter(db: Session, company_id: int, name: str, default: str = "") -> str:
    """Valor efectivo del parametro: el override de la empresa o el default.

    Misma precedencia que la pantalla de Parametros, para que lo que el
    usuario ve configurado sea lo que el modulo realmente respeta.
    """
    definition = (
        db.query(ParameterDefinition)
        .filter_by(parameter=name, active=True)
        .first()
    )
    if definition is None:
        return default
    override = (
        db.query(CompanyParameter)
        .filter_by(
            parameter_definition_id=definition.id, company_id=company_id
        )
        .first()
    )
    return (
        override.value
        if override and override.value is not None
        else definition.default_value
    ) or default


def is_enabled(db: Session, company_id: int) -> bool:
    """Si a esta empresa se le muestra el catalogo de Flexxus."""
    raw = read_parameter(db, company_id, PARAM_ENABLED, "false").strip().lower()
    return raw in ("1", "true", "yes", "si", "sí", "on")


def _price_list(db: Session, company_id: int) -> int:
    try:
        valor = int(
            float(read_parameter(db, company_id, PARAM_PRICE_LIST, "1").strip() or 1)
        )
    except (TypeError, ValueError):
        return 1
    # Solo existen cinco listas de venta en el ERP.
    return valor if 1 <= valor <= 5 else 1


def _database(db: Session, company_id: int) -> str:
    return (
        read_parameter(db, company_id, PARAM_DATABASE, settings.flexxus_database).strip()
        or settings.flexxus_database
    )


def _cliente(db: Session, company_id: int) -> FlexxusClient:
    return FlexxusClient(
        host=settings.flexxus_host,
        port=settings.flexxus_port,
        user=settings.flexxus_user,
        password=settings.flexxus_password,
        charset=settings.flexxus_charset,
        database=_database(db, company_id),
        timeout=settings.flexxus_timeout_seconds,
    )


def buscar_repuestos(
    db: Session,
    company_id: int,
    texto: str,
    limite: int = 20,
) -> dict[str, Any]:
    """Busca repuestos en el catalogo de Flexxus.

    Nunca levanta: si el modulo no esta habilitado para la empresa, o si el
    ERP no responde, devuelve la busqueda vacia con un aviso. La carga de la
    OT y el presupuesto tienen que seguir funcionando igual.
    """
    if not is_enabled(db, company_id):
        # Aca se corta, antes de tocar la red: una empresa que no tiene el
        # modulo habilitado no abre ni un socket contra el ERP.
        #
        # Sin aviso: que el modulo no aplique es el estado normal de todas las
        # empresas menos una, no una falla. El aviso se reserva para cuando el
        # catalogo CORRESPONDE y algo se rompio (ERP caido, sin credencial):
        # ahi si hay que avisarle al operador.
        return {"disponible": False, "aviso": None, "items": []}

    precio_lista = _price_list(db, company_id)
    clave = (company_id, (texto or "").strip().upper(), limite, precio_lista)
    en_cache = _cache_leer(clave)
    if en_cache is not None:
        return {"disponible": True, "aviso": None, "items": en_cache}

    try:
        items = _cliente(db, company_id).buscar_articulos(
            texto, limite=limite, precio_lista=precio_lista
        )
    except FlexxusUnavailable as exc:
        LOGGER.warning("Flexxus no disponible: %s", exc)
        return {"disponible": False, "aviso": AVISO_ERP_CAIDO, "items": []}

    _cache_guardar(clave, items)
    return {"disponible": True, "aviso": None, "items": items}


def estado(db: Session, company_id: int) -> dict[str, Any]:
    """Si el catalogo aplica a esta empresa, y por que no.

    **No abre conexion al ERP**: es solo la habilitacion y que haya
    credencial. El frontend lo consulta al montar el combo para saber si tiene
    que exigir elegir una opcion o dejar escribir a mano.

    `falla` distingue las dos razones por las que no hay catalogo:

    - ``falla: False`` -> la empresa no tiene el modulo. Es el estado normal
      de todas menos una: no se le muestra ningun aviso, porque no hay nada
      que avisar. La pantalla se ve igual que antes del modulo.
    - ``falla: True`` -> el catalogo corresponde pero no se puede usar (ERP
      caido, credencial faltante). Ahi si se avisa, porque el operador esta
      perdiendo una funcion que deberia tener.
    """
    if not is_enabled(db, company_id):
        return {"disponible": False, "motivo": AVISO_NO_DISPONIBLE, "falla": False}
    if not settings.flexxus_password:
        return {"disponible": False, "motivo": AVISO_SIN_CREDENCIAL, "falla": True}
    return {"disponible": True, "motivo": None, "falla": False}


def obtener_repuesto(
    db: Session,
    company_id: int,
    codigo: str,
) -> dict[str, Any] | None:
    """Un repuesto por codigo de articulo, o None si no esta disponible."""
    if not is_enabled(db, company_id):
        return None
    try:
        return _cliente(db, company_id).obtener_articulo(
            codigo, precio_lista=_price_list(db, company_id)
        )
    except FlexxusUnavailable as exc:
        LOGGER.warning("Flexxus no disponible: %s", exc)
        return None
