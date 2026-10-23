"""Paso 0: las personas.

Arma lo que el legacy llama ``dbo.CC_Usuarios`` y sus tareas:

- los **estados** de la OT (los 8 por defecto de la empresa + los 3 que el legacy
  usa y el destino no tiene),
- los **usuarios**: la tabla ``users`` es global (no depende de la empresa), asi que
  los usuarios del legacy se crean ahi y se asocian a la empresa con ``company_users``,
- los **vendedores** (``CC_Usuarios`` con la tarea "Vendedor"),
- los **tecnicos** (``CC_Usuarios`` con la tarea "Tecnico", mas los que
  intervinieron en una OT sin existir ya como usuario).

De los usuarios del legacy, 39 de los responsables de OT y 40 de los que
intervinieron ya no existen: para esos el legacy los muestra como "Sistema".
"""

from __future__ import annotations

import re
import secrets
from collections import Counter

from sqlalchemy import select

from app.core.security import hash_password

from .. import mappers, source
from ..context import Contexto
from ..source import FuenteCiberBase

#: Correo sintetico para los usuarios del legacy sin correo utilizable. El dominio
#: ``.invalid`` esta reservado por RFC 2606: nunca puede ser un correo real.
DOMINIO_SINTETICO = "legacy.invalid"

#: Email del usuario de respaldo, para los responsables que ya no existen.
EMAIL_RESPALDO = f"cyberbrain.legacy@{DOMINIO_SINTETICO}"

#: Nombre del usuario de respaldo.
NOMBRE_RESPALDO = "ImportaciÃ³n / legacy"

_EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _correo_de_respaldo(codigo: str) -> str:
    """Correo sintetico y unico para un usuario del legacy."""
    return f"cyberbrain.{codigo}@{DOMINIO_SINTETICO}"


def _usuarios_legacy(fuente: FuenteCiberBase) -> list[dict[str, object]]:
    """Lee los usuarios del legacy y los pasa a diccionarios."""
    filas = []
    for codigo, nombre, email, descripcion, es_tecnico, es_vendedor, es_facturista in fuente.usuarios():
        filas.append(
            {
                "codigo": source.texto(codigo),
                "nombre": source.texto(nombre),
                "email": source.texto(email),
                "descripcion": source.texto(descripcion),
                "es_tecnico": source.entero(es_tecnico, 0) == 1,
                "es_vendedor": source.entero(es_vendedor, 0) == 1,
                "es_facturista": source.entero(es_facturista, 0) == 1,
            }
        )
    return filas


def _personas_de_intervenciones(fuente: FuenteCiberBase) -> set[str]:
    """Codigos de persona que aparecen en las intervenciones o en las comisiones.

    Son las personas que quedaron en las OTs aunque ya no existan como usuario: el
    legacy las muestra como "Sistema" y hay que importarlas igual, o las
    intervenciones quedan sin tecnico.
    """
    personas: set[str] = set()
    for fila in fuente.intervenciones():
        personas.add(source.texto(fila[1]))
    for fila in fuente.comisiones_linea():
        personas.add(source.texto(fila[1]))
    return personas


def ejecutar(ctx: Contexto) -> None:
    """Crea estados, usuarios, vendedores y tecnicos de la empresa."""
    _estados(ctx)
    _usuarios(ctx)
    _vendedores(ctx)
    _tecnicos(ctx)


# ---------------------------------------------------------------------------
# Estados
# ---------------------------------------------------------------------------
def _estados(ctx: Contexto) -> None:
    """Se asegura de que existan los 8 estados por defecto y los 3 del legacy.

    Los 3 del legacy ("Faltan requisitos", "Rechazada", "Anulada") no estan entre los
    defaults del destino y hay que crearlos: sin ellos, 115 OTs del corte no tendrian
    estado.
    """
    tabla = ctx.tabla("work_order_statuses")
    existentes = set(
        ctx.session.execute(
            select(tabla.c.name).where(tabla.c.company_id == ctx.company_id)
        ).scalars()
    )
    faltantes = []
    for nombre, color, orden, inicial, final, completado, entregado in mappers.ESTADOS_POR_DEFECTO:
        if nombre not in existentes:
            faltantes.append(
                {
                    "company_id": ctx.company_id,
                    "name": nombre,
                    "color": color,
                    "sort_order": orden,
                    "is_initial": inicial,
                    "is_final": final,
                    "marks_completed": completado,
                    "marks_delivered": entregado,
                }
            )
    for nombre, color, orden in mappers.ESTADOS_LEGACY_EXTRA:
        if nombre not in existentes:
            faltantes.append(
                {
                    "company_id": ctx.company_id,
                    "name": nombre,
                    "color": color,
                    "sort_order": orden,
                    "is_initial": False,
                    "is_final": False,
                    "marks_completed": False,
                    "marks_delivered": False,
                }
            )
    ctx.insertar(tabla, faltantes)
    ctx.reporte.linea(
        "work_order_statuses",
        "destino",
        leidos=len(faltantes),
        insertados=len(faltantes),
        motivo="8 por defecto + 'Faltan requisitos', 'Rechazada' y 'Anulada' (legacy)",
    )


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
def _usuarios(ctx: Contexto) -> None:
    """Crea los usuarios del legacy y los asocia a la empresa.

    La tabla ``users`` es global: el mismo correo no puede existir dos veces. El
    legacy tiene 44 usuarios y solo 8 correos distintos (19 de ellos comparten
    ``serviciotecnico@electrotecniref.com.ar``), asi que el correo se sintetiza
    cuando no es utilizable o esta repetido.
    """
    usuarios = _usuarios_legacy(ctx.fuente)
    tabla_usuarios = ctx.tabla("users")
    tabla_membresias = ctx.tabla("company_users")

    por_correo = {
        fila.email: fila.id
        for fila in ctx.session.execute(select(tabla_usuarios.c.email, tabla_usuarios.c.id)).all()
    }
    usos = Counter(u["email"] for u in usuarios if u["email"])

    a_crear: list[dict[str, object]] = []
    codigos_de_creacion: list[str] = []
    for usuario in usuarios:
        codigo = str(usuario["codigo"])
        correo = str(usuario["email"])
        if not _EMAIL_VALIDO.match(correo) or usos.get(correo, 0) > 1:
            correo = _correo_de_respaldo(codigo)
        if correo in por_correo:
            ctx.usuarios_por_codigo[codigo] = por_correo[correo]
            continue
        a_crear.append(
            {
                "email": source.recortar("users.email", correo, 255),
                "full_name": source.recortar("users.full_name", usuario["nombre"], 150)
                or f"Legacy {codigo}",
                # Contrasena aleatoria: el usuario del legacy existe como referencia
                # historica, no como cuenta de acceso.
                "password_hash": hash_password(secrets.token_urlsafe(32)),
                "active": True,
                "is_superadmin": False,
            }
        )
        codigos_de_creacion.append(codigo)

    ctx.insertar(tabla_usuarios, a_crear)
    for codigo, fila in zip(codigos_de_creacion, a_crear):
        ctx.usuarios_por_codigo[codigo] = int(fila["id"])
        por_correo[str(fila["email"])] = int(fila["id"])
        # El nombre del legacy sirve para resolver el campo 'Usuario' de la OT (D5).
        ctx.usuarios_por_nombre.setdefault(
            mappers.normalizar_nombre(str(fila["full_name"])), int(fila["id"])
        )
    for codigo, usuario_id in list(ctx.usuarios_por_codigo.items()):
        nombre = mappers.normalizar_nombre(
            next((u["nombre"] for u in usuarios if str(u["codigo"]) == codigo), "")
        )
        if nombre:
            ctx.usuarios_por_nombre.setdefault(nombre, usuario_id)

    # Usuario de respaldo: se usa cuando el responsable de la OT ya no existe como
    # usuario del legacy (``received_by_user_id`` es NOT NULL).
    respaldo_id = por_correo.get(EMAIL_RESPALDO)
    if respaldo_id is None:
        fila = {
            "email": EMAIL_RESPALDO,
            "full_name": NOMBRE_RESPALDO,
            "password_hash": hash_password(secrets.token_urlsafe(32)),
            "active": True,
            "is_superadmin": False,
        }
        ctx.insertar(tabla_usuarios, [fila])
        respaldo_id = int(fila["id"])
        por_correo[EMAIL_RESPALDO] = respaldo_id
    ctx.usuario_respaldo = respaldo_id

    membresias_existentes = {
        fila[0]
        for fila in ctx.session.execute(
            select(tabla_membresias.c.user_id).where(
                tabla_membresias.c.company_id == ctx.company_id
            )
        ).all()
    }
    membresias = [
        {
            "company_id": ctx.company_id,
            "user_id": usuario_id,
            "role": "MEMBER",
            "is_admin": False,
            "active": True,
        }
        for usuario_id in {ctx.usuarios_por_codigo[str(u["codigo"])] for u in usuarios}
        if usuario_id not in membresias_existentes
    ]
    if respaldo_id not in membresias_existentes:
        membresias.append(
            {
                "company_id": ctx.company_id,
                "user_id": respaldo_id,
                "role": "MEMBER",
                "is_admin": False,
                "active": True,
            }
        )
    ctx.insertar(tabla_membresias, membresias)
    ctx.reporte.linea(
        "users",
        "users.tsv",
        leidos=len(usuarios),
        insertados=len(a_crear) + 1,
        omitidos=len(usuarios) - len(a_crear),
        motivo="usuarios del legacy (tabla global) + 'ImportaciÃ³n / legacy' de respaldo",
    )


# ---------------------------------------------------------------------------
# Vendedores y tecnicos
# ---------------------------------------------------------------------------
def _vendedores(ctx: Contexto) -> None:
    """Crea los vendedores: los ``CC_Usuarios`` con la tarea "Vendedor"."""
    tabla = ctx.tabla("sellers")
    existentes = {
        str(fila[0]): fila[1]
        for fila in ctx.session.execute(
            select(tabla.c.legacy_code, tabla.c.id).where(tabla.c.company_id == ctx.company_id)
        ).all()
        if fila[0] is not None
    }
    a_crear = []
    for usuario in _usuarios_legacy(ctx.fuente):
        if not usuario["es_vendedor"]:
            continue
        codigo = str(usuario["codigo"])
        if codigo in existentes:
            ctx.vendedores_por_codigo[codigo] = existentes[codigo]
            continue
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "name": source.recortar("sellers.name", usuario["nombre"], 150)
                or f"Vendedor {codigo}",
                "legacy_code": int(codigo),
                "user_id": ctx.usuarios_por_codigo.get(codigo),
                "active": True,
            }
        )
    ctx.insertar(tabla, a_crear)
    for fila in a_crear:
        ctx.vendedores_por_codigo[str(fila["legacy_code"])] = int(fila["id"])
    ctx.reporte.linea(
        "sellers",
        "users.tsv",
        leidos=len(a_crear) + len(existentes),
        insertados=len(a_crear),
        omitidos=len(existentes),
        motivo="usuarios del legacy con la tarea 'Vendedor'",
    )


def _tecnicos(ctx: Contexto) -> None:
    """Crea los tecnicos.

    Son tres fuentes: los ``CC_Usuarios`` con la tarea "Tecnico", las personas que
    intervinieron en una OT y las personas de las comisiones por linea. Los que ya
    no existen como usuario se importan con ``legacy_code`` y nombre "Sistema", que
    es como los muestra el legacy.
    """
    tabla = ctx.tabla("technicians")
    usuarios = {str(u["codigo"]): u for u in _usuarios_legacy(ctx.fuente)}
    codigos = set(usuarios)
    for usuario in usuarios.values():
        if usuario["es_tecnico"]:
            codigos.add(str(usuario["codigo"]))
    codigos |= _personas_de_intervenciones(ctx.fuente)

    a_crear = []
    huerfanos = 0
    for codigo in sorted(codigos, key=lambda c: (not c.isdigit(), int(c) if c.isdigit() else 0, c)):
        usuario = usuarios.get(codigo)
        if usuario is None:
            huerfanos += 1
            a_crear.append(
                {
                    "company_id": ctx.company_id,
                    "name": "Sistema",
                    "legacy_code": int(codigo) if codigo.isdigit() else None,
                    "user_id": None,
                    "active": True,
                }
            )
            continue
        a_crear.append(
            {
                "company_id": ctx.company_id,
                "name": source.recortar("technicians.name", usuario["nombre"], 150)
                or f"Tecnico {codigo}",
                "legacy_code": int(codigo) if codigo.isdigit() else None,
                "user_id": ctx.usuarios_por_codigo.get(codigo),
                "active": True,
            }
        )
    ctx.insertar(tabla, a_crear)
    for fila in a_crear:
        if fila["legacy_code"] is not None:
            ctx.tecnicos_por_codigo[str(fila["legacy_code"])] = int(fila["id"])
    ctx.reporte.linea(
        "technicians",
        "users.tsv + technicians.tsv + part_commissions.tsv",
        leidos=len(a_crear),
        insertados=len(a_crear),
        motivo=(
            f"{len(a_crear) - huerfanos} usuarios del legacy, "
            f"{huerfanos} personas borradas (nombre 'Sistema')"
        ),
    )
